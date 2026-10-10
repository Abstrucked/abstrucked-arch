"""The only execution boundary. Neither model text nor tool results grant rights."""

import os
from pathlib import Path
import selectors
import signal
import subprocess
import time
from typing import Callable

from .contracts import AssistantError, PolicyError, PreparedCall, ToolResult
from . import alerts, bash, diagnostics, status, themes, websearch
from .policy import Policy


def action_environment() -> dict[str, str]:
    environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "PAGER": "cat", "SYSTEMD_PAGER": "cat"}
    # Desktop connectivity is necessary; API keys, loader hooks and arbitrary PATHs are not.
    for name in ("HOME", "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR",
                 "DBUS_SESSION_BUS_ADDRESS", "XDG_CONFIG_HOME", "XDG_DATA_HOME"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


def _stop(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_bounded(argv: tuple[str, ...], timeout: int) -> int:
    """Drain at most 8KiB; terminate this tool's process group on cancellation/timeout."""
    return run_captured(argv, timeout)[0]


def theme_environment() -> dict[str, str]:
    environment = action_environment()
    # Only these extra values are needed by the existing theme pipeline.
    for name in ("XDG_STATE_HOME", "HYPRLAND_INSTANCE_SIGNATURE", "AWESOME_THEME"):
        if name in os.environ:
            environment[name] = os.environ[name]
    return environment


def git_environment() -> dict[str, str]:
    environment = action_environment()
    environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_SYSTEM": "/dev/null",
                        "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_ATTR_NOSYSTEM": "1",
                        "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1",
                        "GIT_ALLOW_PROTOCOL": "", "GIT_TERMINAL_PROMPT": "0"})
    return environment


def run_captured(argv: tuple[str, ...], timeout: int | float, *, environment: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Capture separate stdout/stderr under one 8KiB cap and a wall-clock deadline."""
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, env=action_environment() if environment is None else environment,
                               cwd="/", start_new_session=True, close_fds=True)
    assert process.stdout is not None and process.stderr is not None
    deadline = time.monotonic() + timeout
    seen = 0
    output = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssistantError("Tool timed out; its process group was stopped.")
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fd, 4096)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    seen += len(chunk)
                    if seen > 8192:
                        raise AssistantError("Tool exceeded its output limit and was stopped.")
                    output[key.data].extend(chunk)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssistantError("Tool timed out and was stopped.")
        try:
            code = process.wait(timeout=remaining)
            return code, output["stdout"].decode("utf-8", "replace"), output["stderr"].decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            raise AssistantError("Tool timed out and was stopped.") from None
    except BaseException:
        _stop(process)
        raise
    finally:
        process.stdout.close()
        process.stderr.close()


class Runner:
    def __init__(self, policy: Policy, *, dry_run: bool = False,
                 confirm: Callable[[PreparedCall], bool] | None = None,
                 preview: Callable[[PreparedCall], None] | None = None):
        self.policy = policy
        self.dry_run = dry_run
        self.confirm = confirm or (lambda call: False)
        self.preview = preview or (lambda call: None)
        self.children: list[subprocess.Popen] = []

    def run(self, call: PreparedCall) -> ToolResult:
        # Revalidate the frozen call at execution time. Hand-constructed calls cannot bypass policy.
        fresh = self.policy.prepare(call.name, call.argument_dict())
        if fresh != call:
            raise PolicyError("Prepared action changed; nothing executed.")
        self.preview(call)
        if self.dry_run:
            return ToolResult(call.name, "preview", {"arguments": call.argument_dict(), "argv": list(call.argv)})
        if call.mutates:
            if self.confirm(call) is not True:
                return ToolResult(call.name, "denied", {"message": "Action not approved; nothing executed."})
            # Approval applies to this exact call only; validation runs again before execution.
            if self.policy.prepare(call.name, call.argument_dict()) != call:
                raise PolicyError("Action changed after approval; nothing executed.")
            return self._action(call)
        args = call.argument_dict()
        if call.name == "bash":
            try:
                data = bash.run_readonly(call, self.policy.config, run_captured)
            except (AssistantError, OSError):
                return ToolResult(call.name, "error", {"message": "Bash sandbox/command failed or exceeded its limits; no unsandboxed fallback and no host writes."})
            command = bash.plan(self.policy.config, args)
            no_matches = (data["exit_code"] == 1 and not data["stderr"] and len(command.stages) == 1
                          and command.stages[0][0] in {"/usr/bin/grep", "/usr/bin/rg"})
            return ToolResult(call.name, "ok" if data["exit_code"] == 0 or no_matches else "error", data)
        elif call.name == "system_status":
            data = diagnostics.collect_system_status()
        elif call.name == "processes":
            data = diagnostics.collect_processes(args["limit"])
        elif call.name == "theme_status":
            data = themes.catalogue()
            # One overall deadline across the fixed, read-only current-selection commands.
            deadline = time.monotonic() + self.policy.config.tool_timeout
            for key, choices, argv in (
                    ("current_layout", "layouts", (str(themes.THEME_ROOT / "themectl"), "current")),
                    ("current_palette", "palettes", (str(themes.THEME_ROOT / "themectl"), "current", "--colors"))):
                if self.policy.prepare(call.name, args) != call:
                    raise PolicyError("Theme pipeline changed; no further commands executed.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AssistantError("Theme status timed out; no further commands executed.")
                code, stdout, stderr = run_captured(argv, remaining, environment=theme_environment())
                data[key] = themes.current_value(stdout, data[choices]) if not code and not stderr else "unavailable"
        elif call.name == "desktop_status":
            data = status.collect_desktop_status()
        elif call.name == "power_status":
            data = status.collect_power_status()
        elif call.name == "alerts_status":
            data = alerts.status(self.policy.config)
        elif call.name == "plugin_status":
            data = status.collect_plugin_status()
        elif call.name == "display_status":
            environment = theme_environment()
            connected = any(environment.get(name) for name in ("DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE"))
            if call.argv and connected:
                # Bypass the helper's unbounded/following state reads with a validated set.
                environment["WALLPAPER_SET"] = status.display_wallpaper_set()
            data = status.parse_display_list(self.read_only_output(call.argv, environment=environment) if call.argv and connected else None)
        elif call.name == "dotfiles_status":
            git = self.git_status_output(call) if call.argv else None
            data = status.collect_dotfiles_status(
                git, config_linked=status.link_matches(status.CONFIG_HOME / "os-assistant/config.toml",
                                                       status.REPOSITORY / "os-assistant/.config/os-assistant/config.toml"),
                launcher_linked=status.link_matches(Path.home() / ".local/bin/os-assistant",
                                                     status.REPOSITORY / "os-assistant/.local/bin/os-assistant"))
        elif call.name == "directory_usage":
            data = self.policy.directory_usage(call)
            from .filesystem import summary
            data.update({"root": args["root"], "path": args["path"],
                         "summary": summary(data, str(Path(args["root"]) / args["path"]))})
        elif call.name == "find_files":
            records, truncated = self.policy.scan(args["root"])
            data = diagnostics.collect_file_search(records, name_pattern=args["name_pattern"],
                                                   min_size_mb=args["min_size_mb"], limit=args["limit"])
            data = {**data, "root": args["root"], "truncated_scan": truncated,
                    "sample_only": True, "size_kind": "logical_bytes",
                    "excludes": "protected entries, symlinks and special files"}
        else:
            raise PolicyError("Tool has no authorized implementation.")
        return ToolResult(call.name, "ok", data)

    def read_only_output(self, argv: tuple[str, ...], *, environment: dict[str, str] | None = None) -> str | None:
        """Run one fixed, read-only helper command and return bounded stdout.

        Returns None when the helper is missing, fails, times out, or exceeds
        the output limit. Stderr is never surfaced to the model.
        """
        if not argv or not os.access(argv[0], os.X_OK):
            return None
        try:
            code, stdout, stderr = run_captured(argv, self.policy.config.tool_timeout,
                                               environment=action_environment() if environment is None else environment)
        except (AssistantError, OSError):
            return None
        return stdout if code == 0 and not stderr and len(stdout.encode("utf-8")) <= 8192 else None

    def git_status_output(self, call: PreparedCall) -> str | None:
        """Fail closed on external Git filters; never run hooks, fetch, or write the index."""
        environment = git_environment()
        deadline = time.monotonic() + self.policy.config.tool_timeout
        # Read only config key names, never values/URLs/credentials. Local attributes
        # can trigger clean/process filters even in status, so refuse configured filters.
        # Includes can point at private files, and normal status loads them. Refuse
        # their presence without following them, before executing status itself.
        # Do not use -C here: repository discovery itself can load includes before
        # config --no-includes is parsed. Direct --file inspection avoids discovery.
        preflight = ("/usr/bin/git", "config", "--file", str(status.REPOSITORY / ".git/config"), "--no-includes",
                     "--name-only", "--get-regexp", "^(filter\\.|include\\.|includeif\\.)")
        try:
            code, stdout, stderr = run_captured(preflight, self.policy.config.tool_timeout, environment=environment)
            if code != 1 or stdout or stderr:
                return None
            if self.policy.prepare(call.name, call.argument_dict()) != call:
                raise PolicyError("Git helper changed; no further commands executed.")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            code, stdout, stderr = run_captured(call.argv, remaining, environment=environment)
            return stdout if code == 0 and not stderr and len(stdout.encode("utf-8")) <= 8192 else None
        except (AssistantError, OSError):
            return None

    def _action(self, call: PreparedCall) -> ToolResult:
        try:
            if call.name == "bash":
                try:
                    return ToolResult(call.name, "ok", bash.run_mutation(call, self.policy.config))
                except (AssistantError, OSError):
                    return ToolResult(call.name, "error", {"message": "Approved file operation failed; changes may already have been applied. Inspect before retrying; no host shell ran."})
            if call.name in ("apply_theme", "set_theme"):
                try:
                    code, stdout, stderr = run_captured(call.argv, self.policy.config.theme_timeout,
                                                       environment=theme_environment())
                except (AssistantError, OSError):
                    return ToolResult(call.name, "error", {"message": "Theme helper was interrupted or exceeded its limits; changes may already have been applied. Inspect theme_status before retrying."})
                return ToolResult(call.name, "error" if code or stderr else "ok",
                                  {"selected": call.argument_dict(), "exit_code": code,
                                   "output": stdout, "warnings": stderr,
                                   "desktop_verified": False,
                                   "message": "Theme helper completed; desktop appearance is not verified." if not code and not stderr else
                                              "Theme helper failed or reported warnings; changes may already have been applied. Inspect theme_status before retrying."})
            if call.name == "web_search":
                args = call.argument_dict()
                try:
                    return ToolResult(call.name, "ok", websearch.search(self.policy.config, args["query"], args["limit"]))
                except AssistantError as error:
                    return ToolResult(call.name, "error", {"message": str(error)})
            if call.name == "launch_app":
                self.children = [child for child in self.children if child.poll() is None]
                child = subprocess.Popen(call.argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, env=action_environment(), cwd="/",
                                         start_new_session=True, close_fds=True)
                self.children.append(child)
                return ToolResult(call.name, "started", {"app": call.argument_dict()["app"], "pid": child.pid,
                                                        "message": "Launch requested; window visibility is not verified."})
            code = run_bounded(call.argv, self.policy.config.tool_timeout)
            if code:
                return ToolResult(call.name, "error", {"message": "Action utility failed.", "exit_code": code})
            return ToolResult(call.name, "ok", {"requested_percent": call.argument_dict()["percent"]})
        except OSError:
            raise AssistantError("Cannot start the approved action utility.") from None

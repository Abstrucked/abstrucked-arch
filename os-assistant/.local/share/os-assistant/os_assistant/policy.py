"""Deterministic capability checks, strict tool schemas and fd-based file walks."""

import os
from pathlib import Path
import stat
import time
import unicodedata

from .config import Config, STATUS_TOOLS, normalized_root
from .contracts import ConfigurationError, FileRecord, PolicyError, PreparedCall, ToolSchemaError
from . import bash, filesystem, status, themes


PROTECTED = {".ssh", ".gnupg", ".aws", ".azure", ".kube", ".password-store", ".config", ".git",
             ".netrc", ".npmrc", ".pypirc", ".git-credentials", "secrets", "credentials"}


def protected_name(name: str) -> bool:
    lower = name.lower()
    return (lower in PROTECTED or lower.startswith((".env", "credentials.", "secrets."))
            or lower.endswith((".pem", ".key", ".p12", ".token"))
            or lower.startswith(("id_rsa", "id_ed25519", "id_ecdsa", "id_dsa"))
            or any(unicodedata.category(c).startswith("C") for c in name))


def open_directory(path: str) -> int:
    """Walk from / using openat + O_NOFOLLOW; never resolve a symlink then trust it."""
    if not Path(path).is_absolute() or ".." in Path(path).parts:
        raise PolicyError("Folder is outside the approved path policy.")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in Path(path).parts[1:]:
            if protected_name(component):
                raise PolicyError("Protected folder access is forbidden.")
            new_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = new_fd
        return fd
    except (OSError, PolicyError):
        os.close(fd)
        raise PolicyError("Folder is unavailable, protected, or contains a symlink.") from None


def _schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def usage_roots(config: Config) -> tuple[str, ...]:
    # Content approval already includes metadata access, never the reverse.
    return tuple(dict.fromkeys((*config.allowed_roots, *(config.bash_roots if config.bash_enabled else ()))))


def tool_schemas(config: Config) -> list[dict]:
    definitions = [
        ("system_status", "Check general laptop health: returns total RAM and AVAILABLE RAM bytes, battery percent/charging status, CPU load averages, and TOTAL/USED/FREE DISK bytes for the home filesystem. Use for free disk space or RAM availability; no approved folder or arguments needed.", _schema({})),
        ("desktop_status", "Read-only desktop overview: which compositor and app processes run, current theme layout and palette, and saved wallpaper set. Never changes anything and cannot confirm how the desktop looks.",
         _schema({})),
        ("power_status", "Read-only power overview: CPU governor, platform profile, battery, and whether a power-mode backend is installed. Reports only; it cannot change power modes.",
         _schema({})),
        ("plugin_status", "List this dotfiles checkout's optional widgets/plugins and whether each is enabled. Read-only.",
         _schema({})),
        ("display_status", "Report connected monitors and the fixed display helper's planned modes, positions and wallpaper choices. Read-only; not verified current display settings. Unavailable without a desktop session.",
         _schema({})),
        ("dotfiles_status", "Report the dotfiles repository branch, change metadata, and verified assistant Stow links. No file contents returned, no commits/pushes or network. Unavailable Git status is not a clean repository.",
         _schema({})),
        ("alerts_status", "Report current disk and RAM usage against the configured alert thresholds, which metrics are over them, and whether the alert watcher is running. Read-only; changes no thresholds and sends nothing.",
         _schema({})),
        ("processes", "Use only when process/app details are specifically requested. List the top N processes/apps by memory, names and memory only. Pass the requested N as limit; default 10 only if no count was requested. Cannot kill processes.",
         _schema({"limit": {"type": "integer", "minimum": 1, "maximum": 20,
                            "description": "The number of processes/apps requested by the user."}})),
    ]
    definitions = [item for item in definitions if item[0] not in STATUS_TOOLS or item[0] in config.status_enabled]
    if config.allowed_roots:
        root = {"type": "string", "enum": list(config.allowed_roots)}
        definitions.extend([
            ("find_files", "Recursively gather individual file sizes and names in an approved folder, largest first. Metadata only: name/size filters, no dates or contents. Sizes use mebibytes. Results are bounded samples, not a complete listing.",
              _schema({"root": root, "name_pattern": {"type": "string", "minLength": 1, "maxLength": 128,
                       "description": "Case-sensitive basename glob, not regex: *.zip or *.txt for an extension. Use literal unescaped *; do not add backslashes or use .txt alone."},
                      "min_size_mb": {"type": "integer", "minimum": 0, "maximum": 65536, "description": "Only if the user gave a minimum size."},
                      "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Only if the user gave a result count; otherwise omit."}}, ["root"])),
        ])
    roots = usage_roots(config)
    if roots:
        definitions.append(("directory_usage", "Measure a folder's real recursive size using live metadata, not a copied snapshot. Returns allocated disk bytes AND logical file bytes, human-readable sizes and scan completeness. Use for 'size of this directory' or '~/.dotfiles'. With one approved root, omit root. Protected/linked paths are excluded; incomplete totals are labelled. depth selects reported subdirectory levels, not scan recursion.",
                            _schema({"root": {"type": "string", "enum": list(roots)},
                                      "path": {"type": "string", "minLength": 1, "maxLength": 512, "default": ".",
                                              "description": "Omit to measure the root itself. Only for a named child folder, by relative name (never repeat root's basename)."},
                                     "depth": {"type": "integer", "minimum": 1, "maximum": 8},
                                     "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "Only if the user gave a count; otherwise omit."},
                                     "file_limit": {"type": "integer", "minimum": 0, "maximum": 20}},
                                    [] if len(roots) == 1 else ["root"])))
    if config.bash_enabled and config.bash_roots:
        definitions.append(("bash", "Restricted terminal commands in an explicitly approved content-readable folder. "
                            "Supply the complete command including every requested option, path and pipe stage. With one approved folder root is optional. Never substitute du for ls or drop head/counts. "
                            "ls/grep/rg/find/cat/head/tail/wc/sort/uniq/cut/df/pwd and pipes use filtered read-only snapshots. "
                            "Standalone du summaries use real recursive metadata, not snapshot blocks; directory_usage also measures folder sizes. "
                            "Your ~/ aliases work only inside the approved root. No glob/variable expansion or scripts. "
                            "Literal mkdir/touch/cp/mv/rm and echo/printf > or >> require enabled writes and human approval. "
                            "Protected paths, links, recursive deletion, network and unknown commands stay blocked.",
                            _schema({"root": {"type": "string", "enum": list(config.bash_roots)},
                                      "command": {"type": "string", "minLength": 1, "maxLength": 2048,
                                                  "description": "Exact audited syntax, preserving all stages. Never read .env*, auth.json, tokens.json or protected keys. du only supports -s/-h/-b/-k/--apparent-size; NOT --max-depth. Use directory_usage for size breakdowns."},
                                      "cwd": {"type": "string", "minLength": 1, "maxLength": 512, "default": ".",
                                             "description": "Literal folder within root; default '.'; no '..' or protected paths."}},
                                    ["command"] if len(config.bash_roots) == 1 else ["root", "command"])))
    if config.themes_enabled:
        available = themes.catalogue()
        definitions.append(("theme_status", "List available desktop layouts and color palettes, and their current selections. Read-only; no theme changes.", _schema({})))
        if config.actions_enabled:
            definitions.append(("set_theme", "Change the desktop layout, color palette, or both using existing names. At least one selection is required. Updates app configurations and may reload/restart desktop components; always asks human approval. No custom color-file editing.",
                                _schema({"layout": {"type": "string", "enum": available["layouts"]},
                                         "palette": {"type": "string", "enum": available["palettes"]}})))
            definitions.append(("apply_theme", "Re-render and reload the current color palette without selecting a different one. Updates app configurations and may reload/restart desktop components; always asks human approval. Takes no arguments; does not switch desktop layouts.",
                                _schema({})))
    if config.web_search_enabled:
        definitions.append(("web_search", "Search the web through the user's local SearXNG for current or public information not available on this machine. Returns titles, URLs and snippets; always asks human approval. Never put file contents, paths, secrets or personal data in the query.",
                            _schema({"query": {"type": "string", "minLength": 1, "maxLength": 256,
                                               "description": "Plain search terms only; no file contents, paths, secrets or personal data."},
                                     "limit": {"type": "integer", "minimum": 1, "maximum": 10,
                                               "description": "Only if the user gave a result count; otherwise omit."}}, ["query"])))
    if config.actions_enabled:
        for name, description in (("set_volume", "Request a volume percentage; always asks human approval."),
                                  ("set_brightness", "Request a brightness percentage; always asks human approval.")):
            definitions.append((name, description, _schema({"percent": {"type": "integer", "minimum": 0, "maximum": 100}}, ["percent"])))
        if config.apps:
            definitions.append(("launch_app", "Request launching one configured app; always asks human approval.",
                                _schema({"app": {"type": "string", "enum": [a for a, _ in config.apps]}}, ["app"])))
    return [{"type": "function", "function": {"name": n, "description": d, "parameters": s}} for n, d, s in definitions]


class Policy:
    def __init__(self, config: Config):
        self.config = config
        self.identities: dict[str, tuple[int, int]] = {}
        self.definitions = {t["function"]["name"]: t["function"]["parameters"] for t in tool_schemas(config)}

    def _validate(self, name: str, arguments: object) -> dict:
        if not isinstance(name, str) or name not in self.definitions:
            raise PolicyError("Unknown or disabled tool; nothing executed.")
        if not isinstance(arguments, dict) or any(not isinstance(k, str) for k in arguments):
            raise PolicyError("Tool arguments must be an object.")
        arguments = dict(arguments)
        roots = self.config.bash_roots if name == "bash" else usage_roots(self.config) if name == "directory_usage" else ()
        if roots:
            if "root" not in arguments and len(roots) == 1:
                arguments["root"] = roots[0]
            elif isinstance(arguments.get("root"), str):
                try:
                    arguments["root"] = normalized_root(arguments["root"])
                except ConfigurationError:
                    raise PolicyError("Folder must be an approved absolute path or your own ~/ alias.") from None
        schema = self.definitions[name]
        for key, value in arguments.items():
            rule = schema["properties"].get(key)
            if rule is None:
                continue
            if rule["type"] == "integer":
                valid = type(value) is int and rule["minimum"] <= value <= rule["maximum"]
            else:
                valid = (isinstance(value, str) and rule.get("minLength", 0) <= len(value) <= rule.get("maxLength", 4096)
                         and not any(unicodedata.category(c).startswith("C") for c in value)
                         and ("enum" not in rule or value in rule["enum"]))
            if not valid:
                raise PolicyError("Invalid tool argument; nothing executed.")
        if name == "web_search" and isinstance(arguments.get("query"), str) and arguments["query"].strip().lower().startswith("file:"):
            raise PolicyError("Invalid tool argument; nothing executed.")
        # A structural typo must not hide a known unsafe path/command/range and
        # turn a permission refusal into a correction attempt. These checks are
        # pure; no file/executable probing happens until the schema is complete.
        if name == "bash" and {"root", "command"} <= arguments.keys():
            bash.plan(self.config, {key: value for key, value in arguments.items() if key in schema["properties"]})
        if name == "directory_usage" and "root" in arguments:
            bash._relative(arguments["root"], ".", arguments.get("path", "."))
        if arguments.keys() - schema["properties"].keys() or set(schema["required"]) - arguments.keys():
            required = ", ".join(schema["required"]) or "none"
            allowed = ", ".join(schema["properties"]) or "none"
            raise ToolSchemaError(f"Unknown or missing tool argument for {name}; required: {required}; allowed: {allowed}. Nothing executed.")
        return dict(arguments)

    def prepare(self, name: str, arguments: object) -> PreparedCall:
        args = self._validate(name, arguments)
        if name == "bash":
            args, mutates, argv, verification = bash.prepare(self.config, args)
            return PreparedCall(name, tuple(sorted(args.items())), mutates, argv, verification)
        if name == "web_search":
            args.setdefault("limit", 5)
            return PreparedCall(name, tuple(sorted(args.items())), True, (), verification=self.config.web_search_host)
        if name == "processes":
            args.setdefault("limit", 10)
        if name == "find_files":
            args.setdefault("name_pattern", "*")
            args.setdefault("min_size_mb", 0)
            args.setdefault("limit", 20)
        if name == "directory_usage":
            args["path"] = bash._relative(args["root"], ".", args.get("path", "."))
            args.setdefault("depth", 1)
            args.setdefault("limit", 20)
            args.setdefault("file_limit", 0)
        argv: tuple[str, ...] = ()
        verification = ""
        if "root" in args:
            root = args["root"]
            fd = open_directory(root)
            try:
                identity = os.fstat(fd)
                current = (identity.st_dev, identity.st_ino)
                if root in self.identities and self.identities[root] != current:
                    raise PolicyError("Approved folder changed identity; restart and review the folder.")
                self.identities[root] = current
            finally:
                os.close(fd)
        if name == "directory_usage":
            fd = open_directory(args["root"])
            try:
                verification = filesystem.verification(fd, args["path"])
            finally:
                os.close(fd)
        elif name == "display_status":
            helper = status.REPOSITORY / "scripts/.local/bin/display-detect"
            verification = status.display_snapshot()
            if verification:
                argv = (str(helper), "list")
        elif name == "dotfiles_status":
            verification = status.git_snapshot()
            if verification:
                argv = status.git_argv()
        elif name == "apply_theme":
            themes.catalogue()
            argv, verification = (str(themes.THEME_ROOT / "themectl"), "apply"), themes.snapshot()
        elif name == "set_theme":
            argv, verification = themes.prepare(args)
        elif name == "theme_status":
            verification = themes.snapshot()
        elif name == "launch_app":
            executable = dict(self.config.apps)[args["app"]]
            try:
                resolved = Path(executable).resolve(strict=True)
                info = resolved.stat()
                if (not str(resolved).isascii() or len(str(resolved)) > 1024
                        or any(unicodedata.category(c).startswith("C") for c in str(resolved))
                        or info.st_uid != 0 or info.st_mode & 0o022 or not stat.S_ISREG(info.st_mode)
                        or not os.access(resolved, os.X_OK)):
                    raise OSError
                for parent in resolved.parents:
                    info = parent.stat()
                    if info.st_uid != 0 or info.st_mode & 0o022:
                        raise OSError
            except (OSError, ValueError, RuntimeError):
                raise PolicyError("Configured app must be an executable, root-owned, non-writable-by-others file.") from None
            argv = (str(resolved),)
        elif name == "set_volume":
            argv = ("/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{args['percent']}%")
        elif name == "set_brightness":
            argv = ("/usr/bin/brightnessctl", "set", f"{args['percent']}%")
        mutates = bool(argv) and name not in {"display_status", "dotfiles_status"}
        if mutates and not os.access(argv[0], os.X_OK):
            raise PolicyError("Required action utility is not installed or executable.")
        return PreparedCall(name, tuple(sorted(args.items())), mutates, argv, verification)

    def directory_usage(self, call: PreparedCall) -> dict:
        args = call.argument_dict()
        if call.name != "directory_usage" or args["root"] not in usage_roots(self.config):
            raise PolicyError("Folder is not approved for size metadata.")
        fd = open_directory(args["root"])
        try:
            info = os.fstat(fd)
            if (self.identities.get(args["root"]) != (info.st_dev, info.st_ino)
                    or filesystem.verification(fd, args["path"]) != call.verification):
                raise PolicyError("Approved folder changed identity; nothing scanned.")
            return filesystem.usage(fd, args["path"], self.config, depth=args["depth"],
                                    limit=args["limit"], file_limit=args["file_limit"])
        finally:
            os.close(fd)

    def scan(self, root: str) -> tuple[list[FileRecord], bool]:
        if root not in self.config.allowed_roots:
            raise PolicyError("Folder is not explicitly approved.")
        fd = open_directory(root)
        info = os.fstat(fd)
        if self.identities.get(root) != (info.st_dev, info.st_ino):
            os.close(fd)
            raise PolicyError("Approved folder changed identity; nothing scanned.")
        records: list[FileRecord] = []
        examined = 0
        truncated = False
        deadline = time.monotonic() + self.config.scan_seconds

        def walk(parent_fd: int, prefix: str, depth: int) -> None:
            nonlocal examined, truncated
            with os.scandir(parent_fd) as entries:
                for entry in entries:
                    examined += 1
                    if examined > self.config.scan_entries or time.monotonic() >= deadline:
                        truncated = True
                        return
                    if protected_name(entry.name):
                        continue
                    relative = f"{prefix}/{entry.name}" if prefix else entry.name
                    try:
                        metadata = entry.stat(follow_symlinks=False)
                        if stat.S_ISREG(metadata.st_mode):
                            records.append({"relative_path": relative, "name": entry.name, "size_bytes": metadata.st_size})
                        elif stat.S_ISDIR(metadata.st_mode):
                            if depth >= self.config.scan_depth:
                                truncated = True
                                continue
                            child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                            try:
                                walk(child, relative, depth + 1)
                            finally:
                                os.close(child)
                            if examined > self.config.scan_entries or time.monotonic() >= deadline:
                                return
                    except OSError:
                        truncated = True
        try:
            walk(fd, "", 0)
        except OSError:
            raise PolicyError("Cannot inspect the approved folder safely.") from None
        finally:
            os.close(fd)
        return records, truncated

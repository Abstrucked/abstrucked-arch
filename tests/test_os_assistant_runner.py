"""Execution is bounded and approvals are exact, per-call, and fail closed."""

from dataclasses import FrozenInstanceError
from pathlib import Path
import stat
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.config import Config
from os_assistant.contracts import AssistantError, PolicyError, PreparedCall
from os_assistant import status
from os_assistant.policy import Policy
from os_assistant.runner import Runner, action_environment, run_bounded
import os_assistant.runner as execution


@pytest.fixture
def disposable_checkout(monkeypatch, tmp_path):
    """A private Git checkout as REPOSITORY, so results never depend on the host's real clone.

    CI checkouts live under runner-owned, differently-permissioned directories that
    git_snapshot rightly rejects, and linked worktrees are rejected on purpose.
    """
    repo = tmp_path / "checkout"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    subprocess.run(("/usr/bin/git", "init", "--quiet", "--initial-branch=main", str(repo)), check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env=execution.git_environment())
    monkeypatch.setattr(status, "REPOSITORY", repo)
    return repo


@pytest.fixture
def display_dependencies(monkeypatch):
    """Limit the helper's trusted dependencies to coreutils-level tools present on any host.

    The real list names xrandr/column/awk (or hyprctl/jq), which a CI runner lacks.
    """
    monkeypatch.setattr(status, "display_dependencies", lambda: ["/bin/bash", "/usr/bin/sort"])


@pytest.fixture
def policy(monkeypatch):
    monkeypatch.setattr("os_assistant.policy.os.access", lambda *args: True)
    return Policy(Config(actions_enabled=True))


def test_dry_run_does_not_execute_or_request_approval(policy, monkeypatch):
    def forbidden(*args):
        pytest.fail("Dry run attempted execution or approval")
    monkeypatch.setattr(execution, "run_bounded", forbidden)
    runner = Runner(policy, dry_run=True, confirm=forbidden)
    result = runner.run(policy.prepare("set_volume", {"percent": 20}))
    assert result.status == "preview"
    assert result.data["argv"] == ["/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "20%"]


def test_denial_never_executes(policy, monkeypatch):
    monkeypatch.setattr(execution, "run_bounded", lambda *args: pytest.fail("Denied action executed"))
    assert Runner(policy).run(policy.prepare("set_volume", {"percent": 20})).status == "denied"


def test_each_action_needs_fresh_approval_and_exact_argv(policy, monkeypatch):
    approved, executed = [], []
    monkeypatch.setattr(execution, "run_bounded", lambda argv, timeout: executed.append(argv) or 0)
    runner = Runner(policy, confirm=lambda call: approved.append(call) or True)
    call = policy.prepare("set_volume", {"percent": 20})
    assert runner.run(call).status == "ok"
    assert runner.run(call).status == "ok"
    assert len(approved) == 2 and executed == [call.argv, call.argv]


def test_forged_call_cannot_bypass_validation(policy, monkeypatch):
    monkeypatch.setattr(execution, "run_bounded", lambda *args: pytest.fail("Forged action executed"))
    forged = PreparedCall("set_volume", (("percent", 20),), False, ("/bin/sh", "-c", "echo unexpected"))
    with pytest.raises(PolicyError):
        Runner(policy, confirm=lambda call: True).run(forged)


def test_prepared_args_are_an_immutable_snapshot(policy):
    source = {"percent": 20}
    call = policy.prepare("set_volume", source)
    source["percent"] = 100
    assert call.argument_dict()["percent"] == 20
    with pytest.raises(FrozenInstanceError):
        call.argv = ("/bin/sh",)


def test_readonly_dry_run_skips_collectors(monkeypatch):
    monkeypatch.setattr(execution.diagnostics, "collect_system_status", lambda: pytest.fail("Dry-run sampled metrics"))
    runner = Runner(Policy(Config()), dry_run=True)
    assert runner.run(runner.policy.prepare("system_status", {})).status == "preview"


def test_all_status_dry_runs_skip_collectors_helpers_and_confirmation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Status dry-run executed or requested confirmation")
    for name in ("collect_desktop_status", "collect_power_status", "collect_plugin_status"):
        monkeypatch.setattr(status, name, forbidden)
    monkeypatch.setattr(execution, "run_captured", forbidden)
    runner = Runner(Policy(Config()), dry_run=True, confirm=forbidden)
    for name in ("desktop_status", "power_status", "plugin_status", "display_status", "dotfiles_status"):
        call = runner.policy.prepare(name, {})
        assert not call.mutates and runner.run(call).status == "preview"


@pytest.mark.parametrize("code,stdout,stderr,expected", [
    (1, "", "private fixture error", None), (0, "x" * 8193, "", None),
    (0, "ok\n", "warning", None), (0, "ok\n", "", "ok\n"),
])
def test_read_only_output_is_bounded_and_discards_failed_or_warning_output(monkeypatch, code, stdout, stderr, expected):
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: (code, stdout, stderr))
    assert Runner(Policy(Config())).read_only_output(("/usr/bin/git",)) == expected


def test_display_status_freezes_and_uses_the_fixed_read_only_helper(monkeypatch, tmp_path, display_dependencies):
    repo = tmp_path / "checkout"
    helper = repo / "scripts/.local/bin/display-detect"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    monkeypatch.setattr(status, "REPOSITORY", repo)
    monkeypatch.setenv("DISPLAY", ":fixture")
    calls = []
    monkeypatch.setattr(execution, "run_captured", lambda argv, timeout, *, environment:
                        calls.append((argv, environment)) or (0, "eDP  1920  1080  60.01  internal  0  0  /w.png\n", ""))
    runner = Runner(Policy(Config()), confirm=lambda call: pytest.fail("Read-only helper required approval"))
    call = runner.policy.prepare("display_status", {})
    assert not call.mutates and call.argv == (str(helper), "list") and call.verification
    result = runner.run(call)
    assert result.data["monitors"][0]["width"] == 1920
    assert calls[0][0] == call.argv and calls[0][1]["DISPLAY"] == ":fixture"
    assert calls[0][1]["WALLPAPER_SET"] and "/usr/bin:/bin" == calls[0][1]["PATH"]


def test_display_helper_changes_invalidate_a_prepared_status_request(monkeypatch, tmp_path, display_dependencies):
    helper = tmp_path / "scripts/.local/bin/display-detect"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    monkeypatch.setattr(status, "REPOSITORY", tmp_path)
    runner = Runner(Policy(Config()))
    call = runner.policy.prepare("display_status", {})
    helper.write_text("changed fixture")
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("Changed helper executed"))
    with pytest.raises(PolicyError, match="changed"):
        runner.run(call)


def test_headless_display_status_never_executes_a_helper(monkeypatch):
    for name in ("DISPLAY", "WAYLAND_DISPLAY", "HYPRLAND_INSTANCE_SIGNATURE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("Headless helper executed"))
    monkeypatch.setattr(status, "display_wallpaper_set", lambda: pytest.fail("Headless status read wallpaper state"))
    runner = Runner(Policy(Config()))
    assert runner.run(runner.policy.prepare("display_status", {})).data["monitors"] == "unavailable"


def test_dotfiles_status_preflights_filters_and_uses_only_hardened_git_commands(monkeypatch, disposable_checkout):
    calls = []
    def capture(argv, timeout, *, environment):
        calls.append((argv, environment))
        if "config" in argv:
            return 1, "", ""
        return 0, "## main\0?? fixture.txt\0", ""
    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(Policy(Config()), confirm=lambda call: pytest.fail("Git status required approval"))
    call = runner.policy.prepare("dotfiles_status", {})
    result = runner.run(call)
    assert not call.mutates and call.verification and result.data["branch"] == "main"
    assert len(calls) == 2 and calls[1][0] == call.argv
    assert "--name-only" in calls[0][0] and "--no-optional-locks" in call.argv and "-z" in call.argv
    assert "--file" in calls[0][0] and "-C" not in calls[0][0]
    assert "core.fsmonitor=false" in call.argv and "--ignore-submodules=all" in call.argv
    assert "core.excludesFile=/dev/null" in call.argv and "--git-dir" in call.argv and "--work-tree" in call.argv
    assert calls[0][1]["GIT_CONFIG_GLOBAL"] == "/dev/null" and calls[1][1]["GIT_ALLOW_PROTOCOL"] == ""
    assert calls[1][1]["GIT_NO_LAZY_FETCH"] == "1"


@pytest.mark.parametrize("config_key", ["filter.fixture.clean", "include.path", "includeif.gitdir:fixture.path"])
def test_configured_git_filters_or_includes_block_status_before_they_can_run_or_be_read(monkeypatch, disposable_checkout, config_key):
    calls = []
    monkeypatch.setattr(execution, "run_captured", lambda argv, timeout, *, environment:
                        calls.append(argv) or (0, config_key + "\n", ""))
    runner = Runner(Policy(Config()))
    result = runner.run(runner.policy.prepare("dotfiles_status", {}))
    assert len(calls) == 1 and "config" in calls[0]
    assert "--no-includes" in calls[0] and "--name-only" in calls[0]
    assert not result.data["git_available"] and result.data["pending_changes"] is None
    assert config_key not in repr(result.data)


def test_status_allowlist_can_disable_individual_tools(tmp_path):
    from os_assistant.config import load_config
    path = tmp_path / "config.toml"
    path.write_text('[status]\nenabled = ["power_status"]\n')
    permissions = Policy(load_config(path))
    assert permissions.prepare("power_status", {}).name == "power_status"
    for name in ("desktop_status", "plugin_status", "display_status", "dotfiles_status"):
        with pytest.raises(PolicyError):
            permissions.prepare(name, {})


def test_actual_git_status_of_a_disposable_checkout_has_no_index_writes(tmp_path, monkeypatch):
    repo = tmp_path / "checkout"
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    subprocess.run(("/usr/bin/git", "init", "--quiet", "--initial-branch=main", str(repo)), check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env=execution.git_environment())
    (repo / "fixture.txt").write_text("fixture contents are not returned")
    # A configured worktree and excludes file must not redirect this curated check.
    outside = tmp_path / "not-authorized-tree"
    outside.mkdir()
    (outside / "private-fixture.txt").write_text("not authorized")
    with (repo / ".git/config").open("a") as stream:
        stream.write(f'[core]\n\tworktree = {outside}\n\texcludesFile = {outside}/private-fixture.txt\n')
    monkeypatch.setattr(status, "REPOSITORY", repo)
    runner = Runner(Policy(Config()))
    result = runner.run(runner.policy.prepare("dotfiles_status", {}))
    assert result.data["git_available"] and result.data["branch"] == "main"
    assert result.data["pending_changes"] == 1
    assert result.data["changes"] == [{"code": "??", "path": "fixture.txt"}]
    assert "fixture contents" not in repr(result.data)
    assert not (repo / ".git/index").exists() and not (repo / ".git/index.lock").exists()


def test_actual_git_config_preflight_never_follows_an_include_fifo(tmp_path, monkeypatch):
    import os
    repo = tmp_path / "checkout"
    subprocess.run(("/usr/bin/git", "init", "--quiet", str(repo)), check=True,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   env=execution.git_environment())
    private = tmp_path / "not-authorized-config"
    os.mkfifo(private)
    with (repo / ".git/config").open("a") as stream:
        stream.write(f'[include]\n\tpath = {private}\n')
    monkeypatch.setattr(status, "REPOSITORY", repo)
    calls = []
    actual_capture = execution.run_captured
    def capture(argv, timeout, *, environment):
        result = actual_capture(argv, timeout, environment=environment)
        calls.append((argv, result))
        return result
    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(Policy(Config(tool_timeout=1)))
    result = runner.run(runner.policy.prepare("dotfiles_status", {}))
    assert not result.data["git_available"] and result.data["pending_changes"] is None
    assert "not-authorized-config" not in repr(result.data)
    assert len(calls) == 1 and "--no-includes" in calls[0][0]
    assert "--file" in calls[0][0] and "-C" not in calls[0][0]
    assert calls[0][1] == (0, "include.path\n", "")


def test_recursive_size_views_use_bounded_live_metadata(tmp_path):
    root = tmp_path / "approved"
    (root / "a/b").mkdir(parents=True)
    (root / "a/b/large.txt").write_bytes(b"a" * 30)
    (root / "a/small.txt").write_bytes(b"b" * 10)
    (root / "direct.txt").write_bytes(b"c" * 5)
    (root / ".env").write_bytes(b"excluded fixture" * 100)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escaped.txt").write_bytes(b"d" * 100)
    (root / "escape").symlink_to(outside, target_is_directory=True)
    runner = Runner(Policy(Config(allowed_roots=(str(root),))))
    result = runner.run(runner.policy.prepare("directory_usage", {
        "root": str(root), "depth": 2, "file_limit": 2,
    }))
    assert result.status == "ok"
    assert result.data["total_size_bytes"] == 45 and result.data["files_scanned"] == 3
    assert result.data["directories"] == [
        {"name": "a", "size_bytes": 40, "files_scanned": 2,
         "allocated_size_bytes": sum((root / path).stat().st_blocks * 512 for path in ("a", "a/b", "a/b/large.txt", "a/small.txt"))},
        {"name": "a/b", "size_bytes": 30, "files_scanned": 1,
         "allocated_size_bytes": sum((root / path).stat().st_blocks * 512 for path in ("a/b", "a/b/large.txt"))},
        {"name": "(root files)", "size_bytes": 5, "files_scanned": 1,
         "allocated_size_bytes": (root / "direct.txt").stat().st_blocks * 512},
    ]
    assert result.data["files"] == [
        {"relative_path": "a/b/large.txt", "size_bytes": 30},
        {"relative_path": "a/small.txt", "size_bytes": 10},
    ]
    assert result.data["directory_totals_overlap"] and result.data["truncated_files"]
    assert result.data["sample_only"] and not result.data["truncated_scan"]
    assert "excluded fixture" not in repr(result.data) and "escaped.txt" not in repr(result.data)


@pytest.mark.parametrize("arguments", [
    {"depth": 0}, {"depth": 9}, {"depth": True}, {"depth": "2"},
    {"limit": 0}, {"limit": 21}, {"limit": True},
    {"file_limit": -1}, {"file_limit": 21}, {"file_limit": True}, {"file_limit": "2"},
])
def test_bad_recursive_size_options_rejected_before_open_or_scan(monkeypatch, tmp_path, arguments):
    monkeypatch.setattr("os_assistant.policy.open_directory", lambda *a: pytest.fail("Invalid option opened a folder"))
    permissions = Policy(Config(allowed_roots=(str(tmp_path),)))
    with pytest.raises(PolicyError):
        permissions.prepare("directory_usage", {"root": str(tmp_path), **arguments})


def test_recursive_size_dry_run_never_scans(tmp_path, monkeypatch):
    permissions = Policy(Config(allowed_roots=(str(tmp_path),)))
    monkeypatch.setattr(permissions, "scan", lambda *a: pytest.fail("Dry-run scanned files"))
    monkeypatch.setattr(permissions, "directory_usage", lambda *a: pytest.fail("Dry-run scanned usage"))
    runner = Runner(permissions, dry_run=True)
    assert runner.run(permissions.prepare("directory_usage", {
        "root": str(tmp_path), "depth": 8, "file_limit": 20,
    })).status == "preview"


def test_subprocess_environment_drops_loader_hooks_and_credentials(monkeypatch):
    monkeypatch.setenv("PRIVATE_API_TOKEN", "fixture-only")
    monkeypatch.setenv("LD_PRELOAD", "/fixture-do-not-load")
    monkeypatch.setenv("BASH_ENV", "/fixture-do-not-source")
    monkeypatch.setenv("PATH", "/fixture-hostile-bin")
    environment = action_environment()
    assert environment["PATH"] == "/usr/bin:/bin"
    assert not {"PRIVATE_API_TOKEN", "LD_PRELOAD", "BASH_ENV"} & environment.keys()
    assert environment["SYSTEMD_PAGER"] == "cat"


def test_bounded_utility_success():
    assert run_bounded((sys.executable, "-I", "-c", "print('fixture')"), 2) == 0


def test_bounded_utility_stops_oversized_output():
    with pytest.raises(AssistantError, match="output limit"):
        run_bounded((sys.executable, "-I", "-c", "print('x' * 10000)"), 2)


def test_bounded_utility_timeout_stops_own_process():
    with pytest.raises(AssistantError, match="timed out"):
        run_bounded((sys.executable, "-I", "-c", "import time; time.sleep(5)"), 1)


def test_approved_app_launch_is_fixed_nonblocking_and_not_claimed_visible(monkeypatch):
    path = Path("/usr/bin/fixture-browser")
    monkeypatch.setattr(Path, "resolve", lambda self, **kwargs: path)
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o755))
    monkeypatch.setattr("os_assistant.policy.os.access", lambda *args: True)
    policy = Policy(Config(actions_enabled=True, apps=(("browser", str(path)),)))
    child = Mock(pid=123, poll=Mock(return_value=None))
    start = Mock(return_value=child)
    monkeypatch.setattr(execution.subprocess, "Popen", start)
    runner = Runner(policy, confirm=lambda call: True)
    result = runner.run(policy.prepare("launch_app", {"app": "browser"}))
    assert result.status == "started" and result.data["pid"] == 123
    assert "not verified" in result.data["message"]
    args, options = start.call_args
    assert args == (("/usr/bin/fixture-browser",),)
    assert "shell" not in options
    assert options["stdin"] == subprocess.DEVNULL
    assert options["start_new_session"] is True and options["close_fds"] is True
    assert not child.wait.called


def test_closed_output_does_not_bypass_timeout():
    with pytest.raises(AssistantError, match="timed out"):
        run_bounded((sys.executable, "-I", "-c", "import os, time; os.close(1); os.close(2); time.sleep(5)"), 1)


def test_keyboard_interrupt_stops_spawned_utility(monkeypatch):
    real_start = subprocess.Popen
    children = []

    def start(*args, **kwargs):
        child = real_start(*args, **kwargs)
        children.append(child)
        return child

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(execution.subprocess, "Popen", start)
    monkeypatch.setattr(execution.selectors.DefaultSelector, "select", interrupt)
    with pytest.raises(KeyboardInterrupt):
        run_bounded((sys.executable, "-I", "-c", "import time; time.sleep(5)"), 2)
    assert len(children) == 1
    assert children[0].poll() is not None
    assert children[0].stdout.closed


@pytest.fixture
def web_policy():
    return Policy(Config(web_search_enabled=True))


def web_data():
    return {"executor": "searxng", "host": "http://127.0.0.1:8888", "query": "q", "results": [], "unresponsive_engines": 0}


def test_web_search_denied_makes_no_network_call(web_policy, monkeypatch):
    monkeypatch.setattr(execution.websearch, "search", lambda *args: pytest.fail("network call without approval"))
    result = Runner(web_policy, confirm=lambda call: False).run(web_policy.prepare("web_search", {"query": "q"}))
    assert result.status == "denied"


def test_web_search_default_confirm_denies(web_policy, monkeypatch):
    monkeypatch.setattr(execution.websearch, "search", lambda *args: pytest.fail("network call without approval"))
    assert Runner(web_policy).run(web_policy.prepare("web_search", {"query": "q"})).status == "denied"


def test_web_search_approved_runs_search_with_exact_arguments(web_policy, monkeypatch):
    seen = []
    monkeypatch.setattr(execution.websearch, "search", lambda config, query, limit: seen.append((config, query, limit)) or web_data())
    result = Runner(web_policy, confirm=lambda call: True).run(web_policy.prepare("web_search", {"query": "q", "limit": 3}))
    assert result.status == "ok" and result.data == web_data()
    assert seen == [(web_policy.config, "q", 3)]


def test_web_search_error_is_mapped(web_policy, monkeypatch):
    def fail(*args):
        raise AssistantError("Cannot reach local SearXNG.")
    monkeypatch.setattr(execution.websearch, "search", fail)
    result = Runner(web_policy, confirm=lambda call: True).run(web_policy.prepare("web_search", {"query": "q"}))
    assert (result.status, result.data) == ("error", {"message": "Cannot reach local SearXNG."})


def test_web_search_dry_run_previews_without_network(web_policy, monkeypatch):
    monkeypatch.setattr(execution.websearch, "search", lambda *args: pytest.fail("dry run searched"))
    result = Runner(web_policy, dry_run=True, confirm=lambda call: pytest.fail("dry run asked")).run(
        web_policy.prepare("web_search", {"query": "q"}))
    assert result.status == "preview" and result.data["arguments"] == {"query": "q", "limit": 5}


def test_web_search_revalidates_forged_call(web_policy, monkeypatch):
    monkeypatch.setattr(execution.websearch, "search", lambda *args: pytest.fail("forged call searched"))
    forged = PreparedCall("web_search", (("limit", 5), ("query", "x" * 300)), True, (), verification="http://127.0.0.1:8888")
    with pytest.raises(PolicyError):
        Runner(web_policy, confirm=lambda call: True).run(forged)
    stale = PreparedCall("web_search", (("limit", 5), ("query", "q")), True, (), verification="http://127.0.0.1:9999")
    with pytest.raises(PolicyError):
        Runner(web_policy, confirm=lambda call: True).run(stale)

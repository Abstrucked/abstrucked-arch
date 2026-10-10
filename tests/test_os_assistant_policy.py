"""Adversarial regression tests for os_assistant.policy (Policy / prepare / scan).

Tests exercise the real Policy, tool_schemas, open_directory and protected_name
implementation. All trees live in pytest temporary directories; HOME/XDG are
mocked. Execution predicates (os.access) and clocks are patched where tests
cover action tools, so no real wpctl/brightnessctl/app is ever invoked.
"""

import os
from dataclasses import FrozenInstanceError
from pathlib import Path
import stat
import sys

import pytest

_PKG = Path(__file__).resolve().parents[1] / "os-assistant" / ".local" / "share" / "os-assistant"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import os_assistant.policy as policy_module
import os_assistant.status as status_module
from os_assistant.config import Config
from os_assistant.contracts import FileRecord, PolicyError, PreparedCall
from os_assistant.policy import Policy, open_directory, protected_name, tool_schemas


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Mock HOME/XDG so no real user configuration can ever be consulted."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    return home


def make_root(tmp_path, name="root"):
    root = tmp_path / name
    root.mkdir()
    return root


class FakeOs:
    """Replacement for policy's os module: only the execution predicate runs."""

    X_OK = os.X_OK

    def __init__(self, result):
        self.result = result  # True, False, or "explode"
        self.calls = []

    def access(self, path, mode):
        self.calls.append((path, mode))
        if self.result == "explode":
            raise AssertionError("executable check must not run before argument validation")
        return self.result


class FakeClock:
    """Stops the scan time budget on the second monotonic() call."""

    def __init__(self):
        self.calls = 0

    def monotonic(self):
        self.calls += 1
        return 0.0 if self.calls == 1 else 1000.0


# ---------------------------------------------------------------------------
# Registered tool schemas
# ---------------------------------------------------------------------------

def test_schemas_default_register_read_only_tools():
    schemas = tool_schemas(Config())
    names = [s["function"]["name"] for s in schemas]
    assert names == ["system_status", "desktop_status", "power_status",
                     "plugin_status", "display_status", "dotfiles_status", "alerts_status", "processes"]


def test_every_schema_is_closed():
    cfg = Config(allowed_roots=("/srv/data",), actions_enabled=True,
                 apps=(("editor", "/usr/bin/editor"),))
    for schema in tool_schemas(cfg):
        params = schema["function"]["parameters"]
        assert params["additionalProperties"] is False
        assert params["type"] == "object"


def test_file_tools_require_allowed_roots():
    names = [s["function"]["name"] for s in tool_schemas(Config(allowed_roots=("/srv/data",)))]
    assert "find_files" in names
    assert "directory_usage" in names
    assert "set_volume" not in names


def test_action_tools_require_actions_enabled():
    names = [s["function"]["name"] for s in tool_schemas(Config(actions_enabled=True))]
    assert "set_volume" in names
    assert "set_brightness" in names
    assert "launch_app" not in names  # apps not configured
    with_apps = Config(actions_enabled=True, apps=(("editor", "/usr/bin/editor"),))
    assert "launch_app" in [s["function"]["name"] for s in tool_schemas(with_apps)]


def test_root_enum_matches_allowed_roots_exactly():
    cfg = Config(allowed_roots=("/srv/one", "/srv/two"))
    schemas = {s["function"]["name"]: s for s in tool_schemas(cfg)}
    root_rule = schemas["find_files"]["function"]["parameters"]["properties"]["root"]
    assert root_rule["enum"] == ["/srv/one", "/srv/two"]


# ---------------------------------------------------------------------------
# Zero-argument read-only status tools (registered by default, never mutating)
# ---------------------------------------------------------------------------

STATUS_TOOLS = ("system_status", "desktop_status", "power_status",
                "plugin_status", "display_status", "dotfiles_status")

# display_status/dotfiles_status carry frozen, trusted read-only argv and a
# verification snapshot; the remaining status tools carry neither.
SNAPSHOT_ARGV_TOOLS = ("display_status", "dotfiles_status")


def mock_status_trust(monkeypatch, display="d" * 64, git="g" * 64):
    """Fixed trusted snapshots: no real checkout metadata or helper probing."""
    monkeypatch.setattr(status_module, "display_snapshot", lambda: display)
    monkeypatch.setattr(status_module, "git_snapshot", lambda: git)


def forbid_status_snapshots(monkeypatch):
    monkeypatch.setattr(status_module, "display_snapshot",
                        lambda: pytest.fail("Helper trust probe ran before argument validation"))
    monkeypatch.setattr(status_module, "git_snapshot",
                        lambda: pytest.fail("Helper trust probe ran before argument validation"))


@pytest.mark.parametrize("name", STATUS_TOOLS)
def test_status_tools_prepare_read_only_with_no_arguments(name, monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    mock_status_trust(monkeypatch)
    call = Policy(Config()).prepare(name, {})
    assert call.mutates is False  # read-only even when a frozen argv is present
    assert call.argument_dict() == {}
    assert fake.calls == []  # no mutation-only utility availability checks
    if name not in SNAPSHOT_ARGV_TOOLS:
        assert call.argv == ()
        assert call.verification == ""


def test_display_status_argv_is_frozen_and_read_only(monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    mock_status_trust(monkeypatch)
    call = Policy(Config()).prepare("display_status", {})
    assert call.mutates is False
    assert call.verification == "d" * 64
    assert call.argv == (str(status_module.REPOSITORY / "scripts/.local/bin/display-detect"), "list")
    assert fake.calls == []


def test_dotfiles_status_argv_is_frozen_and_read_only(monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    mock_status_trust(monkeypatch)
    call = Policy(Config()).prepare("dotfiles_status", {})
    assert call.mutates is False
    assert call.verification == "g" * 64
    # Frozen exact argv: precisely the trusted git status request, nothing else.
    expected = ("/usr/bin/git", "--no-optional-locks", "--no-replace-objects",
                "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
                "-c", "core.hooksPath=/dev/null", "-c", "core.attributesFile=/dev/null",
                "-c", "core.excludesFile=/dev/null",
                "--git-dir", str(status_module.REPOSITORY / ".git"),
                "--work-tree", str(status_module.REPOSITORY), "-C", str(status_module.REPOSITORY),
                "status", "--porcelain=v1", "--branch", "--untracked-files=normal",
                "--ignore-submodules=all", "--no-renames", "-z")
    assert call.argv == status_module.git_argv() == expected
    assert call.argv[0] == "/usr/bin/git"
    assert "--no-optional-locks" in call.argv and "--no-replace-objects" in call.argv
    assert "status" in call.argv and "--porcelain=v1" in call.argv and "--branch" in call.argv
    assert "core.hooksPath=/dev/null" in call.argv and "core.fsmonitor=false" in call.argv
    assert str(status_module.REPOSITORY) in call.argv
    assert fake.calls == []


@pytest.mark.parametrize("name", SNAPSHOT_ARGV_TOOLS)
def test_status_tool_without_trusted_snapshot_stays_read_only(name, monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    mock_status_trust(monkeypatch, display="", git="")
    call = Policy(Config()).prepare(name, {})
    assert call.mutates is False
    assert call.argv == ()
    assert call.verification == ""
    assert fake.calls == []


@pytest.mark.parametrize("name", STATUS_TOOLS)
@pytest.mark.parametrize("args", [
    {"limit": 5}, {"root": "/srv/data"}, {"command": "apply"}, {"helper": "/bin/sh"},
    {"palette": "nord"}, {"app": "editor"}, {"percent": 50}, {"mutates": True},
    {"approved": True}, {"argv": ["/bin/sh"]},
])
def test_status_tools_reject_unknown_arguments(name, args, monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    forbid_status_snapshots(monkeypatch)
    with pytest.raises(PolicyError):
        Policy(Config()).prepare(name, args)
    assert fake.calls == []  # rejected before any executable probing


@pytest.mark.parametrize("name", STATUS_TOOLS)
@pytest.mark.parametrize("args", [None, [], "root=/srv", 42, 3.5, "x", {1: 2}])
def test_status_tools_reject_malformed_arguments(name, args, monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    forbid_status_snapshots(monkeypatch)
    with pytest.raises(PolicyError):
        Policy(Config()).prepare(name, args)
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Fail-closed validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["shell", "exec", "bash", "", "Find_Files", "system_status ", "run"])
def test_unknown_tools_rejected(name):
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare(name, {})


@pytest.mark.parametrize("name,args", [
    ("find_files", {"root": "/srv/data"}),
    ("directory_usage", {"root": "/srv/data"}),
    ("set_volume", {"percent": 10}),
    ("set_brightness", {"percent": 10}),
    ("launch_app", {"app": "editor"}),
])
def test_disabled_tools_rejected(name, args):
    policy = Policy(Config())  # no roots, no actions
    with pytest.raises(PolicyError):
        policy.prepare(name, args)


@pytest.mark.parametrize("args", [None, [], "root=/srv", 42, 3.5, "x"])
def test_arguments_must_be_object(args):
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare("processes", args)


def test_non_string_argument_keys_rejected():
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare("processes", {1: 2})


@pytest.mark.parametrize("args", [
    {"limit": 5, "extra": 1},
    {"limit": 5, "mutates": True},
    {"limit": 5, "argv": ["/bin/sh"]},
    {"limit": 5, "approved": True},
    {"limit": 5, "permissions": {"grant": "all"}},
])
def test_unknown_arguments_rejected(args):
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare("processes", args)


@pytest.mark.parametrize("name,args", [
    ("find_files", {}),
    ("find_files", {"name_pattern": "*"}),
    ("set_volume", {}),
    ("launch_app", {}),
])
def test_missing_required_arguments_rejected(name, args):
    root = "/srv/data"
    policy = Policy(Config(allowed_roots=(root,), actions_enabled=True,
                           apps=(("editor", "/usr/bin/editor"),)))
    with pytest.raises(PolicyError):
        policy.prepare(name, args)


@pytest.mark.parametrize("value", [True, False, 2.0, "10", None, [10], 10.0])
def test_integers_strictly_typed_excluding_bools(value):
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare("processes", {"limit": value})


@pytest.mark.parametrize("value", [0, -1, 21, 100, 10 ** 12])
def test_process_limit_out_of_range_rejected(value):
    policy = Policy(Config())
    with pytest.raises(PolicyError):
        policy.prepare("processes", {"limit": value})


def test_find_files_arguments_strict(tmp_path):
    root = str(make_root(tmp_path))
    policy = Policy(Config(allowed_roots=(root,), ))
    for args in (
        {"root": root, "min_size_mb": True},
        {"root": root, "min_size_mb": -1},
        {"root": root, "min_size_mb": 65537},
        {"root": root, "limit": 21},
        {"root": root, "limit": 0},
        {"root": root, "limit": True},
        {"root": root, "name_pattern": "x" * 129},
        {"root": root, "name_pattern": ""},
        {"root": root, "name_pattern": "bad\x00pat"},
        {"root": root, "name_pattern": "bad\npat"},
        {"root": root, "name_pattern": 5},
    ):
        with pytest.raises(PolicyError):
            policy.prepare("find_files", args)


def test_root_must_match_approved_enum_exactly(tmp_path):
    approved = make_root(tmp_path, "approved")
    other = make_root(tmp_path, "other")
    policy = Policy(Config(allowed_roots=(str(approved),)))
    for value in ("/etc", "/", str(other),
                  f"{approved}/sub", Path(str(approved)), {"path": str(approved)}):
        with pytest.raises(PolicyError):
            policy.prepare("directory_usage", {"root": value})
    for value in (f"{approved}/", f"{approved}//"):
        assert policy.prepare("directory_usage", {"root": value}).argument_dict()["root"] == str(approved)


def test_model_permission_hints_do_not_grant_access(tmp_path):
    approved = make_root(tmp_path, "approved")
    policy = Policy(Config(allowed_roots=(str(approved),)))
    hint_attempts = [
        {"root": "/", "granted_by_model": True},
        {"root": "/etc", "permissions": {"grant": "read"}},
        {"root": str(approved), "argv": ["/bin/sh", "-c", "id"]},
        {"root": str(approved), "mutates": True},
        {"tool": "find_files", "root": str(approved)},
    ]
    for args in hint_attempts:
        with pytest.raises(PolicyError):
            policy.prepare("directory_usage", args)


def test_direct_config_cannot_bypass_path_policy(tmp_path):
    # Even a hand-built Config cannot make prepare open '..' or control-char paths.
    for root in ("/tmp/x/../y", "relative/dir", "/tmp/bad\nname"):
        policy = Policy(Config(allowed_roots=(root,)))
        with pytest.raises(PolicyError):
            policy.prepare("directory_usage", {"root": root})


# ---------------------------------------------------------------------------
# Deterministic default arguments and frozen PreparedCall
# ---------------------------------------------------------------------------

def test_prepare_fills_deterministic_defaults(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    proc = policy.prepare("processes", {})
    assert proc.argument_dict() == {"limit": 10}
    found = policy.prepare("find_files", {"root": str(root)})
    assert found.argument_dict() == {
        "root": str(root), "name_pattern": "*", "min_size_mb": 0, "limit": 20,
    }
    status = policy.prepare("system_status", {})
    assert status.argument_dict() == {}
    assert status.mutates is False
    assert status.argv == ()
    usage = policy.prepare("directory_usage", {"root": str(root)})
    assert usage.argument_dict() == {"root": str(root), "path": ".", "depth": 1, "limit": 20, "file_limit": 0}


def test_defaults_not_poisoned_by_previous_calls(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    policy.prepare("processes", {"limit": 3})
    assert policy.prepare("processes", {}).argument_dict() == {"limit": 10}
    policy.prepare("find_files", {"root": str(root), "limit": 5})
    assert policy.prepare("find_files", {"root": str(root)}).argument_dict()["limit"] == 20
    policy.prepare("directory_usage", {"root": str(root), "depth": 2, "limit": 1, "file_limit": 3})
    assert policy.prepare("directory_usage", {"root": str(root)}).argument_dict() == {
        "root": str(root), "path": ".", "depth": 1, "limit": 20, "file_limit": 0,
    }


def test_prepare_is_deterministic_across_instances(tmp_path):
    root = make_root(tmp_path)
    cfg = Config(allowed_roots=(str(root),))
    first = Policy(cfg).prepare("find_files", {"root": str(root)})
    second = Policy(cfg).prepare("find_files", {"root": str(root)})
    assert first == second
    assert first.arguments == tuple(sorted(first.argument_dict().items()))


def test_prepared_call_is_frozen(tmp_path):
    root = make_root(tmp_path)
    call = Policy(Config(allowed_roots=(str(root),))).prepare("find_files", {"root": str(root)})
    with pytest.raises(FrozenInstanceError):
        call.name = "launch_app"
    with pytest.raises(FrozenInstanceError):
        call.argv = ("/bin/sh",)
    with pytest.raises(FrozenInstanceError):
        call.mutates = True


# ---------------------------------------------------------------------------
# Root identity: prepare captures, scan requires and rechecks
# ---------------------------------------------------------------------------

def test_prepare_records_root_identity(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    policy.prepare("directory_usage", {"root": str(root)})
    info = os.stat(root)
    assert policy.identities[str(root)] == (info.st_dev, info.st_ino)


def test_scan_requires_prepared_identity(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    with pytest.raises(PolicyError):
        policy.scan(str(root))


def test_scan_rejects_unprepared_sibling_root(tmp_path):
    root_a = make_root(tmp_path, "a")
    root_b = make_root(tmp_path, "b")
    policy = Policy(Config(allowed_roots=(str(root_a), str(root_b))))
    policy.prepare("directory_usage", {"root": str(root_a)})
    with pytest.raises(PolicyError):
        policy.scan(str(root_b))


def test_scan_rejects_replaced_root(tmp_path):
    root = make_root(tmp_path)
    (root / "file.txt").write_bytes(b"x")
    policy = Policy(Config(allowed_roots=(str(root),)))
    policy.prepare("find_files", {"root": str(root)})
    os.rename(root, tmp_path / "root.old")
    root.mkdir()  # same path, new inode
    with pytest.raises(PolicyError):
        policy.scan(str(root))


def test_prepare_rejects_replaced_root(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    policy.prepare("directory_usage", {"root": str(root)})
    os.rename(root, tmp_path / "root.old")
    root.mkdir()
    with pytest.raises(PolicyError):
        policy.prepare("directory_usage", {"root": str(root)})


def test_scan_requires_exact_approved_root_string(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=(str(root),)))
    policy.prepare("directory_usage", {"root": str(root)})
    with pytest.raises(PolicyError):
        policy.scan(f"{root}/")


# ---------------------------------------------------------------------------
# open_directory: fd-based, O_NOFOLLOW, protected components
# ---------------------------------------------------------------------------

def test_open_directory_returns_directory_fd(tmp_path):
    root = make_root(tmp_path)
    fd = open_directory(str(root))
    try:
        assert stat.S_ISDIR(os.fstat(fd).st_mode)
    finally:
        os.close(fd)


@pytest.mark.parametrize("path", ["relative/dir", "/a/../b", "", "/tmp/x/.."])
def test_open_directory_rejects_relative_and_traversal(path):
    with pytest.raises(PolicyError):
        open_directory(path)


def test_open_directory_rejects_protected_components(tmp_path):
    # Intended denial fixtures: '.config' appears only in this test.
    secret_dir = tmp_path / ".ssh"
    secret_dir.mkdir()
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    for path in (secret_dir, config_dir, secret_dir / "keys", tmp_path / "secrets" / "x"):
        with pytest.raises(PolicyError):
            open_directory(str(path))


def test_open_directory_rejects_symlink_components(tmp_path):
    real = make_root(tmp_path, "real")
    (real / "sub").mkdir()
    link = tmp_path / "link"
    os.symlink(real, link)
    with pytest.raises(PolicyError):
        open_directory(str(link))            # symlink as final component
    with pytest.raises(PolicyError):
        open_directory(str(link / "sub"))    # symlink mid-path


def test_open_directory_rejects_missing_and_non_directory(tmp_path):
    with pytest.raises(PolicyError):
        open_directory(str(tmp_path / "missing"))
    plain = tmp_path / "plain.txt"
    plain.write_bytes(b"x")
    with pytest.raises(PolicyError):
        open_directory(str(plain))


def test_open_directory_rejects_control_character_components(tmp_path):
    with pytest.raises(PolicyError):
        open_directory(str(tmp_path / "bad\nname"))


# ---------------------------------------------------------------------------
# protected_name
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    ".ssh", ".SSH", ".gnupg", ".aws", ".azure", ".kube", ".password-store",
    ".config", ".git", "secrets", "Secrets", "credentials", "Credentials",
    ".env", ".env.local", "server.pem", "tls.key", "bundle.p12",
    "id_rsa", "id_rsa.pub", "id_ed25519", "bad\x01name", "weird\u200dname",
    "id_ecdsa", "id_dsa", "credentials.json", "secrets.txt", "session.token",
    ".netrc", ".npmrc", ".pypirc", ".git-credentials",
])
def test_protected_names_detected(name):
    assert protected_name(name) is True


@pytest.mark.parametrize("name", [
    "notes.md", "config.yml", "image.png", "report.pdf", "Public", "music",
])
def test_benign_names_allowed(name):
    assert protected_name(name) is False


def test_root_owned_app_under_writable_parent_is_denied(monkeypatch):
    from types import SimpleNamespace
    path = Path("/tmp/fixture-app")
    monkeypatch.setattr(Path, "resolve", lambda self, **kwargs: path)
    monkeypatch.setattr(Path, "stat", lambda self: SimpleNamespace(
        st_uid=0, st_mode=(stat.S_IFDIR | 0o1777) if self == Path("/tmp") else (stat.S_IFREG | 0o755)))
    monkeypatch.setattr(policy_module.os, "access", lambda *args: True)
    policy = Policy(Config(actions_enabled=True, apps=(("app", str(path)),)))
    with pytest.raises(PolicyError):
        policy.prepare("launch_app", {"app": "app"})


# ---------------------------------------------------------------------------
# scan: metadata-only records, skips, and bounds
# ---------------------------------------------------------------------------

def prepared_policy(config, root):
    policy = Policy(config)
    policy.prepare("directory_usage", {"root": str(root)})
    return policy


def test_scan_returns_metadata_only_records(tmp_path):
    root = make_root(tmp_path)
    (root / "file.txt").write_bytes(b"hello world")  # 11 bytes
    (root / "sub").mkdir()
    (root / "sub" / "inner.txt").write_bytes(b"abc")
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    records, truncated = policy.scan(str(root))
    assert truncated is False
    for record in records:
        assert set(record) == {"relative_path", "name", "size_bytes"}
        assert isinstance(record["relative_path"], str)
        assert isinstance(record["name"], str)
        assert type(record["size_bytes"]) is int
    by_name = {r["name"]: r for r in records}
    assert by_name["file.txt"]["relative_path"] == "file.txt"
    assert by_name["file.txt"]["size_bytes"] == 11
    assert by_name["inner.txt"]["relative_path"] == "sub/inner.txt"
    assert by_name["inner.txt"]["size_bytes"] == 3


def test_scan_skips_symlinks(tmp_path):
    root = make_root(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_bytes(b"s" * 100)
    (root / "real.txt").write_bytes(b"ok")
    os.symlink(outside / "secret.txt", root / "filelink")   # symlink to file
    os.symlink(outside, root / "dirlink")                   # symlink to dir
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    records, _ = policy.scan(str(root))
    names = {r["name"] for r in records}
    assert names == {"real.txt"}
    assert all("secret" not in r["relative_path"] for r in records)


def test_scan_skips_protected_names(tmp_path):
    root = make_root(tmp_path)
    (root / "keep.txt").write_bytes(b"keep")
    (root / "credentials").write_bytes(b"leak")
    (root / "server.pem").write_bytes(b"leak")
    (root / "id_rsa").write_bytes(b"leak")
    (root / ".env.local").write_bytes(b"leak")
    (root / ".ssh").mkdir()
    (root / ".ssh" / "inner.txt").write_bytes(b"leak")
    (root / ".git").mkdir()
    (root / ".git" / "config").write_bytes(b"leak")
    (root / "secrets").mkdir()
    (root / "secrets" / "key.txt").write_bytes(b"leak")
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    records, _ = policy.scan(str(root))
    assert {r["name"] for r in records} == {"keep.txt"}
    joined = " ".join(r["relative_path"] for r in records)
    assert "ssh" not in joined and "secret" not in joined


def test_scan_never_opens_special_files(tmp_path):
    root = make_root(tmp_path)
    (root / "keep.txt").write_bytes(b"keep")
    os.mkfifo(root / "pipe")  # would block forever if opened
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    records, _ = policy.scan(str(root))
    assert {r["name"] for r in records} == {"keep.txt"}


def test_scan_entry_budget_truncates(tmp_path):
    root = make_root(tmp_path)
    for i in range(5):
        (root / f"f{i}.txt").write_bytes(b"x")
    policy = prepared_policy(Config(allowed_roots=(str(root),), scan_entries=2), root)
    records, truncated = policy.scan(str(root))
    assert truncated is True
    assert len(records) <= 2


def test_scan_depth_budget_truncates(tmp_path):
    root = make_root(tmp_path)
    (root / "top.txt").write_bytes(b"x")
    deep = root / "a" / "b"
    deep.mkdir(parents=True)
    (deep / "deep.txt").write_bytes(b"x")
    policy = prepared_policy(Config(allowed_roots=(str(root),), scan_depth=1), root)
    records, truncated = policy.scan(str(root))
    assert truncated is True
    assert {r["name"] for r in records} == {"top.txt"}


def test_scan_time_budget_truncates(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    for i in range(3):
        (root / f"f{i}.txt").write_bytes(b"x")
    policy = prepared_policy(
        Config(allowed_roots=(str(root),), scan_entries=100, scan_seconds=1), root)
    monkeypatch.setattr(policy_module, "time", FakeClock())
    records, truncated = policy.scan(str(root))
    assert truncated is True
    assert records == []


def test_scan_empty_directory_returns_no_truncation(tmp_path):
    root = make_root(tmp_path)
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    assert policy.scan(str(root)) == ([], False)


def test_scan_is_deterministic(tmp_path):
    root = make_root(tmp_path)
    (root / "a.txt").write_bytes(b"a")
    (root / "sub").mkdir()
    (root / "sub" / "b.txt").write_bytes(b"bb")
    policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
    first = sorted(policy.scan(str(root))[0], key=lambda r: r["relative_path"])
    second = sorted(policy.scan(str(root))[0], key=lambda r: r["relative_path"])
    assert first == second


@pytest.mark.skipif(os.geteuid() == 0, reason="permission bits are ignored for root")
def test_scan_unreadable_subdir_is_bounded_not_fatal(tmp_path):
    root = make_root(tmp_path)
    (root / "keep.txt").write_bytes(b"keep")
    locked = root / "locked"
    locked.mkdir()
    locked.chmod(0)
    try:
        policy = prepared_policy(Config(allowed_roots=(str(root),)), root)
        records, truncated = policy.scan(str(root))
    finally:
        locked.chmod(0o755)
    assert truncated is True
    assert {r["name"] for r in records} == {"keep.txt"}


def test_scan_rejects_unapproved_root(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config(allowed_roots=()))
    with pytest.raises(PolicyError):
        policy.scan(str(root))


# ---------------------------------------------------------------------------
# Action tools: strict percent, no execution before validation, fixed argv
# ---------------------------------------------------------------------------

def action_config():
    return Config(actions_enabled=True)


@pytest.mark.parametrize("name,args", [
    ("set_volume", {"percent": 101}),
    ("set_volume", {"percent": -1}),
    ("set_volume", {"percent": True}),
    ("set_volume", {"percent": "50"}),
    ("set_volume", {"percent": 1000}),
    ("set_volume", {"percent": 50.0}),
    ("set_brightness", {"percent": 101}),
    ("set_brightness", {"percent": -5}),
    ("set_brightness", {"percent": False}),
])
def test_action_percent_rejected_before_executable_check(name, args, monkeypatch):
    fake = FakeOs("explode")
    monkeypatch.setattr(policy_module, "os", fake)
    with pytest.raises(PolicyError):
        Policy(action_config()).prepare(name, args)
    assert fake.calls == []  # validation failed before any executable probing


@pytest.mark.parametrize("name", ["set_volume", "set_brightness"])
def test_action_utility_missing_fails_closed(name, monkeypatch):
    fake = FakeOs(False)
    monkeypatch.setattr(policy_module, "os", fake)
    with pytest.raises(PolicyError):
        Policy(action_config()).prepare(name, {"percent": 50})
    assert fake.calls  # probed, and refused


@pytest.mark.parametrize("name,args,expected_argv", [
    ("set_volume", {"percent": 50},
     ("/usr/bin/wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "50%")),
    ("set_brightness", {"percent": 37},
     ("/usr/bin/brightnessctl", "set", "37%")),
])
def test_prepared_action_argv_is_fixed(name, args, expected_argv, monkeypatch):
    fake = FakeOs(True)
    monkeypatch.setattr(policy_module, "os", fake)
    call = Policy(action_config()).prepare(name, args)
    assert call.mutates is True
    assert call.argv == expected_argv  # fixed argv, no shell interpolation


def test_action_boundaries_accepted(monkeypatch):
    fake = FakeOs(True)
    monkeypatch.setattr(policy_module, "os", fake)
    policy = Policy(action_config())
    assert policy.prepare("set_volume", {"percent": 0}).argv[-1] == "0%"
    assert policy.prepare("set_volume", {"percent": 100}).argv[-1] == "100%"


# ---------------------------------------------------------------------------
# launch_app: executable hygiene (never launched here)
# ---------------------------------------------------------------------------

def app_config(tmp_path, name="app", mode=0o755):
    exe = tmp_path / "bin" / name
    exe.parent.mkdir(exist_ok=True)
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(mode)
    return Config(actions_enabled=True, apps=((name, str(exe)),))


@pytest.mark.skipif(os.geteuid() == 0, reason="tmp files are root-owned when running as root")
def test_launch_app_rejects_non_root_owned(tmp_path):
    policy = Policy(app_config(tmp_path))
    with pytest.raises(PolicyError):
        policy.prepare("launch_app", {"app": "app"})


@pytest.mark.parametrize("mutate", ["missing", "not_executable", "directory"])
def test_launch_app_rejects_bad_executables(tmp_path, mutate):
    cfg = app_config(tmp_path)
    exe = Path(dict(cfg.apps)["app"])
    if mutate == "missing":
        exe.unlink()
    elif mutate == "not_executable":
        exe.chmod(0o644)
    else:
        exe.unlink()
        exe.mkdir()
    policy = Policy(cfg)
    with pytest.raises(PolicyError):
        policy.prepare("launch_app", {"app": "app"})


def test_launch_app_rejects_unknown_alias(tmp_path):
    policy = Policy(app_config(tmp_path))
    for app in ("bash", "/usr/bin/sh", "", "app "):
        with pytest.raises(PolicyError):
            policy.prepare("launch_app", {"app": app})


# ---------------------------------------------------------------------------
# Empty permissions: nothing granted
# ---------------------------------------------------------------------------

def test_empty_configuration_grants_nothing(tmp_path):
    root = make_root(tmp_path)
    policy = Policy(Config())
    for name, args in (
        ("find_files", {"root": str(root)}),
        ("directory_usage", {"root": str(root)}),
        ("set_volume", {"percent": 10}),
        ("set_brightness", {"percent": 10}),
        ("launch_app", {"app": "app"}),
    ):
        with pytest.raises(PolicyError):
            policy.prepare(name, args)
    with pytest.raises(PolicyError):
        policy.scan(str(root))


def test_policy_error_exit_code():
    assert PolicyError.exit_code == 3
    assert issubclass(PolicyError, Exception)
    assert issubclass(PreparedCall, object)
    assert FileRecord.__annotations__.keys() == {"relative_path", "name", "size_bytes", "allocated_size_bytes"}
    assert FileRecord.__optional_keys__ == {"allocated_size_bytes"}


def web_names(config):
    return [t["function"]["name"] for t in tool_schemas(config)]


def test_web_search_schema_absent_when_disabled():
    assert "web_search" not in web_names(Config())


def test_web_search_schema_present_and_closed_when_enabled():
    schema = next(t["function"] for t in tool_schemas(Config(web_search_enabled=True)) if t["function"]["name"] == "web_search")
    parameters = schema["parameters"]
    assert parameters["additionalProperties"] is False
    assert parameters["required"] == ["query"]
    assert set(parameters["properties"]) == {"query", "limit"}


@pytest.mark.parametrize("arguments", [
    {}, {"query": ""}, {"query": "x" * 257}, {"query": "a\nb"}, {"query": "a\tb"}, {"query": "file:///etc/passwd"},
    {"query": "ok", "limit": 0}, {"query": "ok", "limit": 11}, {"query": "ok", "limit": True}, {"query": "ok", "extra": 1},
])
def test_web_search_rejects_invalid_arguments(arguments):
    with pytest.raises(PolicyError):
        Policy(Config(web_search_enabled=True)).prepare("web_search", arguments)


def test_web_search_prepare_is_mutating_without_argv_and_defaults_limit():
    call = Policy(Config(web_search_enabled=True)).prepare("web_search", {"query": "arch linux news"})
    assert call.mutates is True and call.argv == ()
    assert call.verification == "http://127.0.0.1:8888"
    assert call.argument_dict() == {"query": "arch linux news", "limit": 5}


def test_web_search_disabled_is_unknown_tool():
    with pytest.raises(PolicyError):
        Policy(Config()).prepare("web_search", {"query": "x"})

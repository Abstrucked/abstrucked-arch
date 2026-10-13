"""Real-filesystem usage tests stay inside disposable approved roots."""

from dataclasses import replace
import os
from pathlib import Path
import stat
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import bash, filesystem
from os_assistant.config import Config
from os_assistant.contracts import PolicyError
from os_assistant.policy import Policy
from os_assistant.runner import Runner


def config(*, roots=(), bash_roots=(), **values):
    return replace(Config(), allowed_roots=tuple(map(str, roots)),
                   bash_roots=tuple(map(str, bash_roots)),
                   bash_enabled=bool(bash_roots), **values)


def usage(policy, root, **args):
    return Runner(policy).run(policy.prepare("directory_usage", {"root": str(root), **args}))


def test_real_usage_counts_allocated_and_logical_sizes_beyond_snapshot_cap(tmp_path):
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    sparse = root / "sparse.bin"
    with sparse.open("wb") as stream:
        stream.seek(2 * 1024 * 1024)
        stream.write(b"x")
    (root / "nested" / "payload.bin").write_bytes(b"p" * (1024 * 1024 + 31))
    expected_logical = sparse.stat().st_size + (root / "nested/payload.bin").stat().st_size
    expected_allocated = sum(path.stat().st_blocks * 512 for path in
                             (sparse, root / "nested/payload.bin", root, root / "nested"))

    result = usage(Policy(config(roots=(root,))), root).data

    assert result["total_size_bytes"] == expected_logical
    assert result["allocated_size_bytes"] == expected_allocated
    assert result["metadata_kind"] == "live_host_metadata_not_snapshot"
    assert not result["contents_read"] and not result["snapshot_only"]
    assert result["scan_complete"] and not result["truncated_scan"]


def test_usage_defaults_to_sole_root_and_scopes_subfolder_recursively(tmp_path):
    root = tmp_path / "approved"
    (root / "sub" / "deep").mkdir(parents=True)
    (root / "top").write_bytes(b"top")
    (root / "sub" / "middle").write_bytes(b"middle")
    (root / "sub" / "deep" / "leaf").write_bytes(b"leaf")
    policy = Policy(config(roots=(root,)))

    default_call = policy.prepare("directory_usage", {})
    assert default_call.argument_dict() == {
        "root": str(root), "path": ".", "depth": 1, "limit": 20, "file_limit": 0,
    }
    assert Runner(policy).run(default_call).data["total_size_bytes"] == 3 + 6 + 4
    scoped = usage(policy, root, path="sub").data
    assert scoped["total_size_bytes"] == 6 + 4
    assert scoped["files_scanned"] == 2


def test_multiple_usage_roots_require_explicit_root_and_include_bash_roots(tmp_path):
    metadata = tmp_path / "metadata"
    bash_root = tmp_path / "bash-only"
    metadata.mkdir()
    bash_root.mkdir()
    (bash_root / "fixture").write_bytes(b"x" * 7)
    policy = Policy(config(roots=(metadata,), bash_roots=(bash_root,)))
    with pytest.raises(PolicyError):
        policy.prepare("directory_usage", {})
    assert "directory_usage" in policy.definitions
    result = usage(policy, bash_root).data
    assert result["total_size_bytes"] == 7
    # Metadata registration does not grant content-reading Bash.
    with pytest.raises(PolicyError):
        policy.prepare("bash", {"root": str(metadata), "command": "cat fixture"})


def test_directory_usage_matches_gnu_du_allocated_and_apparent_totals(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir()
    (root / "one").write_bytes(b"a" * 139)
    (root / "two").write_bytes(b"b" * 4097)
    policy = Policy(config(roots=(root,)))
    data = usage(policy, root).data

    allocated = subprocess.run(["/usr/bin/du", "-s", "-B1", str(root)], check=True,
                               capture_output=True, text=True)
    apparent = subprocess.run(["/usr/bin/du", "-sb", str(root)], check=True,
                              capture_output=True, text=True)
    assert data["allocated_size_bytes"] == int(allocated.stdout.split()[0])
    assert data["total_size_bytes"] == int(apparent.stdout.split()[0])


def test_protected_links_special_and_large_files_are_filtered_without_content_reads(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    secret = root / ".env"
    secret.write_bytes(b"do not inspect" * 100)
    large = root / "large.dat"
    large.write_bytes(b"z" * (2 * 1024 * 1024))
    linked = root / "linked.dat"
    linked.write_bytes(b"h" * 100)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escaped").write_bytes(b"outside")
    (root / "link").symlink_to(outside, target_is_directory=True)
    (root / "file-link").symlink_to(large)
    os.link(linked, root / "hardlink-alias")
    os.mkfifo(root / "pipe")
    original_open = os.open
    opened = []

    def tracked_open(path, flags, *args, **kwargs):
        if path in {".env", "link", "file-link", "hardlink-alias", "pipe", "large.dat"}:
            opened.append((path, flags))
            if path == "large.dat":
                assert flags & getattr(os, "O_PATH", 0)
                assert not flags & os.O_RDONLY
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", tracked_open)
    data = usage(Policy(config(roots=(root,))), root).data

    assert data["total_size_bytes"] == large.stat().st_size
    assert data["files_scanned"] == 1
    assert data["excluded_entries"] >= 5
    assert data["contents_read"] is False
    assert data["excludes"] == "protected paths, symlinks, hardlinks, special files and nested mounts"
    assert ".env" not in repr(data) and "escaped" not in repr(data)
    assert all(name not in {".env", "link", "file-link", "hardlink-alias", "pipe"}
               for name, _ in opened)


def test_usage_reports_exclusions_and_incomplete_entry_depth_and_time_budgets(tmp_path, monkeypatch):
    root = tmp_path / "root"
    (root / "child").mkdir(parents=True)
    for index in range(8):
        (root / f"file-{index}").write_bytes(b"x")
    (root / "child" / "deep-file").write_bytes(b"y")

    limited = Policy(config(roots=(root,), usage_entries=2, scan_entries=1,
                            scan_depth=1, scan_seconds=0.001))
    data = usage(limited, root).data
    assert data["truncated_scan"] and not data["scan_complete"]
    assert "Incomplete scan" in data["summary"]
    assert data["entries_examined"] == 2

    (root / "child" / "grandchild").mkdir()
    depth_limited = Policy(config(roots=(root,), usage_depth=1))
    depth_data = usage(depth_limited, root).data
    assert depth_data["truncated_scan"] and "Incomplete scan" in depth_data["summary"]

    clock = iter((0, 0, 0, 2, 2, 2, 2))
    monkeypatch.setattr(filesystem.time, "monotonic", lambda: next(clock, 2))
    timed = usage(Policy(config(roots=(root,), usage_seconds=1)), root).data
    assert timed["truncated_scan"] and not timed["scan_complete"]


def test_usage_is_independent_of_tiny_snapshot_budgets(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "large").write_bytes(b"x" * (2 * 1024 * 1024))
    policy = Policy(config(roots=(root,), scan_entries=1, scan_depth=1,
                           scan_seconds=0.001))
    data = usage(policy, root).data
    assert data["total_size_bytes"] == 2 * 1024 * 1024
    assert data["scan_complete"]


@pytest.mark.parametrize("command", ["du -sh .", "du -sb ."])
def test_du_uses_live_metadata_without_snapshot_capture_or_subprocess(tmp_path, monkeypatch, command):
    root = tmp_path / "root"
    root.mkdir()
    (root / "file").write_bytes(b"payload" * 200)
    policy = Policy(config(bash_roots=(root,)))
    call = policy.prepare("bash", {"root": str(root), "command": command})
    monkeypatch.setattr(bash, "snapshot", lambda *a, **k: pytest.fail("du made a snapshot"))
    monkeypatch.setattr("os_assistant.runner.run_captured", lambda *a, **k: pytest.fail("du ran subprocess"))
    data = Runner(policy).run(call).data
    assert data["executor"] == "guarded_live_size_metadata"
    assert data["temporary_snapshot_created"] is False
    assert data["metadata_kind"] == "live_host_metadata_not_snapshot"
    assert data["contents_read"] is False


def test_directory_usage_dry_run_never_scans(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    policy = Policy(config(roots=(root,)))
    monkeypatch.setattr(policy, "directory_usage", lambda *a: pytest.fail("dry-run scanned usage"))
    monkeypatch.setattr(filesystem, "usage", lambda *a, **k: pytest.fail("dry-run called scanner"))
    call = policy.prepare("directory_usage", {"root": str(root)})
    assert Runner(policy, dry_run=True).run(call).status == "preview"


@pytest.mark.parametrize("path", ["../outside", "sub/../../outside", "link", "link/child"])
def test_usage_refuses_outside_traversal_and_symlink_subfolders(tmp_path, path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    policy = Policy(config(roots=(root,)))
    with pytest.raises(PolicyError):
        policy.prepare("directory_usage", {"root": str(root), "path": path})


def test_empty_directories_are_counted_from_live_metadata_not_zero_snapshot(tmp_path):
    root = tmp_path / "root"
    (root / "one" / "two").mkdir(parents=True)
    data = usage(Policy(config(roots=(root,))), root).data
    expected = sum(path.stat().st_blocks * 512 for path in (root, root / "one", root / "one/two"))
    assert data["allocated_size_bytes"] == expected
    assert data["directories_scanned"] == 3
    assert data["metadata_kind"] == "live_host_metadata_not_snapshot"


@pytest.mark.parametrize("mounted", ["child", "file"])
def test_same_device_bind_mount_metadata_is_excluded(tmp_path, monkeypatch, mounted):
    root = tmp_path / "approved"
    (root / "child").mkdir(parents=True)
    (root / "child/nested").write_bytes(b"mounted")
    (root / "file").write_bytes(b"file-mount")
    (root / "ordinary").write_bytes(b"safe")
    real_mount_id = bash._mount_id
    def mount_id(fd):
        return "fixture-nested-mount" if os.readlink(f"/proc/self/fd/{fd}") == str(root / mounted) else real_mount_id(fd)
    monkeypatch.setattr(bash, "_mount_id", mount_id)
    data = usage(Policy(config(roots=(root,))), root).data
    expected = 4 + (10 if mounted == "child" else 7)
    assert data["total_size_bytes"] == expected and data["excluded_entries"] == 1
    assert data["scan_complete"]


@pytest.mark.parametrize("command", ["du -sh . | head -n 1", "du -a .", "du -c .", "du --max-depth 1 ."])
def test_du_does_not_silently_use_snapshot_or_unknown_semantics(tmp_path, command, monkeypatch):
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Invalid du reached filesystem probes"))
    with pytest.raises(PolicyError):
        Policy(config(bash_roots=(tmp_path,))).prepare("bash", {"command": command})


def test_home_aliases_canonicalize_but_never_grant_home_or_parent_access(tmp_path, monkeypatch):
    # Alias handling is host-independent: do not require bubblewrap or root-owned /usr/bin tools here.
    monkeypatch.setattr(bash, "_trusted_executable", lambda path: (path, path, "host-independent fixture"))
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".dotfiles"
    root.mkdir()
    policy = Policy(config(bash_roots=(root,)))
    assert policy.prepare("directory_usage", {"root": "~/.dotfiles"}).argument_dict()["root"] == str(root)
    assert policy.prepare("bash", {"command": "ls ~/.dotfiles", "cwd": "~/.dotfiles"}).argument_dict()["cwd"] == "."
    for args in ({"command": "ls ~/"}, {"command": "cat ~/.ssh/key"}, {"command": "ls", "root": "~/"},
                 {"command": "ls", "root": "~/.dotfiles/../outside"}):
        with pytest.raises(PolicyError):
            policy.prepare("bash", args)


def test_changed_usage_root_is_refused_before_scanning(tmp_path, monkeypatch):
    root = tmp_path / "approved"
    root.mkdir()
    policy = Policy(config(roots=(root,)))
    call = policy.prepare("directory_usage", {})
    root.rename(tmp_path / "previous")
    root.mkdir()
    monkeypatch.setattr(filesystem, "usage", lambda *a, **kw: pytest.fail("Replaced root scanned"))
    with pytest.raises(PolicyError):
        Runner(policy).run(call)

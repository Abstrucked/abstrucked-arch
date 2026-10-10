"""Restricted Bash and file operations use disposable folders, never the desktop."""

from dataclasses import FrozenInstanceError, replace
import io
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import bash, cli
from os_assistant.config import Config
from os_assistant.contracts import AssistantError, PolicyError, PreparedCall
from os_assistant.policy import Policy, tool_schemas
from os_assistant.runner import Runner, run_captured
import os_assistant.runner as execution


def configuration(root, *, writes=True, **values):
    return replace(Config(), **{"bash_enabled": True, "bash_roots": (str(root),),
                                "bash_allow_writes": writes, "actions_enabled": writes, **values})


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "approved"
    (root / "sub").mkdir(parents=True)
    (root / "readme.txt").write_text("alpha\nbeta\nalpha\n")
    (root / "sub/code.py").write_text("print('alpha')\n")
    return root


def test_bash_is_disabled_by_default_and_metadata_roots_do_not_grant_contents(workspace):
    for cfg in (Config(), Config(allowed_roots=(str(workspace),))):
        assert "bash" not in {item["function"]["name"] for item in tool_schemas(cfg)}
        with pytest.raises(PolicyError):
            Policy(cfg).prepare("bash", {"root": str(workspace), "command": "ls"})


def test_bash_schema_is_strict_and_uses_separate_approved_roots(workspace):
    schemas = {item["function"]["name"]: item["function"]["parameters"] for item in tool_schemas(configuration(workspace))}
    assert schemas["bash"]["additionalProperties"] is False
    assert schemas["bash"]["required"] == ["command"]
    assert schemas["bash"]["properties"]["root"]["enum"] == [str(workspace)]


@pytest.mark.parametrize("command", [
    "pwd", "ls -lh .", "ls -a sub", "cat readme.txt", "grep -n alpha readme.txt",
    "grep -r -e alpha .", "rg alpha .", "find . -maxdepth 2 -type f -name '*.py' -print",
    "head -n 2 readme.txt", "tail -c 10 readme.txt", "wc -l readme.txt",
    "cat readme.txt | sort -n | uniq -c | head -n 5", "cut -d : -f 1 readme.txt",
    "du -sh .", "df -h .", "echo hello", "printf '%s\\n' hello",
    "grep 'alpha$' readme.txt", "grep -e 'alpha|beta' readme.txt",
])
def test_audited_read_commands_are_frozen_and_never_require_mutation_rights(workspace, command):
    cfg = configuration(workspace, writes=False)
    call = Policy(cfg).prepare("bash", {"root": str(workspace), "command": command})
    assert not call.mutates and call.argument_dict()["cwd"] == "." and len(call.verification) == 64
    if command.startswith("du "):
        assert call.argv == ("/usr/bin/du", "-sh", "--", "/work")
    else:
        assert call.argv[:4] == ("/usr/bin/bash", "--noprofile", "--norc", "-c")
    with pytest.raises(FrozenInstanceError):
        call.mutates = True


@pytest.mark.parametrize("command", [
    "ls; rm readme.txt", "ls && rm readme.txt", "ls || touch x", "ls &", "ls ;& rm x",
    "(ls)", "bash -c ls", "sh -c ls", "python3 -c 'print(1)'", "sudo ls", "curl https://example.com",
    "env ls", "PATH=/tmp ls", "xargs rm", "source readme.txt", "exec ls", "command ls",
    "ls $(touch x)", "echo `touch x`", "echo ${HOME}", "ls > result", "cat < readme.txt",
    "grep -f .env readme.txt", "find . -exec touch x ';'", "find . -delete", "find . -fprint output",
    "sort -o output readme.txt", "sort --compress-program=touch readme.txt", "uniq readme.txt output",
    "sed -i s/a/b/ readme.txt", "rg --pre touch alpha .", "rg --search-zip alpha .",
    "tail -f readme.txt", "wc --files0-from readme.txt", "grep --color=always alpha readme.txt",
    "rm -rf .", "mkdir -p a/b", "cp readme.txt |", "touch ../escaped", "ls /etc",
    "cat /proc/self/environ", "ls $HOME", "ls *.py", "ls .git", "grep -r alpha .config",
    "cat .env", "cat credentials.json", "cat secrets/token", "cat private.key", "ls | | head",
    "ls | cat | sort | uniq | head", "printf hello", "echo -e hello", "ls > x > y",
    "echo hello > x | cat", "ls --unknown", "head -n 1001 readme.txt", "cat 'unterminated",
])
def test_dangerous_unsupported_or_protected_commands_fail_before_trust_probes(workspace, command, monkeypatch):
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Invalid command reached filesystem/executable probes"))
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command})


@pytest.mark.parametrize("arguments", [None, [], "ls", {"root": "missing"},
                                          {}, {"root": "", "command": "ls"},
                                          {"command": "ls", "approved": True},
                                          {"command": "ls", "mutates": False},
                                          {"command": "ls", "command_argv": ["/bin/sh"]},
                                          {"command": "ls\nrm x"}, {"command": "x" * 2049}])
def test_bad_schema_never_reaches_execution(workspace, arguments, monkeypatch):
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Bad schema was prepared"))
    if isinstance(arguments, dict):
        arguments = {"root": str(workspace), **arguments}
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", arguments)


@pytest.mark.parametrize("command", ["mkdir new", "touch new", "cp readme.txt new", "mv readme.txt new",
                                    "rm readme.txt", "echo hello > new", "printf '%s\\n' hello >> new"])
@pytest.mark.parametrize("actions,writes", [(False, False), (False, True), (True, False)])
def test_writes_require_both_opt_ins_before_file_probes(workspace, command, actions, writes, monkeypatch):
    cfg = configuration(workspace, actions_enabled=actions, bash_allow_writes=writes)
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Disabled mutation inspected operands"))
    with pytest.raises(PolicyError):
        Policy(cfg).prepare("bash", {"root": str(workspace), "command": command})


@pytest.mark.parametrize("command", ["ls", "touch new", "rm readme.txt", "echo hello > new"])
def test_dry_run_never_copies_reads_contents_mutates_executes_or_approves(workspace, command, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Dry-run executed, staged contents, or requested approval")
    monkeypatch.setattr(bash, "snapshot", forbidden)
    monkeypatch.setattr(bash, "run_mutation", forbidden)
    monkeypatch.setattr(execution, "run_captured", forbidden)
    runner = Runner(Policy(configuration(workspace)), dry_run=True, confirm=forbidden)
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": command}))
    assert result.status == "preview" and not (workspace / "new").exists()


def test_denial_never_mutates_or_runs_a_shell(workspace, monkeypatch):
    monkeypatch.setattr(bash, "run_mutation", lambda *a, **kw: pytest.fail("Denied operation ran"))
    runner = Runner(Policy(configuration(workspace)))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "rm readme.txt"}))
    assert result.status == "denied" and (workspace / "readme.txt").exists()


def test_bash_cannot_rewrite_its_own_permission_code(workspace, monkeypatch):
    monkeypatch.setattr(bash, "ASSISTANT_PACKAGE", workspace / "assistant")
    for command in ("echo bypass > assistant/policy.py", "rm assistant/policy.py", "cp readme.txt assistant/policy.py"):
        with pytest.raises(PolicyError, match="own package"):
            Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command})


@pytest.mark.parametrize("command", ["echo bypass > themes/themectl", "rm themes/themectl",
                                    "cp readme.txt scripts/display-detect", "mv scripts/display-detect scratch",
                                    "touch plugins/tailscale.json"])
def test_file_write_permission_cannot_rewrite_a_helper_that_runs_automatically(workspace, monkeypatch, command):
    monkeypatch.setattr(bash, "TRUSTED_HELPER_ROOTS", (workspace / "themes", workspace / "scripts", workspace / "plugins"))
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Helper write reached filesystem probes"))
    with pytest.raises(PolicyError, match="trusted theme/plugin/status"):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command})


def test_copying_a_protected_helper_source_out_is_not_a_helper_mutation(workspace, monkeypatch):
    (workspace / "assistant").mkdir()
    (workspace / "assistant/example.py").write_text("print('example')\n")
    monkeypatch.setattr(bash, "ASSISTANT_PACKAGE", workspace / "assistant")
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: True)
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "cp assistant/example.py scratch"}))
    assert result.status == "ok" and (workspace / "scratch").read_text() == "print('example')\n"


def test_escaped_unicode_cannot_hide_a_write_destination_in_a_truncated_preview(workspace, monkeypatch):
    command = "echo '" + "😀" * 600 + "' > new"
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: pytest.fail("Oversized mutation reached file probes"))
    with pytest.raises(PolicyError, match="exact terminal preview"):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command})


def test_forged_read_only_call_cannot_execute_mutation_or_arbitrary_argv(workspace, monkeypatch):
    runner = Runner(Policy(configuration(workspace)))
    real = runner.policy.prepare("bash", {"root": str(workspace), "command": "rm readme.txt"})
    forged = PreparedCall(real.name, real.arguments, False, ("/bin/sh", "-c", "true"), real.verification)
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("Forged shell executed"))
    with pytest.raises(PolicyError):
        runner.run(forged)


@pytest.mark.parametrize("stage", ["before_run", "during_approval"])
def test_changed_mutation_operand_invalidates_exact_approval(workspace, stage):
    runner = Runner(Policy(configuration(workspace)))
    call = runner.policy.prepare("bash", {"root": str(workspace), "command": "rm readme.txt"})
    if stage == "before_run":
        (workspace / "readme.txt").write_text("changed")
    else:
        def approve(call):
            (workspace / "readme.txt").write_text("changed")
            return True
        runner.confirm = approve
    with pytest.raises(PolicyError):
        runner.run(call)
    assert (workspace / "readme.txt").read_text() == "changed"


def test_snapshot_never_reads_links_protected_files_devices_or_large_files(workspace, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("private-fixture-value")
    (workspace / "linked").symlink_to(outside)
    os.link(outside, workspace / "hardlink")
    (workspace / ".env").write_text("private-fixture-value")
    (workspace / ".config").mkdir()
    (workspace / ".config/auth.json").write_text("private-fixture-value")
    os.mkfifo(workspace / "fifo")
    (workspace / "large").write_bytes(b"x" * (bash.FILE_BYTES + 1))
    destination = tmp_path / "snapshot"
    destination.mkdir()
    data = bash.snapshot(str(workspace), destination, configuration(workspace))
    assert data["files_copied"] == 2 and data["excluded_entries"] == 6
    assert sorted(p.name for p in destination.iterdir()) == ["readme.txt", "sub"]
    assert "private-fixture-value" not in repr(data)


def test_snapshot_is_entry_depth_byte_and_time_bounded(workspace, tmp_path, monkeypatch):
    destination = tmp_path / "snapshot"
    destination.mkdir()
    data = bash.snapshot(str(workspace), destination, configuration(workspace, scan_entries=1))
    assert data["truncated_snapshot"]
    destination2 = tmp_path / "snapshot2"
    destination2.mkdir()
    monkeypatch.setattr(bash, "SNAPSHOT_BYTES", 2)
    data = bash.snapshot(str(workspace), destination2, configuration(workspace))
    assert data["bytes_copied"] <= 2 and data["truncated_snapshot"]
    ticks = iter([0, 100])
    monkeypatch.setattr(bash.time, "monotonic", lambda: next(ticks))
    destination3 = tmp_path / "snapshot3"
    destination3.mkdir()
    assert bash.snapshot(str(workspace), destination3, configuration(workspace))["truncated_snapshot"]


def test_snapshot_depth_bound_excludes_deeper_content(workspace, tmp_path):
    (workspace / "sub/deeper").mkdir()
    (workspace / "sub/deeper/hidden.txt").write_text("deeper")
    destination = tmp_path / "snapshot"
    destination.mkdir()
    data = bash.snapshot(str(workspace), destination, configuration(workspace, scan_depth=1))
    assert data["truncated_snapshot"] and not (destination / "sub/deeper").exists()


@pytest.mark.parametrize("command,expected_names", [
    ("ls .", {"readme.txt", "large", "sub"}),
    ("ls sub", {"sub", "sub/code.py"}),
    ("find . -type f", {"readme.txt", "large", "sub", "sub/code.py"}),
    ("du --apparent-size sub", {"sub", "sub/code.py"}),
])
def test_metadata_commands_do_not_read_file_contents_or_consume_copy_budget(workspace, tmp_path, command,
                                                                           expected_names, monkeypatch):
    (workspace / "large").write_bytes(b"x" * (bash.FILE_BYTES + 1))
    destination = tmp_path / "metadata"
    destination.mkdir()
    original_open = bash.os.open
    def open_no_content(path, flags, *args, **kwargs):
        if path in {"readme.txt", "large", "code.py"} and "dir_fd" in kwargs:
            assert flags & os.O_PATH or flags & os.O_WRONLY, "Metadata command read source contents"
        return original_open(path, flags, *args, **kwargs)
    monkeypatch.setattr(bash.os, "open", open_no_content)
    monkeypatch.setattr(bash, "SNAPSHOT_BYTES", 1)
    command_plan = bash.plan(configuration(workspace), {"root": str(workspace), "command": command})
    data = bash.snapshot(str(workspace), destination, configuration(workspace), command_plan)
    assert {str(p.relative_to(destination)) for p in destination.rglob("*")} == expected_names
    assert data["bytes_copied"] == data["files_copied"] == 0 and data["metadata_placeholders"] > 0
    assert not data["truncated_snapshot"]
    if (destination / "readme.txt").exists():
        assert (destination / "readme.txt").stat().st_size == (workspace / "readme.txt").stat().st_size


def test_precise_content_operand_avoids_unrelated_large_subtrees(workspace, tmp_path, monkeypatch):
    for index in range(10):
        (workspace / "sub" / f"unrelated{index}").write_text("unrelated")
    destination = tmp_path / "selected"
    destination.mkdir()
    monkeypatch.setattr(bash, "SNAPSHOT_BYTES", (workspace / "readme.txt").stat().st_size)
    command = bash.plan(configuration(workspace), {"root": str(workspace), "command": "grep alpha readme.txt"})
    data = bash.snapshot(str(workspace), destination, configuration(workspace), command)
    assert data["files_copied"] == 1 and data["metadata_placeholders"] == 0 and not data["truncated_snapshot"]
    assert sorted(p.name for p in destination.iterdir()) == ["readme.txt"]


def test_mixed_pipeline_copies_real_contents_instead_of_reading_metadata_proxies(workspace, tmp_path):
    destination = tmp_path / "mixed"
    destination.mkdir()
    command = bash.plan(configuration(workspace), {"root": str(workspace), "command": "ls . | cat readme.txt"})
    data = bash.snapshot(str(workspace), destination, configuration(workspace), command)
    assert data["files_copied"] == 1 and (destination / "readme.txt").read_text() == "alpha\nbeta\nalpha\n"
    assert not (destination / "sub/code.py").exists()


def test_pure_stdin_pipeline_does_not_scan_the_source_folder(workspace, monkeypatch):
    original_scandir = bash.os.scandir
    def no_scan(path):
        if isinstance(path, int) and os.readlink(f"/proc/self/fd/{path}") == str(workspace):
            pytest.fail("Literal stdin pipeline scanned files")
        return original_scandir(path)
    monkeypatch.setattr(bash.os, "scandir", no_scan)
    runner = Runner(Policy(configuration(workspace, writes=False)))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "echo alpha | grep alpha"}))
    assert result.status == "ok" and result.data["stdout"].strip() == "alpha"
    assert result.data["bytes_copied"] == result.data["metadata_placeholders"] == 0


@pytest.mark.parametrize("target,command", [("sub", "ls ."), ("sub", "grep -r alpha ."),
                                          ("readme.txt", "cat readme.txt"), ("readme.txt", "ls .")])
def test_same_device_nested_mounts_are_not_staged(workspace, tmp_path, monkeypatch, target, command):
    actual_mount_id = bash._mount_id
    def fixture_mount_id(fd):
        path = os.readlink(f"/proc/self/fd/{fd}")
        return "fixture-bind-mount" if path == str(workspace / target) else actual_mount_id(fd)
    monkeypatch.setattr(bash, "_mount_id", fixture_mount_id)
    destination = tmp_path / "mounted"
    destination.mkdir()
    selected = bash.plan(configuration(workspace), {"root": str(workspace), "command": command})
    data = bash.snapshot(str(workspace), destination, configuration(workspace), selected)
    assert not (destination / target).exists() and data["excluded_entries"] >= 1


@pytest.mark.parametrize("command", ["touch readme.txt", "rm readme.txt", "cp readme.txt new", "ls sub"])
def test_mount_identity_changes_block_preparation(workspace, monkeypatch, command):
    actual_mount_id = bash._mount_id
    def fixture_mount_id(fd):
        path = os.readlink(f"/proc/self/fd/{fd}")
        return "fixture-bind-mount" if path in {str(workspace / "readme.txt"), str(workspace / "sub")} else actual_mount_id(fd)
    monkeypatch.setattr(bash, "_mount_id", fixture_mount_id)
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command,
                                                           "cwd": "sub" if command.startswith("ls") else "."})


def test_changed_root_is_rejected_before_any_source_content_is_copied(workspace, tmp_path, monkeypatch):
    policy = Policy(configuration(workspace, writes=False))
    call = policy.prepare("bash", {"root": str(workspace), "command": "cat readme.txt"})
    command = bash.plan(policy.config, call.argument_dict())
    renamed = workspace.with_name("old-approved")
    workspace.rename(renamed)
    workspace.mkdir()
    (workspace / "readme.txt").write_text("replacement-root-fixture")
    destination = tmp_path / "destination"
    destination.mkdir()
    monkeypatch.setattr(bash.os, "scandir", lambda *a: pytest.fail("Replaced root contents inspected"))
    with pytest.raises(PolicyError, match="source folder changed"):
        bash.snapshot(str(workspace), destination, policy.config, command, call.verification)
    assert os.listdir(destination) == []


@pytest.mark.parametrize("command", ["grep alpha -e beta readme.txt", "rg alpha -e beta readme.txt"])
def test_mixed_implicit_and_explicit_patterns_are_refused(workspace, command):
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": command})


def test_pipe_rg_reads_pipeline_input_instead_of_searching_the_whole_tree(workspace):
    runner = Runner(Policy(configuration(workspace, writes=False)))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "echo alpha | rg alpha | wc -l"}))
    assert result.status == "ok", result.data
    assert result.data["stdout"].strip() == "1"


@pytest.mark.parametrize("cwd", ["../outside", ".config", ".git", "/etc", "$HOME"])
def test_working_directory_cannot_bypass_the_root_or_protected_paths(workspace, cwd):
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": "ls", "cwd": cwd})


def test_a_linked_working_directory_is_refused(workspace, tmp_path):
    (workspace / "linked").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": "ls", "cwd": "linked"})


def test_subfolder_paths_are_mapped_without_changing_host_cwd(workspace):
    runner = Runner(Policy(configuration(workspace, writes=False)))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "cat code.py", "cwd": "sub"}))
    assert result.status == "ok" and result.data["stdout"] == "print('alpha')\n"


def test_bash_rechecks_helper_changes_before_execution(workspace, monkeypatch):
    runner = Runner(Policy(configuration(workspace, writes=False)))
    call = runner.policy.prepare("bash", {"root": str(workspace), "command": "ls"})
    monkeypatch.setattr(bash, "_trusted_executable", lambda path: (path, "changed fixture"))
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("Changed helper executed"))
    with pytest.raises(PolicyError):
        runner.run(call)


def test_missing_dependencies_have_no_unsandboxed_fallback(workspace, monkeypatch):
    def unavailable(path):
        raise PolicyError("No trusted sandbox")
    monkeypatch.setattr(bash, "_trusted_executable", unavailable)
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("Missing sandbox bypassed"))
    with pytest.raises(PolicyError):
        Policy(configuration(workspace)).prepare("bash", {"root": str(workspace), "command": "ls"})


def test_confirmations_are_exact_and_not_reused(workspace):
    approvals = []
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: approvals.append(call) or True)
    for command in ("touch first", "touch second"):
        assert runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": command})).status == "ok"
    assert len(approvals) == 2 and approvals[0].argument_dict()["command"] == "touch first"
    assert approvals[1].argument_dict()["command"] == "touch second"


@pytest.mark.parametrize("approval", [False, "yes", 1, None])
def test_only_true_from_the_terminal_approval_callback_grants_file_changes(workspace, approval):
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: approval)
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "touch new"}))
    assert result.status == "denied" and not (workspace / "new").exists()


def test_real_sandbox_cannot_connect_to_a_host_loopback_listener(workspace, tmp_path):
    import socket
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        fixture = bash.CommandPlan(str(workspace), ".", ())
        argv = bash.sandbox_argv(str(tmp_path), fixture)
        script = ("import socket,sys\n"
                  "s=socket.socket();s.settimeout(0.5)\n"
                  f"try: s.connect(('127.0.0.1',{port}))\n"
                  "except OSError: sys.exit(0)\n"
                  "sys.exit(1)")
        code, _, stderr = run_captured((*argv[:-5], "/usr/bin/python3", "-I", "-c", script), 5,
                                      environment={"PATH": "/usr/bin"})
        assert code == 0, stderr


def test_read_only_execution_uses_only_filtered_snapshot_and_scrubbed_environment(workspace, monkeypatch):
    (workspace / ".env").write_text("private fixture")
    def capture(argv, timeout, *, environment):
        assert argv[0] == "/usr/bin/prlimit" and "--as=134217728" in argv
        assert "--unshare-all" in argv and "--disable-userns" in argv and "--new-session" in argv
        assert "--clearenv" in argv and "--share-net" not in argv and "--bind" not in argv
        assert environment == {"PATH": "/usr/bin", "LC_ALL": "C"}
        pos = argv.index("/work")
        staged = Path(argv[pos - 1])
        assert staged != workspace and (staged / "readme.txt").exists() and not (staged / ".env").exists()
        assert str(workspace) not in argv
        return 0, "alpha\n", ""
    monkeypatch.setattr(execution, "run_captured", capture)
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: pytest.fail("Read-only requested approval"))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "grep alpha readme.txt"}))
    assert result.status == "ok" and result.data["snapshot_only"] and not result.data["persistent_host_writes"]
    assert result.data["stdout"] == "alpha\n"


@pytest.mark.parametrize("failure", [AssistantError("fixture timeout"), OSError("fixture unavailable sandbox")])
def test_failed_sandbox_never_falls_back_to_a_host_shell(workspace, monkeypatch, failure):
    calls = []
    def failed(argv, timeout, **kwargs):
        calls.append(argv)
        raise failure
    monkeypatch.setattr(execution, "run_captured", failed)
    runner = Runner(Policy(configuration(workspace)))
    result = runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": "ls"}))
    assert result.status == "error" and len(calls) == 1 and calls[0][0] == "/usr/bin/prlimit"
    assert "no unsandboxed fallback" in result.data["message"]


@pytest.mark.parametrize("command", ["mkdir new", "touch new", "cp readme.txt new", "mv readme.txt new",
                                    "rm readme.txt", "echo hello > new", "printf '%s\\n' hello >> new"])
def test_confirmed_operations_only_modify_disposable_approved_paths(workspace, command, monkeypatch):
    monkeypatch.setattr(execution, "run_captured", lambda *a, **kw: pytest.fail("File operation used a host shell"))
    approvals = []
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: approvals.append(call) or True)
    call = runner.policy.prepare("bash", {"root": str(workspace), "command": command})
    assert call.mutates
    result = runner.run(call)
    assert result.status == "ok" and approvals == [call]
    assert result.data["executor"] == "guarded_fd_file_operation"
    if command.startswith("rm"):
        assert not (workspace / "readme.txt").exists()
    elif command.startswith("mkdir"):
        assert (workspace / "new").is_dir()
    else:
        assert (workspace / "new").is_file()
    if command.startswith("mv"):
        assert not (workspace / "readme.txt").exists()
    assert not list(workspace.glob(".os-assistant-*"))


def test_writes_replace_atomically_and_append_literal_data(workspace):
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: True)
    for command in ("echo first > readme.txt", "printf '%s\\n' second >> readme.txt"):
        assert runner.run(runner.policy.prepare("bash", {"root": str(workspace), "command": command})).status == "ok"
    assert (workspace / "readme.txt").read_text() == "first\nsecond\n"
    assert (workspace / "readme.txt").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("command", ["touch linked", "rm linked", "cp linked copy", "mv linked copy", "echo hello > linked"])
def test_mutations_never_follow_leaf_links_even_with_approval(workspace, tmp_path, command):
    outside = tmp_path / "private.txt"
    outside.write_text("untouched")
    (workspace / "linked").symlink_to(outside)
    runner = Runner(Policy(configuration(workspace)), confirm=lambda call: True)
    with pytest.raises(PolicyError):
        runner.policy.prepare("bash", {"root": str(workspace), "command": command})
    assert outside.read_text() == "untouched"


def test_live_disposable_read_only_pipeline_is_isolated(workspace):
    runner = Runner(Policy(configuration(workspace, writes=False)))
    call = runner.policy.prepare("bash", {"root": str(workspace), "command": "grep alpha readme.txt | wc -l"})
    result = runner.run(call)
    assert result.status == "ok", result.data
    assert result.data["stdout"].strip() == "2" and result.data["persistent_host_writes"] is False


def test_real_sandbox_blocks_host_paths_writes_environment_and_network(workspace, tmp_path):
    secret = tmp_path / "not-visible.txt"
    secret.write_text("not-visible")
    staged = tmp_path / "staged"
    staged.mkdir()
    (staged / "visible").write_text("visible")
    # This is a fixed security fixture, not model input or an exposed tool command.
    script = (f"test ! -e {str(secret)} && test -z \"${{PRIVATE_API_TOKEN:-}}\" && "
              "test ! -e /home && ! touch /work/written && ! touch /usr/bin/written")
    fixture = bash.CommandPlan(str(workspace), ".", ())
    argv = bash.sandbox_argv(str(staged), fixture)
    argv = (*argv[:-1], script)
    code, stdout, stderr = run_captured(argv, 5, environment={"PATH": "/usr/bin", "PRIVATE_API_TOKEN": "fixture-only"})
    assert code == 0, stderr
    assert not (staged / "written").exists() and "fixture-only" not in stdout


def _cli_config(tmp_path, workspace):
    config = tmp_path / "bash-settings.toml"
    config.write_text("[actions]\nenabled = true\n[bash]\nenabled = true\nallow_writes = true\n"
                      f"allowed_roots = [{json.dumps(str(workspace))}]\n")
    return str(config)


def test_cli_bash_read_needs_no_terminal_confirmation_or_model(workspace, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "confirm", lambda call: pytest.fail("Automatic read asked for approval"))
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Direct Bash tool contacted model"))
    arguments = json.dumps({"root": str(workspace), "command": "grep alpha readme.txt"})
    assert cli.main(["--config", _cli_config(tmp_path, workspace), "--tool", "bash", "--arguments", arguments]) == 0
    output = capsys.readouterr().out
    assert "alpha" in output and "filtered snapshot" in output
    assert "data:" not in output and "arguments:" not in output
    assert cli.main(["--config", _cli_config(tmp_path, workspace), "--json", "--tool", "bash", "--arguments", arguments]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["status"] == "ok" and record["data"]["persistent_host_writes"] is False


def test_cli_piped_yes_cannot_approve_bash_file_changes(workspace, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("yes\n"))
    monkeypatch.setattr(bash, "run_mutation", lambda *a, **kw: pytest.fail("Piped approval ran a file operation"))
    arguments = json.dumps({"root": str(workspace), "command": "touch new"})
    assert cli.main(["--config", _cli_config(tmp_path, workspace), "--tool", "bash", "--arguments", arguments]) == 3
    assert not (workspace / "new").exists()


@pytest.mark.parametrize("answer,expected", [("yes\n", 0), ("y\n", 3), ("YES\n", 3)])
def test_cli_bash_write_preview_precedes_exact_typed_approval(workspace, tmp_path, monkeypatch, answer, expected):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    stdin, stdout = Tty(answer), Tty()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)
    config_path = _cli_config(tmp_path, workspace)
    original_mutation = bash.run_mutation
    def inspect_preview(call, config):
        output = stdout.getvalue()
        assert "Command: 'touch new'" in output and str(workspace / "new") in output
        assert "Guarded file operation; no host shell" in output
        assert output.index("Command: 'touch new'") < output.index("Type yes to approve")
        assert "arguments:" not in output and "argv:" not in output
        return original_mutation(call, config)
    monkeypatch.setattr(bash, "run_mutation", inspect_preview)
    arguments = json.dumps({"root": str(workspace), "command": "touch new"})
    assert cli.main(["--config", config_path, "--tool", "bash", "--arguments", arguments]) == expected
    assert (workspace / "new").exists() is (expected == 0)

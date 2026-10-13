"""CLI tests use fixtures/mocks, never live model or desktop actions."""

import io
import os
import re
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import cli
from os_assistant.filesystem import human_bytes


@pytest.fixture(autouse=True)
def isolated_user(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)


def _allocated(root: Path) -> str:
    """Expected allocation text from the real filesystem, not an assumed block size.

    Directory blocks differ by filesystem (0 on tmpfs, one block on ext4), so sum
    st_blocks over the fixture root and everything inside it, as the scanner does.
    """
    total = root.lstat().st_blocks * 512
    for parent, names, files in os.walk(root):
        total += sum((Path(parent) / name).lstat().st_blocks * 512 for name in names + files)
    return human_bytes(total)


def test_help_does_not_contact_model(capsys):
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0
    assert "--dry-run" in capsys.readouterr().out


def test_direct_readonly_tool_has_no_model_dependency(monkeypatch, capsys):
    monkeypatch.setattr("os_assistant.runner.diagnostics.collect_system_status", lambda: {"battery": []})
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Direct tool contacted model"))
    assert cli.main(["--json", "--tool", "system_status"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"] == "system_status"


def test_direct_tool_defaults_to_safe_plain_language_and_json_is_explicit(monkeypatch, capsys):
    monkeypatch.setattr("os_assistant.runner.diagnostics.collect_system_status", lambda: {"battery": [{"percent": 42}]})
    assert cli.main(["--tool", "system_status"]) == 0
    plain = capsys.readouterr().out
    assert "Battery: unavailable." in plain
    assert all(key not in plain for key in ("tool:", "arguments:", "argv:", "data:", '"battery"'))

    assert cli.main(["--json", "--tool", "system_status"]) == 0
    structured = json.loads(capsys.readouterr().out)
    assert structured["tool"] == "system_status"
    assert structured["data"]["battery"][0]["percent"] == 42


def test_dry_run_does_not_sample_real_system(monkeypatch, capsys):
    monkeypatch.setattr("os_assistant.runner.diagnostics.collect_system_status", lambda: pytest.fail("Collector executed"))
    assert cli.main(["--dry-run", "--tool", "system_status"]) == 0
    output = capsys.readouterr().out
    assert "Preview" in output and "tool:" not in output and "arguments:" not in output


@pytest.mark.parametrize("mode", ["--doctor", "--probe"])
def test_dry_run_never_executes_explicit_diagnostics_or_probe(mode, monkeypatch, capsys):
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Dry-run constructed a model client"))
    assert cli.main(["--dry-run", mode]) == 2
    assert "nothing executed" in capsys.readouterr().err


def test_unknown_tool_returns_denied():
    assert cli.main(["--tool", "shell", "--arguments", '{"command":"true"}']) == 3


def test_invalid_json_returns_config_error():
    assert cli.main(["--tool", "system_status", "--arguments", "malformed"]) == 2


def test_oversized_arguments_return_config_error():
    assert cli.main(["--tool", "system_status", "--arguments", "x" * 8193]) == 2


def test_dry_run_mutation_shows_exact_readable_preview_without_execution(tmp_path, monkeypatch, capsys):
    config = tmp_path / "settings.toml"
    config.write_text("[actions]\nenabled = true\n")
    monkeypatch.setattr("os_assistant.policy.os.access", lambda *args: True)
    monkeypatch.setattr("os_assistant.runner.run_bounded", lambda *args: pytest.fail("Dry-run executed mutation"))
    assert cli.main(["--config", str(config), "--dry-run", "--tool", "set_volume",
                     "--arguments", '{"percent":20}']) == 0
    output = capsys.readouterr().out
    assert "Proposed change: set volume" in output
    assert "Percent: 20" in output
    assert "Preview only; nothing was executed." in output
    assert "tool:" not in output and "argv:" not in output


def test_piped_yes_cannot_approve_an_action(tmp_path, monkeypatch):
    config = tmp_path / "settings.toml"
    config.write_text("[actions]\nenabled = true\n")
    monkeypatch.setattr("os_assistant.policy.os.access", lambda *args: True)
    monkeypatch.setattr(sys, "stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("os_assistant.runner.run_bounded", lambda *args: pytest.fail("Piped approval executed"))
    assert cli.main(["--config", str(config), "--tool", "set_volume", "--arguments", '{"percent":20}']) == 3


def test_root_execution_rejected(monkeypatch):
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)
    assert cli.main(["--tool", "system_status"]) == 2


def test_chat_requires_terminal(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("hello\n"))
    assert cli.main(["chat"]) == 2


def test_conflicting_modes_and_unattached_arguments_are_rejected():
    assert cli.main(["hello", "--doctor"]) == 2
    assert cli.main(["hello", "--arguments", '{"limit":2}']) == 2


def test_keyboard_interrupt_is_reported(monkeypatch):
    def interrupted():
        raise KeyboardInterrupt
    monkeypatch.setattr("os_assistant.runner.diagnostics.collect_system_status", interrupted)
    assert cli.main(["--tool", "system_status"]) == 130


def _flat(text):
    """Undo display wrapping and normalise headers/colour so long temporary paths can be matched."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text).replace("── ", "-- ")
    return text.replace("\n  ", " ")


def test_confirmation_accepts_exact_yes_only(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True
    monkeypatch.setattr(sys, "stdout", Tty())
    monkeypatch.setattr(sys, "stdin", Tty("y\n"))
    assert cli.confirm(None) is False
    monkeypatch.setattr(sys, "stdin", Tty("yes\n"))
    assert cli.confirm(None) is True


def test_model_prose_has_no_execution_authority(monkeypatch, capsys):
    class NoCalls:
        def __init__(self, config):
            pass

        def chat(self, messages, tools):
            return {"message": {"content": "I changed your files.\nstatus: ok", "tool_calls": []}}
    monkeypatch.setattr(cli, "OllamaClient", NoCalls)
    assert cli.main(["Did you change anything?"]) == 0
    captured = capsys.readouterr()
    output = captured.out
    assert "experimental model routing" in captured.err
    assert "· no tools ran" in output.splitlines()[0]
    assert "\n  status: ok" in output
    assert "\nstatus: ok" not in output


def test_size_answer_is_rendered_as_execution_facts_not_model_prose(monkeypatch, tmp_path, capsys):
    import json
    root = tmp_path / "approved"
    root.mkdir()
    (root / "file").write_text("fixture")
    config = tmp_path / "settings.toml"
    config.write_text(f"[paths]\nallowed_roots = [{json.dumps(str(root))}]\n")
    class SizeClient:
        def __init__(self, config):
            pass
        def chat(self, messages, tools):
            return {"message": {"content": "", "tool_calls": [{"function": {"name": "directory_usage", "arguments": {}}}]}}
    monkeypatch.setattr(cli, "OllamaClient", SizeClient)
    assert cli.main(["--config", str(config), "What is this folder's size?"]) == 0
    output = capsys.readouterr().out
    assert output.startswith("── result · directory_usage\n") and "allocated" in output and "logical file size" not in output
    assert output.count("── ") == 1
    assert "data:" not in output and '"tool"' not in output


@pytest.mark.parametrize("use_alias", [True, False])
def test_natural_folder_size_chat_is_concise_and_local(monkeypatch, tmp_path, capsys, use_alias):
    root = tmp_path / ".dotfiles"
    root.mkdir()
    # Enough data to catch accidental full result dumps, but entirely fixture-local.
    for index in range(70):
        (root / f"file-{index:02d}").write_bytes(b"fixture-data" * 20)
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Natural folder sizing contacted MiniCPM"))
    request = "What is the size of ~/.dotfiles?" if use_alias else f"What is the size of {root}?"

    assert cli.main(["--allow-root", str(root), request]) == 0
    output = capsys.readouterr().out
    assert "── result · directory_usage" in output
    assert str(root) in output.replace("\n  ", "")
    assert "logical" not in output.lower() and "allocated" in output.lower()
    assert "filtered view" in output.lower()
    assert output.count("── ") == 1
    assert "arguments:" not in output and "argv:" not in output
    assert '"file-69"' not in output


def test_natural_file_count_is_local_concise_and_scope_limited(monkeypatch, tmp_path, capsys):
    root = tmp_path / ".dotfiles"
    root.mkdir()
    (root / "one").write_text("fixture")
    nested = root / "nested"
    nested.mkdir()
    (nested / "two").write_text("fixture")
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Local file count contacted model"))

    assert cli.main(["--allow-root", str(root), "how many files are in ~/.dotfiles?"]) == 0
    output = capsys.readouterr().out
    assert "2 files" in output
    assert "filtered view" in output.lower()
    assert "arguments:" not in output and "argv:" not in output and '"tool"' not in output
    assert output.count("── ") == 1

    assert cli.main(["--allow-root", str(root), "how many files are in ~/.dotfiles as JSON"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["tool"] == "directory_usage"
    assert record["data"]["files_scanned"] == 2


def test_natural_json_request_emits_one_parseable_historical_free_record(monkeypatch, tmp_path, capsys):
    root = tmp_path / ".dotfiles"
    root.mkdir()
    (root / "one").write_text("fixture")
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Local size JSON contacted model"))

    assert cli.main(["--allow-root", str(root), f"size of {root} as JSON"]) == 0
    record = json.loads(capsys.readouterr().out)
    assert record["tool"] == "directory_usage"
    assert record["status"] == "ok"
    assert "logical file size 7 B" in record["data"]["summary"]


def test_doctor_and_probe_default_to_plain_language_with_explicit_json(monkeypatch, capsys):
    class MockClient:
        def __init__(self, config):
            self.config = config

        def doctor(self):
            return {"model": "fixture-model", "digest": "fixture-digest", "raw": {"private": True}}

    monkeypatch.setattr(cli, "OllamaClient", MockClient)
    assert cli.main(["--doctor"]) == 0
    doctor = capsys.readouterr().out
    assert "No readable result available" in doctor
    assert "fixture-digest" not in doctor and '"raw"' not in doctor
    assert cli.main(["--json", "--doctor"]) == 0
    assert json.loads(capsys.readouterr().out)["data"]["digest"] == "fixture-digest"

    report = {"model": "fixture-model", "digest": "fixture-digest", "cases": 2,
              "passed": 2, "accuracy": 1.0, "target": 0.9, "passed_gate": True,
              "results": [{"id": "one", "passed": True, "seconds": 0.1},
                          {"id": "two", "passed": True, "seconds": 0.2}]}
    monkeypatch.setattr("os_assistant.probe.evaluate", lambda client: report)
    assert cli.main(["--probe"]) == 0
    probe = capsys.readouterr().out
    assert "2/2 cases passed" in probe and "0.300s total" in probe
    assert '"results"' not in probe and "fixture-digest" in probe
    assert cli.main(["--json", "--probe"]) == 0
    assert json.loads(capsys.readouterr().out)["results"] == report["results"]


def test_chat_reset_uses_agent_reset_and_discloses_routing_boundary(monkeypatch, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    instances = []

    class ResetSpy:

        def __init__(self, client, runner, *, on_result=None, json_output=False, details=False):
            self.history = []
            self.reset_called = False
            instances.append(self)

        def reset(self):
            self.reset_called = True
            self.history.clear()

        def compact(self):
            return "Context compacted."

        def show_details(self, *, json_output=False):
            return "No previous tool result to show."

    monkeypatch.setattr(cli, "Agent", ResetSpy)
    monkeypatch.setattr(sys, "stdin", Tty("/reset\n/quit\n"))
    monkeypatch.setattr(sys, "stdout", Tty())
    assert cli.main(["chat"]) == 0
    assert instances[0].reset_called
    assert "(experimental routing; verify results)" in sys.stdout.getvalue()
    assert "\nChat cleared.\n" in sys.stdout.getvalue().replace("You> ", "\n")


def test_direct_and_dry_run_directory_usage_keep_full_diagnostics(tmp_path, capsys):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "fixture-file").write_bytes(b"fixture")
    arguments = '{"root":' + json.dumps(str(root)) + ',"path":"."}'

    assert cli.main(["--json", "--allow-root", str(root), "--tool", "directory_usage", "--arguments", arguments]) == 0
    direct = capsys.readouterr().out
    result = json.loads(direct)
    assert result["tool"] == "directory_usage"
    assert result["data"]["metadata_kind"] == "live_host_metadata_not_snapshot"
    assert "logical_size_human" in result["data"]
    assert "truncated_scan" in result["data"] and "unavailable_entries" in result["data"]

    assert cli.main(["--json", "--allow-root", str(root), "--dry-run", "--tool", "directory_usage", "--arguments", arguments]) == 0
    preview = capsys.readouterr().out
    preview_record = json.loads(preview)
    assert preview_record["tool"] == "directory_usage"
    assert preview_record["status"] == "preview"
    assert "arguments" in preview_record["data"] and "argv" in preview_record["data"]


def test_chat_sizes_alias_then_absolute_path_without_constructing_model(monkeypatch, tmp_path, capsys):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    root = tmp_path / ".dotfiles"
    root.mkdir()
    (root / "payload").write_bytes(b"x" * 37)
    input_stream = Tty(f"size of the ~/.dotfiles folder\nsize of {root} folder\n/quit\n")
    output_stream = Tty()
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Local chat sizing constructed MiniCPM"))
    monkeypatch.setattr(cli, "confirm", lambda call: pytest.fail("Read-only sizing asked for approval"))
    monkeypatch.setattr(sys, "stdin", input_stream)
    monkeypatch.setattr(sys, "stdout", output_stream)

    assert cli.main(["--allow-root", str(root), "chat"]) == 0
    output = output_stream.getvalue()
    flat = _flat(output)
    assert flat.count("-- result · directory_usage") == 2
    assert flat.count(f"{root}: {_allocated(root)} allocated (filtered view).") == 2
    assert "logical file size" not in output
    assert 'tool: "directory_usage"' not in output and "arguments:" not in output and "argv:" not in output
    assert "experimental model routing" not in capsys.readouterr().err


def test_chat_clarifies_multiple_roots_then_sizes_bare_approved_name(monkeypatch, tmp_path):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    first = tmp_path / "first"
    chosen = tmp_path / "chosen"
    first.mkdir()
    chosen.mkdir()
    (first / "payload").write_bytes(b"first")
    (chosen / "payload").write_bytes(b"chosen-fixture")
    input_stream = Tty("size of the folder\nchosen\n/quit\n")
    output_stream = Tty()
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Clarification and size selection should stay local"))
    monkeypatch.setattr(sys, "stdin", input_stream)
    monkeypatch.setattr(sys, "stdout", output_stream)

    assert cli.main(["--allow-root", str(first), "--allow-root", str(chosen), "chat"]) == 0
    output = output_stream.getvalue()
    assert "-- assistant Which approved folder should I measure?" in _flat(output)
    assert _flat(output).count(f"{chosen}: {_allocated(chosen)} allocated (filtered view).") == 1
    assert "I measured" not in output


def test_chat_reset_clears_pending_folder_clarification(monkeypatch, tmp_path):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    root = tmp_path / "chosen"
    root.mkdir()
    client_instances = []

    class GenericClient:
        def __init__(self, config):
            self.calls = []
            client_instances.append(self)

        def chat(self, messages, tools):
            self.calls.append(messages)
            return {"message": {"content": "Post-reset generic answer", "tool_calls": []}}

    output_stream = Tty()
    monkeypatch.setattr(cli, "OllamaClient", GenericClient)
    monkeypatch.setattr(sys, "stdin", Tty("size of the folder\n/reset\nchosen\n/quit\n"))
    monkeypatch.setattr(sys, "stdout", output_stream)

    assert cli.main(["--allow-root", str(root), "--allow-root", str(tmp_path / "another"), "chat"]) == 0
    output = output_stream.getvalue()
    assert "-- assistant Which approved folder should I measure?" in _flat(output)
    assert _flat(output).count("· no tools ran Post-reset generic answer") == 1
    assert len(client_instances) == 1 and len(client_instances[0].calls) == 1
    assert client_instances[0].calls[0][-1]["content"] == "chosen"
    assert len(client_instances[0].calls[0]) == 2  # system + current user; reset dropped prior turns


def test_chat_context_commands_are_local_and_details_do_not_rescan(monkeypatch, tmp_path):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    root = tmp_path / "facts"
    root.mkdir()
    (root / "fixture").write_bytes(b"fixture-only")
    scans = []
    original = cli.Policy.directory_usage

    def count_scan(policy, call):
        scans.append(call)
        return original(policy, call)

    monkeypatch.setattr(cli.Policy, "directory_usage", count_scan)
    requests = Tty(f"size of {root} folder\n/details\n/json\nshow JSON\n/compact\n/clear\n/quit\n")
    output = Tty()
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Local commands constructed a model client"))
    monkeypatch.setattr(sys, "stdin", requests)
    monkeypatch.setattr(sys, "stdout", output)

    assert cli.main(["--allow-root", str(root), "chat"]) == 0
    text = output.getvalue()
    assert _flat(text).count("-- result · directory_usage") == 1
    assert "allocated" in text and str(root) in _flat(text)
    assert "historical" in text.lower()
    historical_lines = [line for line in text.splitlines() if '"historical"' in line]
    assert len(historical_lines) == 2
    for line in historical_lines:
        historical = json.loads(line[line.index("{"):])
        assert historical["historical"] is True and historical["new_execution"] is False
    assert "You> Context compacted.\n" in text
    assert "\nChat cleared." in text.replace("You> ", "\n")
    assert len(scans) == 1


def test_natural_size_dry_run_previews_without_scanning_or_implying_execution(monkeypatch, tmp_path, capsys):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "payload").write_bytes(b"must not be scanned")
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("Dry-run local size should not construct MiniCPM"))
    monkeypatch.setattr("os_assistant.policy.Policy.directory_usage", lambda *args: pytest.fail("Dry-run scanned filesystem"))
    monkeypatch.setattr(cli, "confirm", lambda call: pytest.fail("Read-only dry-run requested approval"))

    assert cli.main(["--allow-root", str(root), "--dry-run", f"size of {root} folder"]) == 0
    output = capsys.readouterr().out
    assert "directory usage" in output
    assert str(root) in output
    assert "tool:" not in output and "arguments:" not in output and "argv:" not in output
    assert "Preview only; no folder was scanned." in output
    assert "── preview · nothing executed" in output
    assert "Measuring folder size" not in output
    assert "Scan completed" not in output


def test_local_size_requests_around_generic_chat_construct_client_once(monkeypatch, tmp_path):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    root = tmp_path / ".dotfiles"
    root.mkdir()
    (root / "payload").write_bytes(b"generic interleave fixture")
    clients = []

    class GenericClient:
        def __init__(self, config):
            self.calls = []
            clients.append(self)

        def chat(self, messages, tools):
            self.calls.append((messages, tools))
            return {"message": {"content": "Generic answer from fake client", "tool_calls": []}}

    output_stream = Tty()
    monkeypatch.setattr(cli, "OllamaClient", GenericClient)
    monkeypatch.setattr(sys, "stdin", Tty(f"size of the ~/.dotfiles folder\nTell me hello\nsize of {root} folder\n/quit\n"))
    monkeypatch.setattr(sys, "stdout", output_stream)

    assert cli.main(["--allow-root", str(root), "chat"]) == 0
    output = output_stream.getvalue()
    assert len(clients) == 1 and len(clients[0].calls) == 1
    assert _flat(output).count(f"{root}: {_allocated(root)} allocated (filtered view).") == 2
    assert _flat(output).count("· no tools ran Generic answer from fake client") == 1
    assert 'tool: "directory_usage"' not in output


def test_web_search_disabled_is_denied(monkeypatch):
    monkeypatch.setattr("os_assistant.websearch.search", lambda *args: pytest.fail("searched while disabled"))
    assert cli.main(["--tool", "web_search", "--arguments", '{"query":"x"}']) == 3


def test_web_search_requires_interactive_approval(tmp_path, monkeypatch):
    config = tmp_path / "settings.toml"
    config.write_text("[web_search]\nenabled = true\n")
    monkeypatch.setattr(sys, "stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("os_assistant.websearch.search", lambda *args: pytest.fail("searched without approval"))
    assert cli.main(["--config", str(config), "--tool", "web_search", "--arguments", '{"query":"x"}']) == 3


def _fake_agent(**changes):
    from types import SimpleNamespace
    values = dict(last_results=[], last_answer_kind="model", last_answer_is_summary=False, last_answer_web=False,
                  last_compacted=False, last_status="ok", last_answer_format="text",
                  runner=SimpleNamespace(policy=SimpleNamespace(config=SimpleNamespace(model="m1"))))
    values.update(changes)
    return SimpleNamespace(**values)


def _result(name, status="ok"):
    from os_assistant.contracts import ToolResult
    return ToolResult(name, status, {})


@pytest.mark.parametrize("changes, header", [
    ({"last_answer_kind": "tool", "last_results": [_result("system_status"), _result("system_status"), _result("battery")]},
     "result · system_status, battery"),
    ({}, "m1 · no tools ran"),
    ({"last_answer_is_summary": True, "last_results": [_result("bash")]}, "m1 · summary of read-only output"),
    ({"last_answer_is_summary": True, "last_answer_web": True, "last_results": [_result("web_search")]},
     "m1 · web summary (unverified)"),
    ({"last_answer_kind": "local"}, "assistant"),
    ({"last_answer_kind": "tool", "last_results": [_result("bash", "preview")]}, "preview · nothing executed"),
    ({"last_compacted": True}, "m1 · no tools ran · context compacted"),
])
def test_answer_header_selection(changes, header):
    assert cli.answer_header(_fake_agent(**changes), "m1") == header


def test_stopped_answers_use_stopped_header(monkeypatch):
    agent = _fake_agent(last_answer_kind="tool", last_status="denied", last_results=[_result("bash", "denied")])
    agent.ask = lambda request: "Stopped: not approved."
    out = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    cli.ask_and_explain(agent, "x")
    assert out.getvalue() == "-- stopped\n  Stopped: not approved.\n"


@pytest.mark.parametrize("full, short", [
    ("qwen3:4b-instruct-2507-q4_K_M", "qwen3:4b"),
    ("openbmb/minicpm5-2b:latest", "minicpm5-2b"),
    ("qwen3.5:2b-q4_K_M", "qwen3.5:2b"),
    ("llama3.2:3b", "llama3.2:3b"),
])
def test_short_model_display_name(full, short):
    assert cli.short_model(full) == short


def test_chat_blank_line_after_each_turn(monkeypatch):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    class GenericClient:
        def __init__(self, config):
            pass

        def chat(self, messages, tools):
            return {"message": {"content": "hi", "tool_calls": []}}

    out = Tty()
    monkeypatch.setattr(cli, "OllamaClient", GenericClient)
    monkeypatch.setattr(sys, "stdin", Tty("hello\n/quit\n"))
    monkeypatch.setattr(sys, "stdout", out)
    assert cli.main(["chat"]) == 0
    assert "  hi\n\nYou> " in out.getvalue()

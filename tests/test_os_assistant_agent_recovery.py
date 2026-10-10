"""Pre-execution model correction is bounded and never widens tool policy."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.agent import Agent
from os_assistant.config import Config
from os_assistant.contracts import ModelError, PolicyError, ToolResult
from os_assistant.policy import Policy


def call(name="system_status", arguments=None, **metadata):
    return {"function": {"name": name, "arguments": {} if arguments is None else arguments}, **metadata}


def response(*calls, content=""):
    return {"message": {"content": content, "tool_calls": list(calls)}}


class Client:
    def __init__(self, *responses):
        self.responses = iter(responses)
        self.requests = []

    def chat(self, messages, tools):
        self.requests.append((list(messages), tools))
        return next(self.responses)


class FakeRunner:
    """Use real validation/preparation but never perform an OS operation."""

    def __init__(self, config=None, *, result_status="ok", result_data=None):
        self.policy = Policy(config or Config())
        self.result_status = result_status
        self.result_data = result_data or {"available_bytes": 123}
        self.executed = []

    def run(self, prepared):
        self.executed.append(prepared)
        return ToolResult(prepared.name, self.result_status, dict(self.result_data))


def function_of(messages, index):
    return messages[index]["tool_calls"][0]["function"]


@pytest.mark.parametrize(
    "malformed",
    [call("processes", {"unexpected": "private-value"}), call("processes", {})],
    ids=["unknown-field", "missing-field"],
)
def test_single_schema_error_corrected_once_then_success(malformed):
    runner = FakeRunner(Config(actions_enabled=True))
    malformed = call("set_volume", malformed["function"]["arguments"])
    client = Client(response(malformed), response(call("set_volume", {"percent": 3})), response(content="Done"))

    assert Agent(client, runner).ask("Request volume 3 percent") == "Done"

    assert [item.name for item in runner.executed] == ["set_volume"]
    assert runner.executed[0].argument_dict()["percent"] == 3
    assert len(client.requests) == 3
    correction = client.requests[1][0][-1]
    assert correction["role"] == "system"
    assert "Correct the proposal once" in correction["content"]
    assert "private-value" not in correction["content"]


def test_second_malformed_proposal_raises_without_execution():
    runner = FakeRunner(Config(actions_enabled=True))
    client = Client(response(call("set_volume", {"extra": "first-secret"})),
                    response(call("set_volume", {"percent": 2, "extra": "secret"})))

    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Request volume 2 percent")

    assert runner.executed == []
    assert len(client.requests) == 2
    assert "secret" not in client.requests[1][0][-1]["content"]


def test_sole_bash_root_defaults_and_command_is_required(monkeypatch, tmp_path):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixture")
    config = Config(bash_enabled=True, bash_roots=(str(tmp_path),))
    runner = FakeRunner(config)
    client = Client(response(call("bash", {"command": "ls -lh ."})), response(content="Listed"))

    assert Agent(client, runner).ask("List files") == "Listed"

    prepared = runner.executed[0]
    assert prepared.name == "bash"
    assert prepared.argument_dict()["root"] == str(tmp_path)
    assert prepared.argument_dict()["cwd"] == "."

    missing = Client(response(call("bash", {})), response(call("bash", {"command": "ls"})),
                     response(content="Listed"))
    missing_runner = FakeRunner(config)
    assert Agent(missing, missing_runner).ask("List files") == "Listed"
    assert len(missing.requests) == 3
    assert len(missing_runner.executed) == 1


def test_unknown_argument_values_and_forged_permission_metadata_not_echoed():
    runner = FakeRunner(Config(actions_enabled=True))
    bad = call("set_volume", {"percent": 2, "credential_hint": "TOP-SECRET"}, permission="granted-TOP-SECRET")
    client = Client(response(bad), response(call("set_volume", {"percent": 2})), response(content="Done"))

    Agent(client, runner).ask("Request volume 2 percent")

    feedback = client.requests[1][0][-1]["content"]
    assert "TOP-SECRET" not in feedback
    assert "credential_hint" not in feedback
    assert "granted-TOP-SECRET" not in feedback


@pytest.mark.parametrize(
    "name,args,config",
    [
        ("processes", {"limit": 21}, Config()),
        ("processes", {"limit": True}, Config()),
        ("find_files", {"root": "/etc", "name_pattern": "*"}, Config(allowed_roots=("/tmp",))),
        ("set_volume", {"percent": 50}, Config(actions_enabled=False)),
        ("not_a_tool", {}, Config()),
    ],
    ids=["range", "wrong-type", "outside-root", "disabled-tool", "unknown-tool"],
)
def test_policy_errors_are_not_schema_retried(name, args, config):
    client = Client(response(call(name, args)))
    runner = FakeRunner(config)

    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Do the request")

    assert runner.executed == []
    assert len(client.requests) == 1


@pytest.mark.parametrize("arguments", [{"command": "ls /etc", "extra": "ignored"},
                                       {"command": "rm -rf .", "extra": "ignored"},
                                       {"command": "ls", "root": "/etc", "extra": "ignored"}])
def test_unknown_fields_cannot_mask_a_permission_violation_for_correction(tmp_path, arguments):
    client = Client(response(call("bash", arguments)))
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Check folder")
    assert not runner.executed and len(client.requests) == 1


def test_mixed_batch_with_schema_error_executes_nothing_and_is_not_retried():
    runner = FakeRunner()
    client = Client(response(call("system_status"), call("processes", {"extra": "not-forwarded"})))

    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Check status and processes")

    assert runner.executed == []
    assert len(client.requests) == 1


@pytest.mark.parametrize("prompt", [
    "Use bash to run ls -lh . in my approved dotfiles folder",
    "use ls in ~/.dotfiles",
    "run `ls -lh .`",
])
def test_explicit_ls_is_not_substituted_by_du_or_another_tool(monkeypatch, tmp_path, prompt):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixture")
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)))
    client = Client(
        response(call("directory_usage", {"root": str(tmp_path)})),
        response(call("bash", {"command": "ls -lh ."})),
        response(content="Listed"),
    )

    assert Agent(client, runner).ask(prompt) == "Listed"

    assert len(runner.executed) == 1
    assert runner.executed[0].name == "bash"
    assert runner.executed[0].argument_dict()["command"] == "ls -lh ."
    assert len(client.requests) == 3
    assert "explicitly requested ls" in client.requests[1][0][-1]["content"]


@pytest.mark.parametrize("command", ["echo hello", "printf '%s\\n' hello"])
def test_explicit_echo_and_printf_guard_uses_source_command(monkeypatch, tmp_path, command):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixture")
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)))
    client = Client(response(call("bash", {"command": command})), response(content="Printed"))

    assert Agent(client, runner).ask(f"run `{command}`").startswith("Printed")

    assert len(runner.executed) == 1
    assert runner.executed[0].name == "bash"
    assert bash.plan(runner.policy.config, runner.executed[0].argument_dict()).stages[0][0] == "/usr/bin/printf"


@pytest.mark.parametrize("prompt", ["Do not run rm scratch; explain folder sizes.",
                                  "Never use ls; explain logical versus allocated size.",
                                  "Explain what `du -sh .` does.", "What happens when you run `ls`?"])
def test_intent_guard_does_not_turn_negation_or_examples_into_execution_instructions(prompt):
    from os_assistant.agent import requested_command
    assert requested_command(prompt) == ""


@pytest.mark.parametrize("command", ["du /etc/passwd", "ls /etc/passwd", "ls -nonsense .", "ls .; whoami"])
def test_unsafe_or_outside_bash_proposal_is_not_repaired(monkeypatch, tmp_path, command):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixture")
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)))
    client = Client(response(call("bash", {"command": command})))

    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Run a safe bounded command")

    assert runner.executed == []
    assert len(client.requests) == 1


def test_folder_clarification_then_home_alias_uses_current_turn_and_default_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    approved = tmp_path / ".dotfiles"
    approved.mkdir()
    config = Config(allowed_roots=(str(approved),))
    runner = FakeRunner(config, result_data={"metadata_kind": "live_host_metadata_not_snapshot", "summary": "size summary"})
    client = Client(response(content="Which folder?"), response(call("directory_usage", {"root": "~/.dotfiles"})))
    agent = Agent(client, runner)

    # A complex request stays on the model path; clear size requests now bypass it.
    assert agent.ask("Check folder size and report its largest subfolders") == "Which folder?"
    assert agent.ask("~/.dotfiles") == "size summary"

    prepared = runner.executed[0]
    assert prepared.name == "directory_usage"
    assert prepared.argument_dict()["root"] == str(approved)
    assert prepared.argument_dict()["path"] == "."
    second_prompt = client.requests[1][0][-1]
    assert second_prompt == {"role": "user", "content": "~/.dotfiles"}


def test_failed_turn_is_remembered_as_safe_stop_not_stale_request():
    runner = FakeRunner()
    client = Client(response(call("processes", {"limit": 500})), response(content="Clarified"))
    agent = Agent(client, runner)

    with pytest.raises(PolicyError):
        agent.ask("Show every process")
    assert agent.history[-1] == {
        "role": "assistant",
        "content": "The previous turn stopped on an error. Do not assume an action ran or succeeded.",
    }
    assert agent.ask("What about memory?") == "Clarified"
    prior_turns = client.requests[1][0]
    assert {"role": "user", "content": "Show every process"} in prior_turns
    assert prior_turns[-2]["content"] == "The previous turn stopped on an error. Do not assume an action ran or succeeded."
    assert agent.history[-2:] == [
        {"role": "user", "content": "What about memory?"},
        {"role": "assistant", "content": "Clarified"},
    ]


def test_deterministic_live_size_summary_stops_without_second_model_call():
    data = {"metadata_kind": "live_host_metadata_not_snapshot", "summary": "deterministic summary"}
    runner = FakeRunner(Config(allowed_roots=("/tmp",)), result_data=data)
    client = Client(response(call("directory_usage", {"root": "/tmp"})))

    assert Agent(client, runner).ask("Check folder size and report its largest subfolders") == "deterministic summary"
    assert len(client.requests) == 1
    assert [result.name for result in runner.executed] == ["directory_usage"]


def test_session_context_defines_this_directory_as_approved_root_not_home(tmp_path):
    from os_assistant.agent import default_folder, system_context
    config = Config(bash_enabled=True, bash_roots=(str(tmp_path),))
    assert default_folder(config) == str(tmp_path)
    context = system_context(config)
    assert '"default_approved_folder":' in context and str(tmp_path) in context
    assert "Do not substitute HOME" in context and "recursive size use directory_usage" in context
    assert default_folder(Config(allowed_roots=("/srv/a", "/srv/b"))) is None
    assert "No default approved folder" in system_context(Config())


def test_session_folder_alias_facts_match_real_home_normalization_without_expanding_access(tmp_path, monkeypatch):
    from os_assistant.agent import system_context
    monkeypatch.setenv("HOME", str(tmp_path))
    folder = tmp_path / ".dotfiles"
    folder.mkdir()
    config = Config(bash_enabled=True, bash_roots=(str(folder),))
    context = system_context(config)
    assert '"approved_folder_aliases": {"~/.dotfiles":' in context
    assert str(folder) in context and "not the whole home" in context
    assert Policy(config).prepare("directory_usage", {"root": "~/.dotfiles"}).argument_dict()["root"] == str(folder)
    with pytest.raises(PolicyError):
        Policy(config).prepare("directory_usage", {"root": "~/"})
    outside = Config(allowed_roots=("/srv/shared",))
    assert "approved_folder_aliases" not in system_context(outside)


def test_successful_snapshot_read_stops_before_model_can_repeat_or_invent_counts(monkeypatch, tmp_path):
    import os_assistant.bash as bash
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: "fixture")
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)),
                        result_data={"executor": "read_only_bubblewrap_snapshot",
                                     "stdout": "ordinary names", "truncated_snapshot": False})
    client = Client(response(call("bash", {"command": "ls -lh ."})))
    agent = Agent(client, runner)
    answer = agent.ask("Use bash to run ls -lh .")
    assert "ordinary names" in answer and "filtered snapshot" in answer
    assert agent.last_answer_kind == "tool" and len(client.requests) == 1


def test_partial_snapshot_read_summary_retains_incomplete_coverage(monkeypatch, tmp_path):
    import os_assistant.bash as bash
    monkeypatch.setattr(bash, "verification", lambda *a, **kw: "fixture")
    runner = FakeRunner(Config(bash_enabled=True, bash_roots=(str(tmp_path),)),
                        result_data={"executor": "read_only_bubblewrap_snapshot", "truncated_snapshot": True})
    agent = Agent(Client(response(call("bash", {"command": "find . -type f"}))), runner)
    assert "incomplete" in agent.ask("Run find . -type f").lower()
    assert len(runner.executed) == 1


@pytest.mark.parametrize("status", ["denied", "error", "preview"])
def test_denied_error_and_preview_never_receive_correction(status):
    runner = FakeRunner(result_status=status)
    client = Client(response(call()), response(call("system_status", {"bad": "value"})))
    agent = Agent(client, runner)

    if status == "denied" or status == "error":
        assert "Stopped" in agent.ask("Check status")
        assert len(client.requests) == 1
    else:
        assert "Preview only" in agent.ask("Check status")
        assert len(client.requests) == 1
        assert agent.last_status == "preview"
    assert len(runner.executed) == 1


def test_correction_turn_does_not_increase_executed_tool_budget():
    runner = FakeRunner(Config(max_steps=1))
    client = Client(response(call("processes", {"extra": "bad"})),
                    response(call("system_status")), response(call("system_status")))

    with pytest.raises(ModelError, match="budget"):
        Agent(client, runner).ask("Check status")

    assert len(client.requests) == 3
    assert [item.name for item in runner.executed] == ["system_status"]

"""Literal command intent is preserved without running real OS tools or a model."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.agent import Agent
from os_assistant.config import Config
from os_assistant.contracts import PolicyError, ToolResult
from os_assistant.policy import Policy


def call(command, *, cwd=".", root=None):
    arguments = {"command": command, "cwd": cwd}
    if root is not None:
        arguments["root"] = root
    return {"function": {"name": "bash", "arguments": arguments}}


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
    """Use real Policy preparation, but never execute a prepared tool call."""

    def __init__(self, config):
        self.policy = Policy(config)
        self.executed = []

    def run(self, prepared):
        self.executed.append(prepared)
        return ToolResult(prepared.name, "ok", {"fixture": True})


@pytest.fixture
def bash_config(tmp_path):
    return Config(bash_enabled=True, bash_roots=(str(tmp_path),))


@pytest.fixture
def no_probe(monkeypatch):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixed-fixture-verification")


@pytest.mark.parametrize("prompt,expected", [
    ("Run `ls -lh .`", "ls -lh ."),
    ("Please execute `find . -type f | head -n 3`", "find . -type f | head -n 3"),
    ("Use bash to run ls -lh . in my approved dotfiles folder", "ls -lh ."),
    ("Execute echo hello > note.txt in the approved folder", "echo hello > note.txt"),
    ("Run cp 'one file' 'two file' in this directory", "cp 'one file' 'two file'"),
])
def test_literal_parser_extracts_only_supported_leading_command(prompt, expected):
    from os_assistant.intent import literal_command

    assert literal_command(prompt) == expected


@pytest.mark.parametrize("prompt,expected", [
    ('Run echo "in my approved dotfiles folder"', 'echo "in my approved dotfiles folder"'),
    ("Run echo 'in my approved dotfiles folder'", "echo 'in my approved dotfiles folder'"),
])
def test_folder_suffix_inside_quotes_is_not_stripped(prompt, expected):
    from os_assistant.intent import literal_command

    assert literal_command(prompt) == expected


@pytest.mark.parametrize("prompt", [
    "Run ls and then explain what it would show",
    "Run ls if the folder exists",
    "Run ls; then run pwd",
    "Do not run ls; explain what it does",
    "Please explain: run `ls`",
    "Run `ls` or `pwd`",
    "In general, one might run ls",
])
def test_explanatory_negated_conditional_or_ambiguous_prose_has_no_literal(prompt):
    from os_assistant.intent import literal_command

    assert literal_command(prompt) is None


def test_unquoted_command_keeps_final_period_as_filename_character():
    from os_assistant.intent import literal_command

    assert literal_command("Run ls note.txt.") == "ls note.txt."


@pytest.mark.parametrize("prompt,expected", [
    ("Run `cat README.md` to display its contents.", "cat README.md"),
    ("Execute `find . -type f` and explain the output.", "find . -type f"),
    ("Run `ls .` if the folder exists.", None),
    ("Run `ls .` and then execute pwd.", None),
])
def test_backticked_command_allows_output_explanation_but_not_conditional_extra_actions(prompt, expected):
    from os_assistant.intent import literal_command
    assert literal_command(prompt) == expected


def test_original_unquoted_pipeline_request_cannot_lose_head_stage(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    wanted = "ls -lh . | head -n 5"
    client = Client(response(call("ls -lh .")), response(call(wanted)), response(content="Listed five entries."))
    assert Agent(client, runner).ask("Run ls -lh . | head -n 5 in my approved dotfiles folder.") == "Listed five entries."
    assert [item.argument_dict()["command"] for item in runner.executed] == [wanted]
    assert len(client.requests) == 3


@pytest.mark.parametrize("command,expected", [
    ("du -sb .", "8192 B logical (filtered view)."),
    ("du -sk .", "4 KiB allocated (filtered view)."),
    ("du -sh .", "4.0 KiB allocated (filtered view)."),
    ("du --apparent-size -sk .", "8 KiB logical (filtered view)."),
])
def test_directory_adapter_preserves_literal_du_units_and_metric(bash_config, no_probe, command, expected):
    runner = FakeRunner(bash_config)
    def run(prepared):
        runner.executed.append(prepared)
        args = prepared.argument_dict()
        return ToolResult(prepared.name, "ok", {
            "root": args["root"], "path": args["path"], "metadata_kind": "live_host_metadata_not_snapshot",
            "total_size_bytes": 8192, "allocated_size_bytes": 4096, "files_scanned": 2,
            "truncated_scan": False, "summary": "DO NOT USE THIS LEGACY SUMMARY",
        })
    runner.run = run
    client = Client(response({"function": {"name": "directory_usage", "arguments": {"root": bash_config.bash_roots[0]}}}))
    agent = Agent(client, runner)
    assert agent.ask("Run `" + command + "`") == expected
    assert agent.last_answer_kind == "tool" and len(client.requests) == 1 and len(runner.executed) == 1
    assert expected in agent.show_details()


def test_in_root_absolute_operand_is_equivalent_without_silent_rewriting(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    absolute = str(Path(bash_config.bash_roots[0]) / "file.txt")
    proposal = f"head -n 2 {absolute}"
    client = Client(response(call(proposal)), response(content="Displayed."))
    assert Agent(client, runner).ask("Run `head -n 2 file.txt`") == "Displayed."
    assert runner.executed[0].argument_dict()["command"] == proposal
    assert len(client.requests) == 2


def test_literal_source_command_name_is_preserved_even_with_explanation_suffix(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    client = Client(response(call("printf '%s\\n' hello")), response(call("echo hello")), response(content="Printed."))
    assert Agent(client, runner).ask("Run `echo hello` and explain the output.") == "Printed."
    assert [item.argument_dict()["command"] for item in runner.executed] == ["echo hello"]
    assert len(client.requests) == 3


@pytest.mark.parametrize("proposal", [
    "find . -type f",
    "find . -type f | head -n 4",
    "head -n 3 | find . -type f",
    "find . -type f | head -n 3 | head -n 3",
])
def test_pipeline_literal_mismatch_gets_one_correction_before_any_execution(
    bash_config, no_probe, proposal
):
    requested = "find . -type f | head -n 3"
    runner = FakeRunner(bash_config)
    client = Client(
        response(call(proposal)),
        response(call(requested)),
        response(content="Corrected."),
    )

    assert Agent(client, runner).ask(f"Run `{requested}`") == "Corrected."
    assert [c.argument_dict()["command"] for c in runner.executed] == [requested]
    assert len(client.requests) == 3
    assert "Pre-execution correction" in client.requests[1][0][-1]["content"]


@pytest.mark.parametrize("requested,proposal", [
    ("ls -lh .", "ls -l ."),
    ("ls -lh .", "ls -lh subdir"),
    ("ls -lh .", "ls -lh . -a"),
])
def test_ls_flag_target_and_extra_command_changes_are_not_authorized(
    bash_config, no_probe, requested, proposal
):
    runner = FakeRunner(bash_config)
    client = Client(response(call(proposal)), response(content="I cannot preserve that command."))
    assert Agent(client, runner).ask(f"Run `{requested}`") == "I cannot preserve that command."
    assert runner.executed == []
    assert len(client.requests) == 2


def test_parent_target_is_rejected_by_policy_without_correction(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    client = Client(response(call("ls -hl ..")), response(call("ls -lh .")))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Run `ls -lh .`")
    assert runner.executed == []
    assert len(client.requests) == 1


@pytest.mark.parametrize("requested,proposal", [("pwd", "pwd -P"), ("ls subdir", "ls .")])
def test_cwd_or_option_mismatch_is_corrected_before_execution(bash_config, no_probe, requested, proposal):
    runner = FakeRunner(bash_config)
    client = Client(response(call(proposal, cwd="subdir" if requested == "pwd" else ".")),
                    response(call(requested)), response(content="Corrected."))
    answer = Agent(client, runner).ask(f"Run `{requested}`")
    assert answer == "Corrected."
    assert len(runner.executed) == 1
    assert runner.executed[0].argument_dict()["command"] == requested
    assert len(client.requests) == 3


def test_shell_quote_equivalent_is_executed_as_proposed_without_correction(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    proposal = 'ls "a b"'
    client = Client(response(call(proposal)), response(content="Listed."))
    assert Agent(client, runner).ask("Run `ls 'a b'`") == "Listed."
    assert len(runner.executed) == 1
    assert runner.executed[0].argument_dict()["command"] == proposal
    assert len(client.requests) == 2


def test_safe_ls_short_switch_group_order_is_equivalent(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    client = Client(response(call("ls -hl .")), response(content="Listed."))
    assert Agent(client, runner).ask("Run `ls -lh .`") == "Listed."
    assert len(runner.executed) == 1
    assert len(client.requests) == 2


def test_command_key_normalizes_only_safe_ls_switch_order_and_preserves_other_order(bash_config):
    import os_assistant.bash as bash
    from os_assistant.intent import command_key

    root = bash_config.bash_roots[0]
    plan = lambda command: bash.plan(bash_config, {"root": root, "command": command})
    assert command_key(plan("ls -lh .")) == command_key(plan("ls -hl ."))
    assert command_key(plan("ls -t -S .")) != command_key(plan("ls -S -t ."))
    assert command_key(plan("head -n 3 .")) != command_key(plan("head -n 4 ."))


def test_unsupported_shell_chain_is_not_repaired_as_a_safe_mismatch(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    client = Client(response(call("ls .; pwd")), response(call("ls -lh .")))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Run `ls -lh .`")
    assert runner.executed == []
    assert len(client.requests) == 1


@pytest.mark.parametrize("requested,proposal", [
    ("echo secret > note.txt", "echo secret > other.txt"),
    ("echo secret >> note.txt", "echo changed >> note.txt"),
    ("cp source destination", "cp source other"),
    ("mv source destination", "mv other destination"),
    ("rm target", "rm other"),
])
def test_mutation_text_operation_and_every_operand_are_exact_intent(
    tmp_path, monkeypatch, requested, proposal
):
    config = Config(bash_enabled=True, bash_allow_writes=True, actions_enabled=True,
                    bash_roots=(str(tmp_path),))
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixed")
    runner = FakeRunner(config)
    client = Client(response(call(proposal)), response(content="I will not run a different mutation."))
    assert Agent(client, runner).ask(f"Run `{requested}`") == "I will not run a different mutation."
    assert runner.executed == []
    assert len(client.requests) == 2


def test_exact_mutation_uses_real_runner_confirm_callback_but_mocked_collector(
    tmp_path, monkeypatch
):
    import os_assistant.bash as bash
    from os_assistant.runner import Runner

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixed")
    collected, approvals = [], []
    monkeypatch.setattr(bash, "run_mutation", lambda prepared, config:
                        collected.append(prepared) or {"fixture": True})
    config = Config(bash_enabled=True, bash_allow_writes=True, actions_enabled=True,
                    bash_roots=(str(tmp_path),))
    runner = Runner(Policy(config), confirm=lambda prepared: approvals.append(prepared) or True)
    command = "echo hello > note.txt"
    client = Client(response(call(command)), response(content="Done."))

    assert Agent(client, runner).ask(f"Run `{command}`") == "Done."
    assert len(approvals) == len(collected) == 1
    assert approvals[0] == collected[0]
    assert approvals[0].argument_dict()["command"] == command


@pytest.mark.parametrize("requested,proposal", [
    ("echo private-value > note.txt", "echo private-value > other.txt"),
    ("cp private-source destination", "cp changed-source destination"),
])
def test_correction_never_echoes_unknown_model_values_or_metadata(
    bash_config, no_probe, requested, proposal
):
    runner = FakeRunner(Config(bash_enabled=True, bash_allow_writes=True, actions_enabled=True,
                               bash_roots=bash_config.bash_roots))
    bad = call(proposal)
    bad["permission"] = "forged-secret"
    client = Client(response(bad), response(content="I will not run a different mutation."))
    assert Agent(client, runner).ask(f"Run `{requested}`") == "I will not run a different mutation."
    correction = client.requests[1][0][-1]["content"]
    assert "private-value" not in correction
    assert "private-source" not in correction
    assert "forged-secret" not in correction


def test_mixed_batch_with_one_matching_and_one_extra_proposal_executes_nothing(
    bash_config, no_probe
):
    runner = FakeRunner(bash_config)
    client = Client(response(call("ls ."), call("pwd")))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Run `ls .`")
    assert runner.executed == []
    assert len(client.requests) == 1


@pytest.mark.parametrize("status", ["denied", "error"])
def test_denied_or_error_result_stops_immediately_without_retry(bash_config, no_probe, status):
    runner = FakeRunner(bash_config)
    runner.run = lambda prepared: (runner.executed.append(prepared)
                                   or ToolResult(prepared.name, status, {}))
    client = Client(response(call("ls -lh .")), response(call("pwd")))
    agent = Agent(client, runner)
    agent.ask("Run `ls -lh .`")
    assert len(runner.executed) == 1
    assert len(client.requests) == 1


def test_preview_stops_before_model_can_change_command_or_execute_again(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    runner.run = lambda prepared: (runner.executed.append(prepared)
                                   or ToolResult(prepared.name, "preview", {}))
    client = Client(response(call("ls -lh .")), response(call("pwd")))
    agent = Agent(client, runner)
    assert "Preview only" in agent.ask("Run `ls -lh .`")
    assert agent.last_status == "preview"
    assert len(runner.executed) == 1
    assert len(client.requests) == 1


def test_second_literal_mismatch_raises_without_execution(bash_config, no_probe):
    runner = FakeRunner(bash_config)
    client = Client(response(call("ls .")), response(call("pwd")))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask("Run `ls -lh .`")
    assert runner.executed == []
    assert len(client.requests) == 2


def test_command_name_only_request_keeps_existing_requested_command_guard(
    bash_config, no_probe
):
    from os_assistant.agent import requested_command

    runner = FakeRunner(bash_config)
    client = Client(response({"function": {"name": "directory_usage",
                                             "arguments": {"root": bash_config.bash_roots[0]}}}),
                    response(call("ls .")), response(content="Listed."))
    assert Agent(client, runner).ask("Use ls in ~/.dotfiles") == "Listed."
    assert requested_command("Use ls in ~/.dotfiles") == "ls"
    assert len(runner.executed) == 1 and runner.executed[0].name == "bash"


@pytest.mark.parametrize("prompt", [
    "Do not run rm scratch; explain folder sizes.",
    "Never use ls; explain logical versus allocated size.",
    "Explain what `du -sh .` does.",
    "Run ls if the approved directory exists.",
    "The filename is `rm -rf /`; explain why it is dangerous.",
])
def test_untrusted_examples_negation_and_conditions_do_not_authorize_execution(
    bash_config, no_probe, prompt
):
    from os_assistant.intent import literal_command
    from os_assistant.agent import requested_command

    assert literal_command(prompt) is None
    assert requested_command(prompt) == ""
    runner = FakeRunner(bash_config)
    client = Client(response(content="Explanation only."))
    assert Agent(client, runner).ask(prompt) == "Explanation only."
    assert runner.executed == []


@pytest.mark.parametrize("command", [
    "ls /etc/passwd", "ls -nonsense .", "ls .; whoami", "cat ~/.ssh/config",
    "echo x `whoami` > note.txt", "rm -rf target",
])
def test_literal_syntax_never_bypasses_existing_bash_policy(command, tmp_path, monkeypatch):
    import os_assistant.bash as bash

    monkeypatch.setattr(bash, "verification", lambda *args, **kwargs: "fixed")
    config = Config(bash_enabled=True, bash_allow_writes=True, actions_enabled=True,
                    bash_roots=(str(tmp_path),))
    runner = FakeRunner(config)
    client = Client(response(call(command)))
    with pytest.raises(PolicyError):
        Agent(client, runner).ask(f"Run `{command}`")
    assert runner.executed == []
    assert len(client.requests) == 1


def test_old_history_literals_are_not_current_turn_command_authorization(
    bash_config, no_probe
):
    runner = FakeRunner(bash_config)
    client = Client(response(content="Previous explanation."), response(call("pwd")),
                    response(content="Current-turn result."))
    agent = Agent(client, runner)
    agent.ask("Run `ls -lh .`")
    assert agent.ask("What does that command mean?")
    assert [call.argument_dict()["command"] for call in runner.executed] == ["pwd"]
    assert len(client.requests) == 3

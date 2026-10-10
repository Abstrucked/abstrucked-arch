"""Natural-language folder sizing is deterministic and never depends on tool-call copying."""

from dataclasses import replace
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.agent import Agent
from os_assistant.config import Config
from os_assistant.contracts import PolicyError
from os_assistant.policy import Policy
from os_assistant.runner import Runner


class NoModel:
    def __init__(self):
        self.requests = []

    def chat(self, messages, tools):
        self.requests.append((messages, tools))
        pytest.fail("A deterministic folder-size request must not invoke the model")


class ChatClient:
    def __init__(self, answer="I can help with that."):
        self.answer = answer
        self.requests = []

    def chat(self, messages, tools):
        self.requests.append((messages, tools))
        return {"message": {"content": self.answer, "tool_calls": []}}


def make_config(*, roots=(), bash_roots=(), **values):
    return replace(Config(), allowed_roots=tuple(map(str, roots)),
                   bash_roots=tuple(map(str, bash_roots)), bash_enabled=bool(bash_roots), **values)


def size_agent(config):
    policy = Policy(config)
    model = NoModel()
    emitted = []
    agent = Agent(model, Runner(policy), on_result=emitted.append)
    return agent, model, emitted


def test_common_dotfiles_requests_run_real_scoped_metadata_without_model(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".dotfiles"
    root.mkdir()
    (root / "payload").write_bytes(b"x" * 37)
    config = make_config(roots=(root,))
    agent, model, emitted = size_agent(config)

    alias_answer = agent.ask("size of the ~/.dotfiles folder")
    absolute_answer = agent.ask(f"size of {root} folder")

    assert [result.name for result in emitted] == ["directory_usage", "directory_usage"]
    assert all(result.status == "ok" and result.data["total_size_bytes"] == 37 for result in emitted)
    assert str(root) in alias_answer and str(root) in absolute_answer
    assert "allocated" in alias_answer.lower() and "filtered view" in alias_answer.lower()
    assert "logical" not in alias_answer.lower() and "excluded_entries" not in alias_answer
    assert not model.requests
    assert len(emitted) == 2
    assert emitted[-1:] == agent.last_results


@pytest.mark.parametrize("prompt", [
    "what is the recursive size of ~/.dotfiles?",
    "how big is the dotfiles folder?",
    "check the size of this directory",
    "use bash and check the size of this directory",
    "how much space does this folder use?",
])
def test_common_variants_route_to_directory_usage_for_sole_approved_root(tmp_path, monkeypatch, prompt):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".dotfiles"
    (root / "nested" / "deeper").mkdir(parents=True)
    (root / "nested" / "data").write_bytes(b"known bytes")
    agent, model, _ = size_agent(make_config(roots=(root,)))

    answer = agent.ask(prompt)

    result = agent.last_results[0]
    assert result.name == "directory_usage"
    assert result.data["total_size_bytes"] == len(b"known bytes")
    assert len(agent.last_results) == 1
    assert str(root) in answer
    assert not model.requests


def test_size_request_after_failed_model_turn_does_not_reuse_bad_arguments(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "known").write_bytes(b"abc")

    class FirstCallThenNoModel:
        def __init__(self):
            self.calls = 0

        def chat(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                return {"message": {"content": "", "tool_calls": [{"function": {
                    "name": "processes", "arguments": {"limit": 500}}}]}}
            pytest.fail("The follow-up size request should bypass inference")

    client = FirstCallThenNoModel()
    agent = Agent(client, Runner(Policy(make_config(roots=(root,)))))
    with pytest.raises(PolicyError):
        agent.ask("Show every process")

    assert str(root) in agent.ask("size of the approved folder")
    assert client.calls == 1
    assert agent.last_results[0].data["total_size_bytes"] == 3


def test_subfolder_size_uses_recursive_totals_and_does_not_include_sibling(tmp_path):
    root = tmp_path / "approved"
    (root / "tests" / "nested").mkdir(parents=True)
    (root / "tests" / "one").write_bytes(b"1234")
    (root / "tests" / "nested" / "two").write_bytes(b"56789")
    (root / "other").write_bytes(b"excluded sibling")
    agent, model, _ = size_agent(make_config(roots=(root,)))

    answer = agent.ask("size of tests folder")

    assert agent.last_results[0].data["total_size_bytes"] == 9
    assert agent.last_results[0].data["files_scanned"] == 2
    assert str(root / "tests") in answer
    assert not model.requests


def test_logical_and_allocated_totals_are_independently_counted_from_nested_metadata(tmp_path):
    root = tmp_path / "approved"
    nested = root / "nested" / "deeper"
    nested.mkdir(parents=True)
    ordinary = root / "ordinary.bin"
    ordinary.write_bytes(b"a" * 137)
    sparse = nested / "sparse.bin"
    with sparse.open("wb") as stream:
        stream.seek(2 * 1024 * 1024)
        stream.write(b"z")
    expected_logical = ordinary.stat().st_size + sparse.stat().st_size
    expected_allocated = sum(path.stat().st_blocks * 512 for path in
                             (root, root / "nested", nested, ordinary, sparse))
    agent, model, emitted = size_agent(make_config(roots=(root,), max_steps=1))

    answer = agent.ask("size of this directory")

    result = agent.last_results[0]
    assert result.name == "directory_usage" and len(agent.last_results) == 1
    assert result.data["total_size_bytes"] == expected_logical
    assert result.data["allocated_size_bytes"] == expected_allocated
    assert result.data["total_size_bytes"] != result.data["allocated_size_bytes"]
    assert "logical" in answer.lower() and "allocated" in answer.lower()
    assert len(emitted) == 1 and not model.requests


def test_directory_usage_never_reads_file_contents(tmp_path, monkeypatch):
    from os_assistant import filesystem

    root = tmp_path / "approved"
    root.mkdir()
    (root / "payload").write_bytes(b"fixture content that must not be read")
    original_open = os.open
    observed = []

    def checked_open(path, flags, *args, **kwargs):
        if path == "payload":
            observed.append(flags)
            assert flags & getattr(os, "O_PATH", 0)
            assert not flags & (os.O_WRONLY | os.O_RDWR)
        return original_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(filesystem.os, "open", checked_open)
    monkeypatch.setattr(filesystem.os, "read", lambda *a, **k: pytest.fail("size scanner read file contents"))
    agent, model, _ = size_agent(make_config(roots=(root,)))

    agent.ask("size of this directory")

    assert len(observed) == 1
    assert agent.last_results[0].data["contents_read"] is False
    assert not model.requests


def test_bash_only_root_is_eligible_for_size_but_metadata_root_does_not_grant_bash(tmp_path):
    bash_root = tmp_path / "bash-approved"
    metadata_root = tmp_path / "metadata-only"
    bash_root.mkdir()
    metadata_root.mkdir()
    (bash_root / "payload").write_bytes(b"bash data")
    config = make_config(bash_roots=(bash_root,))
    assert not config.allowed_roots
    agent, model, _ = size_agent(config)

    answer = agent.ask("check the size of this directory")

    assert agent.last_results[0].name == "directory_usage"
    assert agent.last_results[0].data["total_size_bytes"] == len(b"bash data")
    assert str(bash_root) in answer
    assert not model.requests

    metadata_policy = Policy(make_config(roots=(metadata_root,)))
    with pytest.raises(PolicyError):
        metadata_policy.prepare("bash", {"root": str(metadata_root), "command": "cat payload"})


def test_disabled_bash_roots_do_not_join_metadata_size_roots(tmp_path):
    metadata_root, disabled_bash_root = tmp_path / "metadata", tmp_path / "bash-disabled"
    metadata_root.mkdir()
    disabled_bash_root.mkdir()
    (disabled_bash_root / "payload").write_bytes(b"not authorized")
    config = replace(make_config(roots=(metadata_root,)), bash_roots=(str(disabled_bash_root),),
                     bash_enabled=False)
    agent, model, _ = size_agent(config)

    answer = agent.ask("size of this directory")

    assert str(metadata_root) in answer
    assert agent.last_results[0].name == "directory_usage"
    assert agent.last_results[0].data["total_size_bytes"] == 0
    assert not model.requests
    with pytest.raises(PolicyError):
        agent.ask(f"size of {disabled_bash_root} folder")
    assert not agent.last_results and not model.requests


def test_explicit_absolute_subfolder_selects_most_specific_overlapping_root(tmp_path):
    broad = tmp_path / "approved"
    narrow = broad / "nested-approved"
    (narrow / "tests").mkdir(parents=True)
    (narrow / "tests" / "inside").write_bytes(b"inside")
    (broad / "sibling").write_bytes(b"must not count")
    agent, model, _ = size_agent(make_config(roots=(broad, narrow)))

    answer = agent.ask(f"size of {narrow / 'tests'} folder")

    result = agent.last_results[0]
    assert result.data["root"] == str(narrow)
    assert result.data["path"] == "tests"
    assert result.data["total_size_bytes"] == len(b"inside")
    assert str(narrow / "tests") in answer
    assert len(agent.last_results) == 1 and not model.requests


@pytest.mark.parametrize("target", ["~other/private", "$HOME", "${HOME}", "../outside"])
def test_home_aliases_env_text_and_traversal_never_expand_or_widen(tmp_path, target):
    root = tmp_path / "approved"
    root.mkdir()
    agent, model, _ = size_agent(make_config(roots=(root,)))

    with pytest.raises(PolicyError):
        agent.ask(f"size of {target} folder")

    assert not agent.last_results and not model.requests


def test_explicit_nonexistent_location_is_denied_without_scan_or_model(tmp_path, monkeypatch):
    from os_assistant import filesystem

    root = tmp_path / "approved"
    root.mkdir()
    missing = root / "does-not-exist"
    monkeypatch.setattr(filesystem, "usage", lambda *a, **k: pytest.fail("missing path was scanned"))
    agent, model, _ = size_agent(make_config(roots=(root,)))

    with pytest.raises(PolicyError):
        agent.ask(f"size of {missing} folder")

    assert not agent.last_results and not model.requests


def test_multiple_roots_clarify_locally_then_literal_folder_answer_selects_approved_root(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "payload").write_bytes(b"second")
    agent, model, _ = size_agent(make_config(roots=(first, second)))

    clarification = agent.ask("size")
    assert "folder" in clarification.lower() or "which" in clarification.lower()
    assert not agent.last_results
    assert not model.requests

    answer = agent.ask("second")
    assert agent.last_results[0].name == "directory_usage"
    assert agent.last_results[0].data["total_size_bytes"] == 6
    assert str(second) in answer
    assert not model.requests


@pytest.mark.parametrize("small_talk", ["hello", "thanks", "ls"])
def test_small_talk_and_bare_command_after_local_clarification_cannot_select_a_root(tmp_path, small_talk):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    model = ChatClient("Conversational fallback.")
    agent = Agent(model, Runner(Policy(make_config(roots=(first, second)))))

    agent.ask("size")
    assert agent.ask(small_talk) == "Conversational fallback."
    assert agent.ask("second") == "Conversational fallback."

    assert len(model.requests) == 2
    assert not agent.last_results


@pytest.mark.parametrize("roots,ambiguous_name", [
    (("one/dotfiles", "two/dotfiles"), "dotfiles"),
    (("one/.dotfiles", "two/dotfiles"), "dotfiles"),
])
def test_ambiguous_same_or_dotless_root_names_clarify_then_explicit_path_works(
        tmp_path, roots, ambiguous_name):
    first, second = (tmp_path / item for item in roots)
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    (second / "payload").write_bytes(b"second")
    agent, model, emitted = size_agent(make_config(roots=(first, second)))

    clarification = agent.ask(f"size of {ambiguous_name} folder")
    assert "approved folder" in clarification.lower() or "which" in clarification.lower()
    assert not emitted
    assert not model.requests

    answer = agent.ask(f"size of {second} folder")
    assert agent.last_results[0].data["total_size_bytes"] == 6
    assert str(second) in answer
    assert len(emitted) == 1 and not model.requests


@pytest.mark.parametrize("target", ["protected", "nested_protected", "outside", "traversal", "symlink"])
def test_denied_or_unsupported_size_path_never_falls_back_to_model(tmp_path, target):
    root = tmp_path / "approved"
    root.mkdir()
    (root / ".env").write_text("fixture secret", encoding="utf-8")
    nested = root / "nested"
    (nested / ".git").mkdir(parents=True)
    (nested / ".git" / "config").write_text("fixture secret", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    requested = {
        "protected": root / ".env",
        "nested_protected": nested / ".git",
        "outside": outside,
        "traversal": root / ".." / "outside",
        "symlink": root / "link",
    }[target]
    agent, model, _ = size_agent(make_config(roots=(root,)))

    with pytest.raises(PolicyError):
        agent.ask(f"size of {requested} folder")

    assert not agent.last_results
    assert not model.requests


@pytest.mark.parametrize("prompt", [
    "Do not check the folder size; explain what recursive size means.",
    "If the folder is large, check its size and tell me what to delete.",
    "Explain how to check the size of this directory.",
    "Check this directory's size and list its files.",
])
def test_negated_conditional_explanatory_and_mixed_requests_use_chat_fallback(tmp_path, prompt):
    root = tmp_path / "approved"
    root.mkdir()
    client = ChatClient("This is a conversational answer, not a scan.")
    agent = Agent(client, Runner(Policy(make_config(roots=(root,)))))

    assert agent.ask(prompt) == "This is a conversational answer, not a scan."
    assert len(client.requests) == 1
    assert not agent.last_results


@pytest.mark.parametrize("prompt", [
    "`ls`",
    "Explain `du -sh .`.",
    "Run `du -sh .`; then list files.",
    "If the folder is large, check its size.",
    "Check the folder size and list its files.",
])
def test_quoted_commands_chains_conditions_and_mixed_actions_never_route_to_size(tmp_path, prompt):
    root = tmp_path / "approved"
    root.mkdir()
    client = ChatClient("Safe no-call text.")
    agent = Agent(client, Runner(Policy(make_config(roots=(root,)))))

    assert agent.ask(prompt) == "Safe no-call text."
    assert len(client.requests) == 1
    assert not agent.last_results


def test_denied_runner_result_stops_without_retry_or_model_fallback(tmp_path, monkeypatch):
    from os_assistant.contracts import ToolResult

    root = tmp_path / "approved"
    root.mkdir()
    policy = Policy(make_config(roots=(root,)))
    runner = Runner(policy)
    calls = []

    def denied(call):
        calls.append(call)
        return ToolResult(call.name, "denied", {"message": "fixture denial"})

    monkeypatch.setattr(runner, "run", denied)
    model = NoModel()
    agent = Agent(model, runner)
    assert "Stopped" in agent.ask("check the size of this directory")
    assert len(calls) == 1
    assert len(agent.last_results) == 1
    assert not model.requests


def test_size_context_resets_and_bare_folder_after_reset_is_not_selected(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "payload").write_bytes(b"first")
    (second / "payload").write_bytes(b"second")
    config = make_config(roots=(first, second))
    model = ChatClient()
    agent = Agent(model, Runner(Policy(config)))

    agent.ask(f"size of {first} folder")
    assert agent.ask("which folder was that?")
    agent.reset()
    assert agent.history == []
    assert agent.ask("second")
    assert not agent.last_results
    assert len(model.requests) <= 1


def test_immediate_folder_reply_uses_narrow_size_context_and_which_folder_is_local(tmp_path):
    root = tmp_path / "approved"
    child = root / "nested"
    child.mkdir(parents=True)
    (child / "payload").write_bytes(b"nested")
    model = NoModel()
    emitted = []
    runner = Runner(Policy(make_config(roots=(root,))))
    agent = Agent(model, runner, on_result=emitted.append)

    first = agent.ask(f"size of {child} folder")
    which = agent.ask("which folder did you measure?")

    assert str(child) in first and str(child) in which
    assert len(emitted) == 1
    assert agent.last_results == []
    assert not model.requests

    # An immediate literal path reply is scoped to the same approved location.
    next_answer = agent.ask(str(child))
    assert str(child) in next_answer
    assert len(emitted) == 2
    assert agent.last_results[0].data["total_size_bytes"] == len(b"nested")
    assert not model.requests


@pytest.mark.parametrize("small_talk", ["hello", "thanks", "ls"])
def test_small_talk_and_bare_command_after_size_do_not_reuse_size_context(tmp_path, small_talk):
    root = tmp_path / "approved"
    root.mkdir()
    model = ChatClient("Safe no-call reply.")
    emitted = []
    agent = Agent(model, Runner(Policy(make_config(roots=(root,)))), on_result=emitted.append)

    agent.ask("size of this directory")
    assert agent.ask(small_talk) == "Safe no-call reply."

    assert len(model.requests) == 1
    assert len(emitted) == 1
    assert agent.last_results == []


def test_model_generated_clarification_does_not_arm_bare_folder_routing(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    model = ChatClient("Which folder should I measure?")
    agent = Agent(model, Runner(Policy(make_config(roots=(root,)))))

    assert agent.ask("Can you help me?") == "Which folder should I measure?"
    assert agent.ask(str(root)) == "Which folder should I measure?"

    assert len(model.requests) == 2
    assert not agent.last_results


@pytest.mark.parametrize("status", ["denied", "error", "preview"])
def test_denied_error_and_preview_disarm_followup_context(tmp_path, monkeypatch, status):
    from os_assistant.contracts import ToolResult

    root = tmp_path / "approved"
    root.mkdir()
    model = ChatClient("No scan was requested.")
    runner = Runner(Policy(make_config(roots=(root,))))
    calls = []

    def result(call):
        calls.append(call)
        return ToolResult(call.name, status, {"summary": "fixture"})

    monkeypatch.setattr(runner, "run", result)
    agent = Agent(model, runner)

    agent.ask("size of this directory")
    assert agent.ask(str(root)) == "No scan was requested."

    assert len(calls) == 1
    assert len(model.requests) == 1
    assert not agent.last_results


def test_runner_exception_disarms_size_context_before_next_turn(tmp_path, monkeypatch):
    root = tmp_path / "approved"
    root.mkdir()
    model = ChatClient("Safe fallback.")
    runner = Runner(Policy(make_config(roots=(root,))))
    monkeypatch.setattr(runner, "run", lambda call: (_ for _ in ()).throw(PolicyError("fixture")))
    agent = Agent(model, runner)

    with pytest.raises(PolicyError):
        agent.ask("size of this directory")
    assert agent.ask(str(root)) == "Safe fallback."
    assert len(model.requests) == 1
    assert not agent.last_results


@pytest.mark.parametrize("directory_name", ["Annual folder", "Quarter 1.release."])
def test_quoted_folder_with_spaces_and_final_period_is_path_data(tmp_path, directory_name):
    root = tmp_path / "approved"
    named = root / directory_name
    named.mkdir(parents=True)
    (named / "payload").write_bytes(b"period")
    agent, model, _ = size_agent(make_config(roots=(root,)))

    answer = agent.ask(f'size of "{named}" folder?')

    assert agent.last_results[0].data["total_size_bytes"] == len(b"period")
    assert str(named) in answer
    assert not model.requests


def test_question_mark_inside_quoted_folder_path_is_preserved_and_policy_denied(tmp_path):
    # '?' is intentionally forbidden by the existing pathname policy. The
    # parser must not trim it into a different, permitted sibling path.
    root = tmp_path / "approved"
    named = root / "folder?"
    named.mkdir(parents=True)
    (named / "payload").write_bytes(b"question")
    permitted_sibling = root / "folder"
    permitted_sibling.mkdir()
    (permitted_sibling / "payload").write_bytes(b"wrong target")
    agent, model, _ = size_agent(make_config(roots=(root,)))

    with pytest.raises(PolicyError):
        agent.ask(f'size of "{named}"?')

    assert not agent.last_results
    assert not model.requests


def test_quoted_size_words_in_history_do_not_turn_followup_into_a_scan(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    model = ChatClient("A conversational answer.")
    agent = Agent(model, Runner(Policy(make_config(roots=(root,)))))

    agent.ask("Explain the phrase 'check the size of this directory'.")
    agent.ask("Don't do that; just explain the wording.")

    assert len(model.requests) == 2
    assert not agent.last_results


def test_dry_run_routes_preview_without_scanner_model_or_confirmation(tmp_path, monkeypatch):
    from os_assistant import filesystem
    from os_assistant import bash
    import os_assistant.runner as execution

    root = tmp_path / "approved"
    root.mkdir()
    policy = Policy(make_config(roots=(root,)))
    monkeypatch.setattr(filesystem, "usage", lambda *a, **k: pytest.fail("dry-run scanned folder metadata"))
    monkeypatch.setattr(bash, "snapshot", lambda *a, **k: pytest.fail("dry-run created a snapshot"))
    monkeypatch.setattr(execution, "run_captured", lambda *a, **k: pytest.fail("dry-run captured output"))
    model = ChatClient("Safe no-call fallback.")
    previews = []
    runner = Runner(policy, dry_run=True, confirm=lambda call: pytest.fail("size preview asked for confirmation"),
                    preview=previews.append)
    agent = Agent(model, runner)

    answer = agent.ask("size of this directory")

    assert agent.last_results[0].status == "preview"
    assert len(previews) == 1 and previews[0].name == "directory_usage"
    assert "preview" in answer.lower() or "preview" in repr(agent.last_results[0].data).lower()
    assert not model.requests
    assert agent.ask(str(root)) == "Safe no-call fallback."
    assert len(model.requests) == 1
    assert not agent.last_results


def test_summary_preserves_exclusions_and_incomplete_scan_labels(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    (root / ".env").write_text("never read", encoding="utf-8")
    (root / "nested" / "deeper").mkdir(parents=True)
    for number in range(4):
        (root / f"file-{number}").write_bytes(b"x")
    config = make_config(roots=(root,), usage_depth=1)
    agent, model, _ = size_agent(config)

    answer = agent.ask("how much space does this folder use?")

    data = agent.last_results[0].data
    assert data["truncated_scan"] is True and data["scan_complete"] is False
    assert data["excluded_entries"] >= 1
    assert "incomplete" in answer.lower()
    assert "filtered view" in answer.lower()
    assert not model.requests


def test_no_approved_root_is_a_local_limitation_not_a_model_request():
    agent, model, emitted = size_agent(Config())
    answer = agent.ask("check the size of this directory")
    assert "No folder is approved" in answer
    assert agent.last_answer_kind == "local" and agent.last_status == "ok"
    assert not model.requests and not emitted and not agent.last_results


@pytest.mark.parametrize("prompt", [
    "check the size of this directory.",
    "what is this folder's size?",
    "please could you tell me the size of this folder?",
])
def test_plain_sentence_variants_stay_local(tmp_path, prompt):
    root = tmp_path / "approved"
    root.mkdir()
    agent, model, emitted = size_agent(make_config(roots=(root,)))
    assert str(root) in agent.ask(prompt)
    assert len(emitted) == 1 and not model.requests


def test_parent_path_punctuation_is_not_trimmed_into_current_folder(tmp_path, monkeypatch):
    from os_assistant import filesystem
    root = tmp_path / "approved"
    root.mkdir()
    agent, model, emitted = size_agent(make_config(roots=(root,)))
    monkeypatch.setattr(filesystem, "usage", lambda *a, **k: pytest.fail("parent traversal caused a scan"))
    with pytest.raises(PolicyError):
        agent.ask("size of ..")
    assert not model.requests and not emitted and not agent.last_results


def test_invalid_user_turn_disarms_local_clarification(tmp_path):
    from os_assistant.contracts import ModelError
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    model = ChatClient("No-call conversation.")
    agent = Agent(model, Runner(Policy(make_config(roots=(first, second)))))
    agent.ask("size")
    with pytest.raises(ModelError):
        agent.ask("x" * 2049)
    assert agent.ask(str(first)) == "No-call conversation."
    assert len(model.requests) == 1 and not agent.last_results


@pytest.mark.parametrize("question", [
    "how many files are in ~/.dotfiles?",
    "number of files in the ~/.dotfiles folder",
    "file count of ~/.dotfiles",
    "count files in ~/.dotfiles",
    "how many files does the dotfiles folder contain?",
    "show me the number of files in this folder",
])
def test_file_count_questions_are_metric_only_scoped_and_local(tmp_path, monkeypatch, question):
    monkeypatch.setenv("HOME", str(tmp_path))
    root = tmp_path / ".dotfiles"
    (root / "nested").mkdir(parents=True)
    (root / "one").write_bytes(b"1")
    (root / "nested" / "two").write_bytes(b"22")
    (root / ".env").write_bytes(b"excluded")
    agent, model, emitted = size_agent(make_config(roots=(root,)))
    assert agent.ask(question) == "2 files (filtered view)."
    assert len(emitted) == 1 and not model.requests
    assert emitted[0].data["contents_read"] is False
    assert emitted[0].data["excluded_entries"] == 1


def test_count_clarification_remembers_metric_but_compaction_disarms_it(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (second / "file").write_bytes(b"x")
    agent, model, emitted = size_agent(make_config(roots=(first, second)))
    assert "Which approved folder" in agent.ask("number of files")
    assert agent.ask("second") == "1 file (filtered view)."
    assert len(emitted) == 1 and not model.requests


def test_json_and_details_are_explicit_and_cached_results_do_not_rescan(tmp_path):
    import json
    root = tmp_path / "approved"
    root.mkdir()
    (root / "file").write_bytes(b"123")
    agent, model, emitted = size_agent(make_config(roots=(root,)))
    data = json.loads(agent.ask("size of this directory as JSON"))
    assert data["tool"] == "directory_usage" and data["data"]["total_size_bytes"] == 3
    assert agent.last_answer_format == "json"
    details = agent.ask("show details")
    assert "not a new check" in details and "Excluded entries" in details
    cached = json.loads(agent.ask("show JSON"))
    assert cached["historical"] is True and cached["new_execution"] is False
    assert len(emitted) == 1 and not model.requests and not agent.last_results


def test_logical_size_is_only_returned_when_requested(tmp_path):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "file").write_bytes(b"123")
    agent, model, _ = size_agent(make_config(roots=(root,)))
    assert "3 B logical file size" in agent.ask("logical size of this directory")
    assert "allocated" not in agent.ask("logical size of this directory")
    assert not model.requests


@pytest.mark.parametrize("prompt", [
    "Run echo as JSON",
    "Use the terminal to execute echo as JSON",
    "Use bash to execute echo with details",
    "Use echo as JSON",
    "Run echo 'with details'",
    'size of "folder as JSON"',
    'size of "folder with details"',
])
def test_output_preferences_never_rewrite_literal_command_data_or_quoted_paths(prompt):
    from os_assistant.routing import output_request
    options = output_request(prompt)
    assert options.question == prompt
    assert not options.json_output and not options.details


def test_explicit_backtick_command_can_request_json_without_altering_the_command():
    from os_assistant.routing import output_request
    from os_assistant.intent import literal_command
    options = output_request("Run `ls -lh . | head -n 5` as JSON")
    assert options.json_output
    assert literal_command(options.question) == "ls -lh . | head -n 5"


@pytest.mark.parametrize("target", ["logical", "allocated", '"allocated and logical"'])
def test_folder_name_never_selects_an_unrequested_size_metric(target):
    from os_assistant.routing import size_request
    request = size_request("size of " + target)
    assert request is not None and request.metric == "size"


@pytest.mark.parametrize("question", [
    "allocated and logical size of this directory",
    "logical and allocated size of this directory",
    "disk usage and logical file bytes of this directory",
])
def test_both_size_metrics_require_an_explicit_request(tmp_path, question):
    root = tmp_path / "approved"
    root.mkdir()
    (root / "payload").write_bytes(b"123")
    agent, model, _ = size_agent(make_config(roots=(root,)))
    answer = agent.ask(question)
    assert "allocated" in answer and "3 B logical file size" in answer
    assert not model.requests

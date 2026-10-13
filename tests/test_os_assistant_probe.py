"""The routing probe evaluates model choices without executing any OS tool."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant.config import Config
from os_assistant.probe import CASES, evaluate


class ProbeClient:
    config = Config()

    def __init__(self, malformed=False):
        self.index = 0
        self.malformed = malformed

    def doctor(self):
        return {"digest": "fixture-digest-not-real-model-evidence"}

    def chat(self, messages, tools):
        assert {item["function"]["name"] for item in tools} == {
            "system_status", "processes", "find_files", "directory_usage"}
        _, _, name, args = CASES[self.index]
        self.index += 1
        calls = [] if name is None else [{"function": {"name": name, "arguments": args}}]
        if self.malformed:
            calls = [{"function": None}]
        return {"message": {"tool_calls": calls, "content": "fixture"}}


def test_perfect_mock_passes_with_no_execution():
    report = evaluate(ProbeClient())
    assert report["cases"] >= 30
    assert report["passed_gate"] and report["accuracy"] == 1
    assert report["digest"] == "fixture-digest-not-real-model-evidence"
    assert report["profile"]["context"] == 8192


def test_malformed_mock_fails_without_crash():
    report = evaluate(ProbeClient(malformed=True))
    assert not report["passed_gate"]
    assert report["passed"] == 0


def test_unrequested_optional_filter_does_not_count_as_correct():
    class WrongFilter(ProbeClient):
        def chat(self, messages, tools):
            answer = super().chat(messages, tools)
            calls = answer["message"]["tool_calls"]
            if calls and calls[0]["function"]["name"] == "find_files":
                calls[0]["function"]["arguments"] = {**calls[0]["function"]["arguments"], "limit": 7}
            return answer
    report = evaluate(WrongFilter())
    assert report["passed"] == len(CASES) - 8
    assert not report["passed_gate"]

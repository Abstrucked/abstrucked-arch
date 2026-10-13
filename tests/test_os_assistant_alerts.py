"""Alert watcher tests use fakes only: no real notifications, sockets or desktop session."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import alerts, cli
from os_assistant.config import Config, STATUS_TOOLS, load_config
from os_assistant.contracts import ConfigurationError, ToolResult
from os_assistant.policy import tool_schemas
from os_assistant.replies import answer

GIB = 1024 ** 3
CONFIG = Config()


def sample(memory=None, disk=None):
    result = {}
    if memory is not None:
        result["memory"] = {"percent": memory, "total": 32 * GIB, "free": int(32 * GIB * (100 - memory) / 100)}
    if disk is not None:
        result["disk:/"] = {"percent": disk, "total": 240 * GIB, "free": int(240 * GIB * (100 - disk) / 100)}
    return result


def run(steps, config=CONFIG, start=1000.0):
    """Feed (seconds, sample) steps through evaluate; returns the notifications of each step."""
    state, out = {}, []
    for seconds, values in steps:
        state, notes = alerts.evaluate(state, values, config, start + seconds)
        out.append(notes)
    return out


def test_crossing_up_notifies_once_per_level():
    out = run([(0, sample(disk=50)), (60, sample(disk=91)), (120, sample(disk=92)), (180, sample(disk=96)),
               (240, sample(disk=97))])
    assert [len(n) for n in out] == [0, 1, 0, 1, 0]
    assert (out[1][0].urgency, out[1][0].icon, out[1][0].metric) == ("normal", "drive-harddisk", "disk:/")
    assert out[3][0].urgency == "critical"
    assert out[3][0].body == "Disk / is 96% full — 9.6 GiB available of 240.0 GiB"


def test_memory_notification_text():
    note = run([(0, sample(memory=91))])[0][0]
    assert (note.metric, note.icon, note.urgency) == ("memory", "memory", "normal")
    assert note.body.startswith("RAM 91% used — ") and "available of 32.0 GiB" in note.body


def test_first_sample_over_threshold_notifies_immediately():
    assert run([(0, sample(memory=96))])[0][0].urgency == "critical"


def test_hysteresis_band_keeps_level_and_clears_below_five_points():
    out = run([(0, sample(disk=91)), (60, sample(disk=86)), (120, sample(disk=91)), (180, sample(disk=84.9)),
               (240, sample(disk=91))])
    assert [len(n) for n in out] == [1, 0, 0, 1, 1]
    assert out[3][0].urgency == "low" and out[3][0].title == "Disk space back to normal"
    assert out[4][0].urgency == "normal"


def test_critical_to_warning_is_silent_and_recovers_to_ok():
    out = run([(0, sample(disk=96)), (60, sample(disk=89)), (120, sample(disk=80))])
    assert [len(n) for n in out] == [1, 0, 1]
    assert out[2][0].urgency == "low"


def test_reminders_follow_repeat_minutes_and_zero_disables():
    steps = [(s, sample(disk=92)) for s in (0, 1800, 3599, 3600, 7100, 7200)]
    assert [len(n) for n in run(steps)] == [1, 0, 0, 1, 0, 1]
    off = Config(alerts_repeat_minutes=0)
    assert [len(n) for n in run(steps, off)] == [1, 0, 0, 0, 0, 0]


def test_unavailable_metrics_are_ignored():
    state, notes = alerts.evaluate({}, {}, CONFIG, 0)
    assert (state, notes) == ({}, [])
    state, _ = alerts.evaluate({}, sample(disk=92), CONFIG, 0)
    state, notes = alerts.evaluate(state, {}, CONFIG, 10)
    assert notes == [] and state["disk:/"][0] == 1


def test_measure_skips_unavailable_and_computes_percentages(monkeypatch):
    def fake(*, disk_path=None, **_):
        if disk_path == "/gone":
            return {"memory_bytes": "unavailable", "disk_bytes": "unavailable"}
        return {"memory_bytes": {"total": 1000, "available": 100},
                "disk_bytes": {"total": 220, "used": 150, "free": 50}}
    monkeypatch.setattr(alerts.diagnostics, "collect_system_status", fake)
    config = Config(alerts_disk_paths=("/", "/gone"))
    result = alerts.measure(config)
    assert set(result) == {"memory", "disk:/"}
    assert result["memory"]["percent"] == pytest.approx(90)
    assert result["disk:/"]["percent"] == pytest.approx(75)
    monkeypatch.setattr(alerts.diagnostics, "collect_system_status",
                        lambda **_: {"memory_bytes": "unavailable", "disk_bytes": "unavailable"})
    assert alerts.measure(config) == {}


def test_disk_percent_follows_df_with_reserved_blocks(monkeypatch):
    # total > used + free: 10 reserved units; df reports 90 / (90 + 10) = 90%, not 90 / 120 = 75%.
    monkeypatch.setattr(alerts.diagnostics, "collect_system_status", lambda **_: {
        "memory_bytes": "unavailable", "disk_bytes": {"total": 120, "used": 90, "free": 10}})
    entry = alerts.measure(Config())["disk:/"]
    assert entry["percent"] == pytest.approx(90) and (entry["total"], entry["free"]) == (120, 10)


class FakeRun:
    def __init__(self, stdout=b"42\n", code=0, error=None):
        self.calls, self.stdout, self.code, self.error = [], stdout, code, error

    def __call__(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(argv, self.code, self.stdout, b"")


NOTE = alerts.Notification("disk:/", "critical", "drive-harddisk", "Disk space critical", "body text")


def test_notify_argv_env_and_id(monkeypatch):
    for name, value in (("HOME", "/h"), ("DBUS_SESSION_BUS_ADDRESS", "unix:path=/b"), ("XDG_RUNTIME_DIR", "/r"),
                        ("DISPLAY", ":0"), ("SECRET_TOKEN", "x")):
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    fake = FakeRun()
    monkeypatch.setattr(alerts.subprocess, "run", fake)
    assert alerts.notify(NOTE, None) == 42
    argv, kwargs = fake.calls[0]
    assert argv == ["/usr/bin/notify-send", "-a", "os-assistant", "-u", "critical", "-i", "drive-harddisk", "-p",
                    "Disk space critical", "body text"]
    assert kwargs["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin", "HOME": "/h",
                             "DBUS_SESSION_BUS_ADDRESS": "unix:path=/b", "XDG_RUNTIME_DIR": "/r", "DISPLAY": ":0"}
    assert kwargs["timeout"] == 5 and kwargs["stdin"] == subprocess.DEVNULL
    assert alerts.notify(NOTE, 7) == 42
    assert fake.calls[1][0][8:10] == ["-r", "7"]


@pytest.mark.parametrize("fake", [FakeRun(error=FileNotFoundError()), FakeRun(error=subprocess.TimeoutExpired("x", 5)),
                                  FakeRun(code=1), FakeRun(stdout=b"garbage"), FakeRun(stdout=b"")])
def test_notify_failures_return_none(monkeypatch, fake):
    monkeypatch.setattr(alerts.subprocess, "run", fake)
    assert alerts.notify(NOTE, None) is None


def test_session_alive_cases(tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir()
    assert alerts.session_alive({}) is False
    assert alerts.session_alive({"DISPLAY": "localhost:10"}) is False
    assert alerts.session_alive({"WAYLAND_DISPLAY": "wayland-9", "XDG_RUNTIME_DIR": str(runtime)}) is False
    (runtime / "wayland-9").touch()
    assert alerts.session_alive({"WAYLAND_DISPLAY": "wayland-9", "XDG_RUNTIME_DIR": str(runtime)}) is True
    assert alerts.session_alive({"WAYLAND_DISPLAY": str(runtime / "wayland-9")}) is True
    assert alerts.session_alive({"DISPLAY": ":987654"}) is False


def test_session_alive_x11(monkeypatch):
    seen = []
    monkeypatch.setattr(alerts.os.path, "exists", lambda p: seen.append(str(p)) or True)
    assert alerts.session_alive({"DISPLAY": ":3.0"}) is True
    assert seen == ["/tmp/.X11-unix/X3"]


def watch_env(tmp_path):
    runtime = tmp_path / "run"
    runtime.mkdir(exist_ok=True)
    return {"XDG_RUNTIME_DIR": str(runtime)}


def test_watch_requires_runtime_dir():
    with pytest.raises(ConfigurationError):
        alerts.watch(CONFIG, env={})


def test_watch_sends_replaces_and_exits_with_session(tmp_path, monkeypatch):
    env = watch_env(tmp_path)
    samples = iter([sample(disk=91), sample(disk=96), sample(disk=70)])
    monkeypatch.setattr(alerts, "measure", lambda config: next(samples))
    sent, ids, now = [], iter([11, None, 13]), [0.0]
    lives = iter([True, True, True, False])

    def notifier(note, replace_id):
        sent.append((note.urgency, replace_id))
        return next(ids)

    def sleep(seconds):
        assert seconds == 60
        now[0] += seconds

    assert alerts.watch(CONFIG, clock=lambda: now[0], sleep=sleep, notifier=notifier,
                        alive=lambda e: next(lives), env=env) == 0
    # id reused on escalation; a None id is dropped so the recovery is a fresh popup
    assert sent == [("normal", None), ("critical", 11), ("low", None)]
    assert oct((tmp_path / "run/os-assistant").stat().st_mode & 0o777) == "0o700"


def test_second_instance_exits_silently_while_lock_is_held(tmp_path, monkeypatch):
    env = watch_env(tmp_path)
    inner = []

    def alive(e):
        inner.append(alerts.watch(CONFIG, alive=lambda x: pytest.fail("second watcher ran"), env=env))
        assert alerts.watcher_running(env) is True
        return False

    monkeypatch.setattr(alerts, "measure", lambda config: {})
    assert alerts.watch(CONFIG, alive=alive, env=env, sleep=lambda s: None) == 0
    assert inner == [0]
    assert alerts.watcher_running(env) is False


def test_watcher_running_false_without_lock_file(tmp_path):
    assert alerts.watcher_running({}) is False
    assert alerts.watcher_running(watch_env(tmp_path)) is False


def test_sigterm_stops_cleanly_and_restores_handlers(tmp_path, monkeypatch):
    env = watch_env(tmp_path)
    monkeypatch.setattr(alerts, "measure", lambda config: {})
    before = signal.getsignal(signal.SIGTERM)

    def sleep(seconds):
        os.kill(os.getpid(), signal.SIGTERM)
        pytest.fail("SIGTERM did not interrupt the loop")

    assert alerts.watch(CONFIG, sleep=sleep, alive=lambda e: True, env=env) == 0
    assert signal.getsignal(signal.SIGTERM) == before


def test_status_is_stateless_and_reports_watcher(monkeypatch):
    monkeypatch.setattr(alerts, "measure", lambda config: {**sample(memory=97), **sample(disk=91)})
    monkeypatch.setattr(alerts, "watcher_running", lambda env=None: True)
    data = alerts.status(CONFIG)
    assert [(m["metric"], m["level"]) for m in data["metrics"]] == [("memory", "critical"), ("disk:/", "warning")]
    assert data["watcher_running"] is True
    monkeypatch.setattr(alerts, "measure", lambda config: {})
    assert {m["level"] for m in alerts.status(CONFIG)["metrics"]} == {"unavailable"}


def test_displayed_percent_floors_so_it_never_reaches_the_threshold_early(monkeypatch):
    monkeypatch.setattr(alerts, "measure", lambda config: sample(disk=94.96))
    monkeypatch.setattr(alerts, "watcher_running", lambda env=None: True)
    data = alerts.status(CONFIG)
    disk = next(m for m in data["metrics"] if m["metric"] == "disk:/")
    assert disk["level"] == "warning" and disk["percent"] == 94.9
    text = answer(ToolResult("alerts_status", "ok", data))
    assert "Disk /: 94% used (warning at 90%, critical at 95%) — WARNING" in text


# configuration

def write(tmp_path, text):
    path = tmp_path / "c.toml"
    path.write_text(text)
    return path


def test_config_defaults_and_values(tmp_path):
    config = load_config(write(tmp_path, ""))
    assert (config.alerts_interval, config.alerts_disk_paths, config.alerts_disk_warning, config.alerts_disk_critical,
            config.alerts_memory_warning, config.alerts_memory_critical, config.alerts_repeat_minutes) == (
        60, ("/",), 90, 95, 85, 95, 60)
    config = load_config(write(tmp_path, "[alerts]\ninterval = 15\ndisk_paths = ['/', '/', '/home']\nrepeat_minutes = 0\n"
                                         "memory_warning_percent = 50\nmemory_critical_percent = 51\n"))
    assert config.alerts_disk_paths == ("/", "/home") and config.alerts_repeat_minutes == 0
    assert (config.alerts_memory_warning, config.alerts_memory_critical) == (50, 51)


@pytest.mark.parametrize("body", [
    "interval = 14", "interval = 3601", "interval = '60'", "interval = true", "repeat_minutes = 1441",
    "disk_warning_percent = 49", "disk_warning_percent = 100", "disk_critical_percent = 101",
    "disk_warning_percent = 95", "disk_warning_percent = 96\ndisk_critical_percent = 96",
    "memory_critical_percent = 85", "disk_paths = []", "disk_paths = 'x'", "disk_paths = ['relative']",
    "disk_paths = ['/a/../b']", "disk_paths = ['/1','/2','/3','/4','/5','/6','/7','/8','/9']", "bogus = 1",
])
def test_config_rejects_invalid_alerts(tmp_path, body):
    with pytest.raises(ConfigurationError):
        load_config(write(tmp_path, "[alerts]\n" + body + "\n"))


def test_alerts_status_is_a_default_read_only_tool():
    assert "alerts_status" in STATUS_TOOLS and "alerts_status" in Config().status_enabled
    schema = next(s for s in tool_schemas(Config()) if s["function"]["name"] == "alerts_status")
    assert schema["function"]["parameters"]["properties"] == {}
    assert "alerts_status" not in [s["function"]["name"] for s in tool_schemas(Config(status_enabled=()))]


# reply formatting and CLI

DATA = {"metrics": [{"metric": "memory", "level": "ok", "percent": 41.2, "warning_percent": 85, "critical_percent": 95},
                    {"metric": "disk:/", "level": "warning", "percent": 91.9, "warning_percent": 90, "critical_percent": 95},
                    {"metric": "disk:/mnt", "level": "unavailable", "warning_percent": 90, "critical_percent": 95}],
        "watcher_running": False}


def test_reply_formatter():
    text = answer(ToolResult("alerts_status", "ok", DATA))
    assert "RAM: 41% used (warning at 85%, critical at 95%) — OK" in text
    assert "Disk /: 91% used (warning at 90%, critical at 95%) — WARNING" in text
    assert "Disk /mnt: unavailable" in text
    assert "Alert watcher: not running (enable with: pluginctl enable system-alerts)." in text
    running = answer(ToolResult("alerts_status", "ok", {**DATA, "watcher_running": True}))
    assert "Alert watcher: running." in running


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(cli, "OllamaClient", lambda config: pytest.fail("alert modes contacted the model"))


@pytest.mark.parametrize("level,code", [("ok", 0), ("warning", 6), ("critical", 6)])
def test_cli_check_alerts_exit_codes(isolated, monkeypatch, capsys, level, code):
    item = {"metric": "disk:/", "level": level, "percent": 50.0, "warning_percent": 90, "critical_percent": 95}
    monkeypatch.setattr(cli.alerts, "status", lambda config: {"metrics": [item], "watcher_running": False})
    assert cli.main(["--check-alerts"]) == code
    out = capsys.readouterr().out
    assert out.startswith("── alerts") and "Disk /: 50% used" in out
    assert cli.main(["--check-alerts", "--json"]) == code
    assert json.loads(capsys.readouterr().out)["data"]["metrics"][0]["level"] == level


def test_cli_watch_alerts_dispatches_before_runner(isolated, monkeypatch):
    monkeypatch.setattr(cli, "Runner", lambda *a, **k: pytest.fail("Runner built"))
    seen = []
    monkeypatch.setattr(cli.alerts, "watch", lambda config: seen.append(config) or 0)
    assert cli.main(["--watch-alerts"]) == 0 and len(seen) == 1


@pytest.mark.parametrize("flags", [["--watch-alerts", "--dry-run"], ["--check-alerts", "--dry-run"],
                                   ["--watch-alerts", "hello"], ["--check-alerts", "hello"]])
def test_cli_alert_modes_reject_dry_run_and_prompts(isolated, monkeypatch, capsys, flags):
    monkeypatch.setattr(cli.alerts, "watch", lambda config: pytest.fail("ran"))
    monkeypatch.setattr(cli.alerts, "status", lambda config: pytest.fail("ran"))
    assert cli.main(flags) == 2
    assert "error:" in capsys.readouterr().err


def test_cli_alert_modes_are_mutually_exclusive(isolated):
    with pytest.raises(SystemExit):
        cli.main(["--watch-alerts", "--check-alerts"])
    with pytest.raises(SystemExit):
        cli.main(["--check-alerts", "--doctor"])

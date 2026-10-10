"""Disk/RAM threshold alerts: reads /proc and statvfs, sends desktop notifications, keeps state only in memory."""

from dataclasses import dataclass
import fcntl
import math
import os
from pathlib import Path
import signal
import subprocess
import time
from typing import Callable

from .config import Config
from .contracts import ConfigurationError
from . import diagnostics

NOTIFY_SEND = "/usr/bin/notify-send"
HYSTERESIS = 5
LEVELS = ("ok", "warning", "critical")
_URGENCY = {1: "normal", 2: "critical"}


@dataclass(frozen=True)
class Notification:
    metric: str
    urgency: str
    icon: str
    title: str
    body: str


class _Stop(Exception):
    pass


def human(value: int) -> str:
    for power, unit in enumerate(("B", "KiB", "MiB", "GiB", "TiB", "PiB")):
        if value < 1024 ** (power + 1) or unit == "PiB":
            return f"{value} B" if power == 0 else f"{value / 1024 ** power:.1f} {unit}"
    raise AssertionError("Unreachable size unit")


def _count(value: object) -> bool:
    return type(value) is int and value >= 0


def measure(config: Config) -> dict:
    """Used percentages plus bytes per metric; unavailable metrics are simply absent."""
    sample = {}
    memory = diagnostics.collect_system_status().get("memory_bytes")
    if isinstance(memory, dict) and _count(memory.get("total")) and _count(memory.get("available")) and memory["total"]:
        total, available = memory["total"], min(memory["available"], memory["total"])
        sample["memory"] = {"percent": 100 * (1 - available / total), "total": total, "free": available}
    for path in config.alerts_disk_paths:
        disk = diagnostics.collect_system_status(disk_path=path).get("disk_bytes")
        # df's definition: used / (used + available to users), so reserved blocks count as full.
        if isinstance(disk, dict) and _count(disk.get("total")) and _count(disk.get("used")) and _count(disk.get("free")) \
                and disk["total"] and disk["used"] + disk["free"]:
            sample[f"disk:{path}"] = {"percent": 100 * disk["used"] / (disk["used"] + disk["free"]),
                                      "total": disk["total"], "free": disk["free"]}
    return sample


def thresholds(config: Config, metric: str) -> tuple[int, int]:
    if metric == "memory":
        return config.alerts_memory_warning, config.alerts_memory_critical
    return config.alerts_disk_warning, config.alerts_disk_critical


def _level(percent: float, limits: tuple[int, int], previous: int) -> int:
    warning, critical = limits
    raw = 2 if percent >= critical else 1 if percent >= warning else 0
    # A level already reached is kept until the value is HYSTERESIS points below its threshold.
    held = 2 if previous == 2 and percent >= critical - HYSTERESIS else (
        1 if previous >= 1 and percent >= warning - HYSTERESIS else 0)
    return max(raw, held)


def _notification(metric: str, entry: dict, level: int) -> Notification:
    shown = int(entry["percent"])
    if metric == "memory":
        icon, name = "memory", "Memory"
        detail = f"RAM {shown}% used — {human(entry['free'])} available of {human(entry['total'])}"
        back = f"RAM is back to {shown}% used"
    else:
        icon, name = "drive-harddisk", "Disk space"
        path = metric.partition(":")[2]
        detail = f"Disk {path} is {shown}% full — {human(entry['free'])} available of {human(entry['total'])}"
        back = f"Disk {path} is back to {shown}% full"
    if level == 0:
        return Notification(metric, "low", icon, f"{name} back to normal", back)
    return Notification(metric, _URGENCY[level], icon, f"{name} {LEVELS[level]}", detail)


def evaluate(state: dict, sample: dict, config: Config, now: float) -> tuple[dict, list[Notification]]:
    """Pure transition: state maps metric -> (level, time of last notification)."""
    new, notes = dict(state), []
    for metric, entry in sample.items():
        previous, last = state.get(metric, (0, now))
        level = _level(entry["percent"], thresholds(config, metric), previous)
        repeat = config.alerts_repeat_minutes * 60
        if level > previous:
            notes.append(_notification(metric, entry, level))
            last = now
        elif level == 0 and previous > 0:
            notes.append(_notification(metric, entry, 0))
            last = now
        elif level > 0 and repeat and now - last >= repeat:
            notes.append(_notification(metric, entry, level))
            last = now
        new[metric] = (level, last)
    return new, notes


def notify(notification: Notification, replace_id: int | None = None) -> int | None:
    """Send through notify-send with a fixed argv; returns the popup id or None, never raises."""
    argv = [NOTIFY_SEND, "-a", "os-assistant", "-u", notification.urgency, "-i", notification.icon, "-p"]
    if replace_id:
        argv += ["-r", str(replace_id)]
    argv += [notification.title, notification.body]
    env = {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}
    for name in ("HOME", "DBUS_SESSION_BUS_ADDRESS", "XDG_RUNTIME_DIR", "DISPLAY", "WAYLAND_DISPLAY"):
        if name in os.environ:
            env[name] = os.environ[name]
    try:
        done = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              timeout=5, env=env, check=False)
        text = done.stdout.decode("ascii", "replace").strip()
        return int(text) if done.returncode == 0 and text.isascii() and text.isdigit() and len(text) <= 10 else None
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def session_alive(env=os.environ) -> bool:
    """True while the X socket for DISPLAY or the Wayland socket still exists."""
    wayland = env.get("WAYLAND_DISPLAY")
    if wayland:
        runtime = env.get("XDG_RUNTIME_DIR")
        socket = Path(wayland) if os.path.isabs(wayland) else Path(runtime, wayland) if runtime else None
        if socket is not None and os.path.exists(socket):
            return True
    display = env.get("DISPLAY")
    if display and display.startswith(":") and display[1:].split(".")[0].isdigit():
        return os.path.exists(f"/tmp/.X11-unix/X{display[1:].split('.')[0]}")
    return False


def _lock_path(env) -> Path:
    runtime = env.get("XDG_RUNTIME_DIR")
    if not runtime or not os.path.isabs(runtime):
        raise ConfigurationError("XDG_RUNTIME_DIR is required for the alert watcher lock.")
    return Path(runtime) / "os-assistant/alerts.lock"


def watch(config: Config, *, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
          notifier: Callable[[Notification, int | None], int | None] = notify,
          alive: Callable[[object], bool] = session_alive, env=os.environ) -> int:
    path = _lock_path(env)
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    except OSError:
        raise ConfigurationError("Cannot open the alert watcher lock file.") from None
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0
        def stop(signum, frame):
            raise _Stop
        previous = {}
        for number in (signal.SIGTERM, signal.SIGINT):
            try:
                previous[number] = signal.signal(number, stop)
            except ValueError:  # not the main thread
                pass
        state, ids = {}, {}
        try:
            while alive(env):
                state, notes = evaluate(state, measure(config), config, clock())
                for note in notes:
                    sent = notifier(note, ids.get(note.metric))
                    if sent is None:
                        ids.pop(note.metric, None)
                    else:
                        ids[note.metric] = sent
                sleep(config.alerts_interval)
        except _Stop:
            pass
        finally:
            for number, handler in previous.items():
                signal.signal(number, handler)
        return 0
    finally:
        os.close(fd)


def watcher_running(env=os.environ) -> bool:
    try:
        fd = os.open(_lock_path(env), os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except (OSError, ConfigurationError):
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
    except OSError:
        return True
    finally:
        os.close(fd)
    return False


def status(config: Config) -> dict:
    """Stateless view: each metric against its thresholds (no hysteresis), plus whether the watcher runs."""
    sample = measure(config)
    metrics = []
    for metric in ("memory", *(f"disk:{p}" for p in config.alerts_disk_paths)):
        warning, critical = thresholds(config, metric)
        entry = sample.get(metric)
        item = {"metric": metric, "warning_percent": warning, "critical_percent": critical}
        if entry is None:
            item["level"] = "unavailable"
        else:
            item.update(level=LEVELS[_level(entry["percent"], (warning, critical), 0)],
                        percent=math.floor(entry["percent"] * 10) / 10, total_bytes=entry["total"], free_bytes=entry["free"])
        metrics.append(item)
    return {"metrics": metrics, "watcher_running": watcher_running(), "interval_seconds": config.alerts_interval}

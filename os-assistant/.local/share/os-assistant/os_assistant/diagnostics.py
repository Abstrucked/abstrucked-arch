"""Bounded read-only diagnostics: fixed-file probes and pure metadata helpers.

Collectors never run commands, touch the network, read credentials or process
arguments.  Missing or malformed metrics degrade to the string "unavailable"
instead of raising.  The pure collectors only transform metadata records that a
caller already authorized; they perform no filesystem access at all.
"""

import fnmatch
import math
import os
from collections.abc import Iterable
from pathlib import Path
import shutil
import time
import unicodedata

from .contracts import FileRecord

UNAVAILABLE = "unavailable"

_MEMINFO_BYTES = 65536
_LOADAVG_BYTES = 1024
_BATTERY_ATTR_BYTES = 256
_BATTERY_ENUM_MAX = 32
_BATTERY_MAX = 8
_STATUS_FILE_BYTES = 16384
_PROC_MAX_DIRS = 4096
_PROC_WALL_SECONDS = 2.0
_LABEL_MAX = 64
_MEGABYTE = 1024 ** 2

_BATTERY_STATUS = {
    "charging": "Charging",
    "discharging": "Discharging",
    "full": "Full",
    "not charging": "Not charging",
    "unknown": "Unknown",
}


def _read_fixed(path: Path, cap: int) -> str | None:
    """Read at most cap bytes of one fixed diagnostic file.

    Only the final attribute file must not be a symlink; parent links are still
    traversed because kernel-managed /sys/class/power_supply entries are
    themselves symlinks into /sys/devices.
    """
    try:
        if path.is_symlink():
            return None
        with open(path, "rb") as stream:
            data = stream.read(cap)
    except OSError:
        return None
    return data.decode("utf-8", "replace")


def _digits(text: str) -> int | None:
    """Parse a short plain ASCII digit string only, so hostile content cannot smuggle values.

    The 20-character cap rejects excessive input before int(), keeping it away
    from Python's integer-string-length limit.
    """
    text = text.strip()
    if 0 < len(text) <= 20 and text.isascii() and text.isdigit():
        return int(text)
    return None


def _clean_label(value: str, max_length: int) -> str | None:
    value = value.strip()
    if not value or len(value) > max_length:
        return None
    if any(unicodedata.category(c).startswith("C") for c in value):
        return None
    return value


def _memory_bytes(proc_root: Path) -> dict | str:
    text = _read_fixed(proc_root / "meminfo", _MEMINFO_BYTES)
    if text is None:
        return UNAVAILABLE
    values: dict[str, int] = {}
    for line in text.splitlines():
        name, sep, rest = line.partition(":")
        if not sep or name not in ("MemTotal", "MemAvailable"):
            continue
        fields = rest.split()
        if len(fields) != 2 or fields[1] != "kB":
            return UNAVAILABLE
        amount = _digits(fields[0])
        if amount is None:
            return UNAVAILABLE
        values[name] = amount * 1024
    if "MemTotal" in values and "MemAvailable" in values:
        return {"total": values["MemTotal"], "available": values["MemAvailable"]}
    return UNAVAILABLE


def _load_average(proc_root: Path) -> dict | str:
    text = _read_fixed(proc_root / "loadavg", _LOADAVG_BYTES)
    if text is None:
        return UNAVAILABLE
    fields = text.split()
    if len(fields) < 3:
        return UNAVAILABLE
    try:
        averages = [float(field) for field in fields[:3]]
    except ValueError:
        return UNAVAILABLE
    if not all(math.isfinite(a) and a >= 0 for a in averages):
        return UNAVAILABLE
    return {"1min": averages[0], "5min": averages[1], "15min": averages[2]}


def _attribute_present(path: Path) -> bool:
    """True when a fixed attribute name exists at all, even as a read-denied symlink."""
    return os.path.lexists(path)


def _battery(sys_root: Path) -> list:
    """Report fixed capacity/status attributes of power-supply entries; nothing else is read.

    At most 32 entries are examined (before sorting) and at most 8 reported.
    Entries exposing neither fixed attribute, such as mains adapters, are
    skipped; entries whose attributes are present but malformed or unreadable
    are reported with "unavailable" fields.
    """
    directory = sys_root / "class" / "power_supply"
    try:
        with os.scandir(directory) as entries:
            names = []
            for entry in entries:
                names.append(entry.name)
                if len(names) >= _BATTERY_ENUM_MAX:
                    break
            names.sort()
    except OSError:
        return []
    batteries = []
    for name in names:
        label = _clean_label(name, _LABEL_MAX)
        if label is None:
            continue
        capacity_path = directory / name / "capacity"
        status_path = directory / name / "status"
        if not _attribute_present(capacity_path) and not _attribute_present(status_path):
            continue
        capacity: int | str = UNAVAILABLE
        raw = _read_fixed(capacity_path, _BATTERY_ATTR_BYTES)
        if raw is not None:
            value = _digits(raw)
            if value is not None and 0 <= value <= 100:
                capacity = value
        status: str = UNAVAILABLE
        raw = _read_fixed(status_path, _BATTERY_ATTR_BYTES)
        if raw is not None:
            status = _BATTERY_STATUS.get(raw.strip().lower(), UNAVAILABLE)
        batteries.append({"name": label, "capacity": capacity, "status": status})
        if len(batteries) >= _BATTERY_MAX:
            break
    return batteries


def _disk_bytes(disk_path) -> dict | str:
    try:
        target = Path(disk_path) if disk_path is not None else Path.home()
        usage = shutil.disk_usage(target)
    except (OSError, RuntimeError, ValueError):
        return UNAVAILABLE
    return {"total": int(usage.total), "used": int(usage.used), "free": int(usage.free)}


def collect_system_status(*, proc_root=Path("/proc"), sys_root=Path("/sys"), disk_path=None) -> dict:
    """Collect memory, load, battery and one filesystem's capacity from fixed files.

    Reads are bounded and limited to proc/meminfo, proc/loadavg and the
    capacity/status attributes under sys/class/power_supply.  disk_path defaults
    to the caller's home folder.  Every missing or malformed metric is reported
    as "unavailable"; this function never raises on bad data.
    """
    proc_root = Path(proc_root)
    sys_root = Path(sys_root)
    return {
        "memory_bytes": _memory_bytes(proc_root),
        "load_average": _load_average(proc_root),
        "battery": _battery(sys_root),
        "disk_bytes": _disk_bytes(disk_path),
    }


def _process_entry(directory: Path) -> dict | None:
    text = _read_fixed(directory / "status", _STATUS_FILE_BYTES)
    if text is None:
        return None
    name: str | None = None
    rss_kib = 0
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        if key == "Name":
            name = _clean_label(rest, _LABEL_MAX)
        elif key == "VmRSS":
            fields = rest.split()
            if len(fields) == 2 and fields[1] == "kB":
                rss_kib = _digits(fields[0]) or 0
    if name is None:
        return None
    return {"pid": int(directory.name), "name": name, "rss_bytes": max(rss_kib, 0) * 1024}


def collect_processes(limit=10, *, proc_root=Path("/proc")) -> dict:
    """List process names and memory use from bounded status-file reads.

    Only each process's status file is read (at most 16 KiB); command lines,
    environments and arguments are never opened.  At most 4096 process folders
    are examined and the scan stops after about two seconds.  Results are sorted
    by memory use descending with the pid as a stable tiebreak.  "truncated" is
    True whenever the result is not the full process list: a scan bound was hit
    or more processes matched than limit.  Vanished, inaccessible or malformed
    processes are skipped; limit must be an integer from 1 to 20.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20.")
    deadline = time.monotonic() + _PROC_WALL_SECONDS
    truncated = False
    names: list[str] = []
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if time.monotonic() >= deadline or len(names) >= _PROC_MAX_DIRS:
                    truncated = True
                    break
                if _digits(entry.name) is not None:
                    names.append(entry.name)
    except OSError:
        return {"processes": [], "truncated": False}
    names.sort(key=int)
    processes = []
    for name in names:
        if time.monotonic() >= deadline:
            truncated = True
            break
        parsed = _process_entry(Path(proc_root) / name)
        if parsed is not None:
            processes.append(parsed)
    processes.sort(key=lambda p: (-p["rss_bytes"], p["pid"]))
    if len(processes) > limit:
        truncated = True
        processes = processes[:limit]
    return {"processes": processes, "truncated": truncated}


def collect_file_search(records: Iterable[FileRecord], *, name_pattern="*", min_size_mb=0, limit=20) -> dict:
    """Filter and rank already-authorized file metadata; this is pure and does no I/O.

    name_pattern is matched (fnmatch, case-sensitive) against each file's base
    name only.  min_size_mb keeps files of at least that many mebibytes
    (1024**2 bytes).  The largest files come first with the relative path as a
    stable tiebreak, at most limit entries.  "matches" counts every match while
    "returned" counts the emitted entries.
    """
    if not isinstance(name_pattern, str) or not name_pattern or len(name_pattern) > 128:
        raise ValueError("name_pattern must be a non-empty string of at most 128 characters.")
    if type(min_size_mb) is not int or min_size_mb < 0:
        raise ValueError("min_size_mb must be a non-negative integer.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20.")
    minimum = min_size_mb * _MEGABYTE
    matches = []
    for record in records:
        relative = record["relative_path"]
        size = record["size_bytes"]
        if size >= minimum and fnmatch.fnmatchcase(relative.rsplit("/", 1)[-1], name_pattern):
            matches.append({"relative_path": relative, "size_bytes": size})
    matches.sort(key=lambda f: (-f["size_bytes"], f["relative_path"]))
    files = matches[:limit]
    return {"files": files, "matches": len(matches), "returned": len(files)}


def collect_directory_usage(records: Iterable[FileRecord], *, depth=1, limit=20, file_limit=0,
                            allocated_directories: dict[str, int] | None = None) -> dict:
    """Aggregate already-authorized file sizes by directory; pure, no I/O.

    Each record is taken from the iterable exactly once and feeds the
    cumulative total of every ancestor directory from depth 1 up to depth: at
    depth 2, "a/b/c.txt" adds its bytes and a file count to both "a" and
    "a/b", while "a/d.txt" adds only to "a".  Files directly in the scan root
    stay grouped under "(root files)" at every depth.  Cumulative totals can
    therefore overlap when depth is greater than 1, which the explicit
    directory_totals_overlap flag reports.  Groups are ranked by size
    descending with the name as a stable tiebreak and capped at limit entries;
    truncated_directories reports only that emission cap, never scan state.
    total_size_bytes and files_scanned count each source record exactly once
    regardless of overlap or truncation, and each group also reports how many
    records fed it.  files lists the largest file_limit individual records by
    size descending with the relative path as a stable tiebreak; file_limit 0
    explicitly opts out and yields an empty, untruncated file view.  depth must
    be an integer from 1 to 8, limit from 1 to 20, file_limit from 0 to 20;
    booleans do not count as integers here.  These summaries cover only the
    records supplied, never the whole filesystem.
    """
    if type(depth) is not int or not 1 <= depth <= 8:
        raise ValueError("depth must be an integer between 1 and 8.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20.")
    if type(file_limit) is not int or not 0 <= file_limit <= 20:
        raise ValueError("file_limit must be an integer between 0 and 20.")
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    entries: list[dict] = []
    files_scanned = 0
    total_size_bytes = 0
    allocated_files = 0
    allocated_totals: dict[str, int] = {}
    for record in records:
        files_scanned += 1
        relative = record["relative_path"]
        size = record["size_bytes"]
        total_size_bytes += size
        if allocated_directories is not None:
            allocated_files += record["allocated_size_bytes"]
        if file_limit:
            entries.append({"relative_path": relative, "size_bytes": size})
        if "/" not in relative:
            groups = ["(root files)"]
        else:
            parts = relative.split("/")[:-1]
            groups = ["/".join(parts[:level]) for level in range(1, min(depth, len(parts)) + 1)]
        for name in groups:
            totals[name] = totals.get(name, 0) + size
            counts[name] = counts.get(name, 0) + 1
            if allocated_directories is not None:
                allocated_totals[name] = allocated_totals.get(name, 0) + record["allocated_size_bytes"]
    if allocated_directories is not None:
        for relative, allocated in allocated_directories.items():
            if relative == ".":
                continue
            parts = relative.split("/")
            for level in range(1, min(depth, len(parts)) + 1):
                name = "/".join(parts[:level])
                allocated_totals[name] = allocated_totals.get(name, 0) + allocated
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    directories = [
        {"name": name, "size_bytes": size, "files_scanned": counts[name]}
        for name, size in ranked[:limit]
    ]
    entries.sort(key=lambda f: (-f["size_bytes"], f["relative_path"]))
    files = entries[:file_limit]
    data = {
        "directories": directories,
        "directories_total": len(ranked),
        "directories_returned": len(directories),
        "truncated_directories": len(ranked) > limit,
        "directory_totals_overlap": depth > 1,
        "total_size_bytes": total_size_bytes,
        "files_scanned": files_scanned,
        "files": files,
        "files_returned": len(files),
        "truncated_files": file_limit > 0 and files_scanned > file_limit,
    }
    if allocated_directories is not None:
        for directory in data["directories"]:
            directory["allocated_size_bytes"] = allocated_totals.get(directory["name"], 0)
        data.update({"allocated_size_bytes": allocated_files + sum(allocated_directories.values()),
                     "allocated_file_bytes": allocated_files,
                     "allocated_directory_bytes": sum(allocated_directories.values())})
    return data

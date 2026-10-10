"""Diagnostic collector tests use fixture proc/sys trees and synthetic metadata only.

Nothing here reads the real /proc, /sys, HOME directory, or any process's
command line or environment.
"""

import ast
import builtins
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant" / ".local" / "share" / "os-assistant"))

from os_assistant import diagnostics
from os_assistant.contracts import FileRecord

MB = 1024 ** 2


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def record(relative_path: str, size_bytes: int) -> FileRecord:
    return {"relative_path": relative_path, "name": relative_path.rsplit("/", 1)[-1], "size_bytes": size_bytes}


class RecordingOpen:
    """Stand-in for builtins.open that records every path and can forbid suffixes."""

    def __init__(self, forbidden: tuple[str, ...] = ()):
        self.real = builtins.open
        self.forbidden = forbidden
        self.opened = []

    def __call__(self, file, *args, **kwargs):
        path = str(file)
        self.opened.append(path)
        for suffix in self.forbidden:
            if path.endswith(suffix):
                raise AssertionError("forbidden read: " + path)
        return self.real(file, *args, **kwargs)


class FakeScandir:
    """os.scandir stand-in yielding scripted entries and recording consumption."""

    def __init__(self, names, seen):
        self.names = names
        self.seen = seen

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for name in self.names:
            self.seen.append(name)
            yield types.SimpleNamespace(name=name)


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)


class SystemStatusTests(_Base):
    def setUp(self):
        super().setUp()
        self.proc = self.tmp / "proc"
        self.sys = self.tmp / "sys"
        self.proc.mkdir()
        self.sys.mkdir()
        self.disk = self.tmp / "disk"
        self.disk.mkdir()

    def status(self, **kwargs):
        kwargs.setdefault("proc_root", self.proc)
        kwargs.setdefault("sys_root", self.sys)
        kwargs.setdefault("disk_path", self.disk)
        return diagnostics.collect_system_status(**kwargs)

    def test_reads_fixed_metrics(self):
        write(self.proc / "meminfo",
              "MemTotal:        2048 kB\nMemFree:          100 kB\nMemAvailable:    1024 kB\n")
        write(self.proc / "loadavg", "0.10 0.20 0.30 1/234 56789\n")
        write(self.sys / "class/power_supply/BAT0/capacity", "88\n")
        write(self.sys / "class/power_supply/BAT0/status", "Discharging\n")
        result = self.status()
        self.assertEqual(result["memory_bytes"], {"total": 2048 * 1024, "available": 1024 * 1024})
        self.assertEqual(result["load_average"], {"1min": 0.1, "5min": 0.2, "15min": 0.3})
        self.assertEqual(result["battery"], [{"name": "BAT0", "capacity": 88, "status": "Discharging"}])
        disk = result["disk_bytes"]
        self.assertTrue(all(type(value) is int for value in disk.values()))
        self.assertEqual(disk["total"], disk["used"] + disk["free"])
        json.dumps(result)

    def test_missing_metrics_are_unavailable(self):
        result = self.status(disk_path=self.tmp / "absent")
        self.assertEqual(result["memory_bytes"], "unavailable")
        self.assertEqual(result["load_average"], "unavailable")
        self.assertEqual(result["battery"], [])
        self.assertEqual(result["disk_bytes"], "unavailable")

    def test_malformed_metrics_are_unavailable(self):
        write(self.proc / "meminfo", "MemTotal: plenty kB\nMemAvailable:    1024 kB\n")
        write(self.proc / "loadavg", "0.10 not-a-number 0.30\n")
        write(self.sys / "class/power_supply/BAT0/capacity", "over 9000\n")
        write(self.sys / "class/power_supply/BAT0/status", "Launch codes\n")
        result = self.status()
        self.assertEqual(result["memory_bytes"], "unavailable")
        self.assertEqual(result["load_average"], "unavailable")
        self.assertEqual(result["battery"],
                         [{"name": "BAT0", "capacity": "unavailable", "status": "unavailable"}])

    def test_partial_meminfo_is_unavailable(self):
        write(self.proc / "meminfo", "MemTotal:    2048 kB\n")
        self.assertEqual(self.status()["memory_bytes"], "unavailable")

    def test_capacity_and_status_are_strictly_validated(self):
        write(self.sys / "class/power_supply/BAT0/capacity", "150\n")
        write(self.sys / "class/power_supply/BAT0/status", "CHARGING\n")
        write(self.sys / "class/power_supply/BAT1/capacity", "12.5\n")
        write(self.sys / "class/power_supply/BAT1/status", "full\n")
        write(self.sys / "class/power_supply/BAT2/capacity", "042\n")
        write(self.sys / "class/power_supply/BAT2/status", "Not charging\n")
        result = self.status()
        self.assertEqual(result["battery"], [
            {"name": "BAT0", "capacity": "unavailable", "status": "Charging"},
            {"name": "BAT1", "capacity": "unavailable", "status": "Full"},
            {"name": "BAT2", "capacity": 42, "status": "Not charging"},
        ])

    def test_only_fixed_files_are_read_and_never_arbitrary_content(self):
        write(self.proc / "meminfo", "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n")
        write(self.proc / "loadavg", "0.10 0.20 0.30\n")
        write(self.sys / "class/power_supply/BAT0/capacity", "55\n")
        write(self.sys / "class/power_supply/BAT0/status", "Full\n")
        write(self.sys / "class/power_supply/BAT0/serial_number", "SECRET-123\n")
        write(self.sys / "class/power_supply/BAT0/uevent", "SECRET-456\n")
        guard = RecordingOpen()
        with mock.patch("builtins.open", guard):
            result = self.status()
        self.assertEqual(set(guard.opened), {
            str(self.proc / "meminfo"), str(self.proc / "loadavg"),
            str(self.sys / "class/power_supply/BAT0/capacity"),
            str(self.sys / "class/power_supply/BAT0/status"),
        })
        self.assertNotIn("SECRET", json.dumps(result))

    def test_final_attribute_symlinks_are_not_followed(self):
        write(self.proc / "meminfo", "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n")
        write(self.proc / "loadavg", "0.10 0.20 0.30\n")
        secret = self.tmp / "secret"
        write(secret, "SECRET-789\n")
        (self.sys / "class/power_supply").mkdir(parents=True)
        (self.sys / "class/power_supply/BAT0").mkdir()
        (self.sys / "class/power_supply/BAT0/capacity").symlink_to(secret)
        (self.sys / "class/power_supply/BAT0/status").symlink_to(secret)
        result = self.status()
        self.assertEqual(result["battery"],
                         [{"name": "BAT0", "capacity": "unavailable", "status": "unavailable"}])
        self.assertNotIn("SECRET", json.dumps(result))

    def test_parent_links_are_supported(self):
        device = self.tmp / "devices" / "BAT0dev"
        write(device / "capacity", "88\n")
        write(device / "status", "Discharging\n")
        supply = self.sys / "class/power_supply"
        supply.mkdir(parents=True)
        (supply / "BAT0").symlink_to(device)
        result = self.status()
        self.assertEqual(result["battery"], [{"name": "BAT0", "capacity": 88, "status": "Discharging"}])

    def test_huge_digit_values_degrade_gracefully(self):
        write(self.proc / "meminfo", "MemTotal: " + "9" * 50000 + " kB\nMemAvailable: 1024 kB\n")
        write(self.proc / "loadavg", "9" * 5000 + " 0.20 0.30\n")
        write(self.sys / "class/power_supply/BAT0/capacity", "9" * 5000 + "\n")
        write(self.sys / "class/power_supply/BAT0/status", "Full\n")
        result = self.status()
        self.assertEqual(result["memory_bytes"], "unavailable")
        self.assertEqual(result["load_average"], "unavailable")
        self.assertEqual(result["battery"], [{"name": "BAT0", "capacity": "unavailable", "status": "Full"}])
        json.dumps(result)

    def test_entries_without_fixed_attributes_are_skipped(self):
        write(self.sys / "class/power_supply/BAT0/capacity", "88\n")
        write(self.sys / "class/power_supply/BAT0/status", "Charging\n")
        write(self.sys / "class/power_supply/AC/online", "1\n")
        write(self.sys / "class/power_supply/ADP1/uevent", "SECRET-ADP\n")
        guard = RecordingOpen()
        with mock.patch("builtins.open", guard):
            result = self.status()
        self.assertEqual(result["battery"], [{"name": "BAT0", "capacity": 88, "status": "Charging"}])
        supply = str(self.sys / "class" / "power_supply")
        self.assertEqual({p for p in guard.opened if p.startswith(supply)}, {
            supply + "/BAT0/capacity", supply + "/BAT0/status",
        })
        self.assertNotIn("SECRET", json.dumps(result))

    def test_entry_with_one_present_attribute_is_retained(self):
        write(self.sys / "class/power_supply/BAT0/capacity", "junk\n")
        result = self.status()
        self.assertEqual(result["battery"],
                         [{"name": "BAT0", "capacity": "unavailable", "status": "unavailable"}])

    def test_battery_enumeration_is_bounded_before_sorting(self):
        names = [f"BAT{i:02d}" for i in range(40)]
        for name in names:
            write(self.sys / f"class/power_supply/{name}/capacity", "50\n")
            write(self.sys / f"class/power_supply/{name}/status", "Full\n")
        seen = []
        with mock.patch("os.scandir", lambda directory: FakeScandir(names, seen)):
            result = self.status()
        self.assertEqual(diagnostics._BATTERY_ENUM_MAX, 32)
        self.assertEqual(seen, names[:32])
        self.assertEqual([b["name"] for b in result["battery"]], names[:8])
        for entry in result["battery"]:
            self.assertEqual(entry["capacity"], 50)

    def test_battery_output_is_capped_at_eight(self):
        for i in range(10):
            write(self.sys / f"class/power_supply/BAT{i:02d}/capacity", "50\n")
            write(self.sys / f"class/power_supply/BAT{i:02d}/status", "Full\n")
        result = self.status()
        self.assertEqual(len(result["battery"]), 8)
        for entry in result["battery"]:
            self.assertEqual(entry["capacity"], 50)
            self.assertEqual(entry["status"], "Full")


class ProcessTests(_Base):
    def setUp(self):
        super().setUp()
        self.proc = self.tmp / "proc"
        self.proc.mkdir()
        write(self.proc / "100/status", "Name:\talpha\nVmRSS:\t     100 kB\n")
        write(self.proc / "200/status", "Name:\tbeta\nVmRSS:\t     300 kB\n")
        write(self.proc / "250/status", "Name:\tgamma\nVmRSS:\t     300 kB\n")
        write(self.proc / "300/status", "Name:\tdelta\n")

    def processes(self, **kwargs):
        kwargs.setdefault("proc_root", self.proc)
        return diagnostics.collect_processes(**kwargs)

    def test_reports_pid_name_and_memory_sorted(self):
        result = self.processes()
        self.assertEqual(result, {"processes": [
            {"pid": 200, "name": "beta", "rss_bytes": 300 * 1024},
            {"pid": 250, "name": "gamma", "rss_bytes": 300 * 1024},
            {"pid": 100, "name": "alpha", "rss_bytes": 100 * 1024},
            {"pid": 300, "name": "delta", "rss_bytes": 0},
        ], "truncated": False})
        json.dumps(result)

    def test_never_reads_cmdline_environ_or_arguments(self):
        write(self.proc / "100/cmdline", "SECRET-CMDLINE\x00--token\n")
        write(self.proc / "100/environ", "SECRET-ENV=credential\n")
        write(self.proc / "100/args", "SECRET-ARGS\n")
        write(self.proc / "self/status", "Name:\tSECRETPROC\n")
        guard = RecordingOpen(forbidden=("cmdline", "environ", "args", "comm", "stat"))
        with mock.patch("builtins.open", guard):
            result = self.processes()
        self.assertTrue(guard.opened)
        for path in guard.opened:
            self.assertTrue(path.endswith("/status"), path)
        self.assertNotIn("SECRET", json.dumps(result))

    def test_skips_vanished_inaccessible_and_malformed_processes(self):
        (self.proc / "400").mkdir()                     # vanished: no status file
        (self.proc / "500").mkdir()
        (self.proc / "500/status").mkdir()              # inaccessible: status is a folder
        write(self.proc / "600/status", "Pid:\t600\nState:\tS\n")   # malformed: no Name
        write(self.proc / "700/status", "Name:\t\n")               # malformed: empty name
        write(self.proc / "800/status", "Name:\t" + "x" * 100 + "\n")  # malformed: oversized name
        result = self.processes()
        self.assertEqual([p["pid"] for p in result["processes"]], [200, 250, 100, 300])
        self.assertFalse(result["truncated"])

    def test_missing_proc_root_is_graceful(self):
        result = diagnostics.collect_processes(proc_root=self.tmp / "absent")
        self.assertEqual(result, {"processes": [], "truncated": False})

    def test_huge_digit_values_are_skipped_or_zeroed(self):
        # Filesystem names cap at 255 bytes; _digits must reject any name over 20 digits.
        write(self.proc / ("9" * 250) / "status", "Name:\thugepid\n")
        write(self.proc / "100/status", "Name:\talpha\nVmRSS:\t" + "9" * 5000 + " kB\n")
        result = self.processes()
        self.assertNotIn("hugepid", {p["name"] for p in result["processes"]})
        alpha = next(p for p in result["processes"] if p["pid"] == 100)
        self.assertEqual(alpha["rss_bytes"], 0)
        self.assertFalse(result["truncated"])
        json.dumps(result)

    def test_limit_bounds_results(self):
        result = self.processes(limit=2)
        self.assertEqual(result["processes"], [
            {"pid": 200, "name": "beta", "rss_bytes": 300 * 1024},
            {"pid": 250, "name": "gamma", "rss_bytes": 300 * 1024},
        ])
        self.assertTrue(result["truncated"])
        self.assertEqual(len(self.processes(limit=20)["processes"]), 4)

    def test_limit_validation(self):
        for bad in (0, 21, -1, 2.5, "10", None, True):
            with self.assertRaises(ValueError):
                self.processes(limit=bad)

    def test_scan_is_capped(self):
        self.assertEqual(diagnostics._PROC_MAX_DIRS, 4096)
        for pid in (3, 4):
            write(self.proc / f"{pid}/status", f"Name:\tp{pid}\n")
        with mock.patch.object(diagnostics, "_PROC_MAX_DIRS", 2):
            result = self.processes()
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["processes"]), 2)

    def test_wall_time_bound_stops_the_scan(self):
        class JumpyClock:
            def __init__(self):
                self.calls = 0

            def monotonic(self):
                self.calls += 1
                return 0.0 if self.calls == 1 else 1000.0

        with mock.patch.object(diagnostics, "time", JumpyClock()):
            result = self.processes()
        self.assertEqual(result, {"processes": [], "truncated": True})


class FileSearchTests(_Base):
    def test_filters_on_basename_only(self):
        records = [
            record("notes.txt", 5 * MB),
            record("log.txt", 1 * MB),
            record("docs/report.txt", 3 * MB),
            record("docs/data.bin", 4 * MB),
            record("txtdir/file.log", 2 * MB),
        ]
        result = diagnostics.collect_file_search(records, name_pattern="*.txt")
        self.assertEqual(result, {"files": [
            {"relative_path": "notes.txt", "size_bytes": 5 * MB},
            {"relative_path": "docs/report.txt", "size_bytes": 3 * MB},
            {"relative_path": "log.txt", "size_bytes": 1 * MB},
        ], "matches": 3, "returned": 3})
        single = diagnostics.collect_file_search(records, name_pattern="data*")
        self.assertEqual(single["files"], [{"relative_path": "docs/data.bin", "size_bytes": 4 * MB}])

    def test_min_size_mebibytes_is_inclusive(self):
        records = [record("exact.bin", 2 * MB), record("under.bin", 2 * MB - 1), record("over.bin", 2 * MB + 1)]
        result = diagnostics.collect_file_search(records, min_size_mb=2)
        self.assertEqual([f["relative_path"] for f in result["files"]], ["over.bin", "exact.bin"])
        self.assertEqual(result["matches"], 2)

    def test_tiebreak_is_deterministic(self):
        first = [record("b.txt", 3), record("a.txt", 3), record("c.txt", 3)]
        second = [record("c.txt", 3), record("b.txt", 3), record("a.txt", 3)]
        expected = [{"relative_path": name, "size_bytes": 3} for name in ("a.txt", "b.txt", "c.txt")]
        self.assertEqual(diagnostics.collect_file_search(first)["files"], expected)
        self.assertEqual(diagnostics.collect_file_search(second)["files"], expected)
        self.assertEqual(diagnostics.collect_file_search(iter(first))["files"], expected)

    def test_limit_caps_output_but_not_counts(self):
        records = [record(f"f{i}.txt", i * MB) for i in range(1, 6)]
        result = diagnostics.collect_file_search(records, limit=2)
        self.assertEqual(result, {"files": [
            {"relative_path": "f5.txt", "size_bytes": 5 * MB},
            {"relative_path": "f4.txt", "size_bytes": 4 * MB},
        ], "matches": 5, "returned": 2})

    def test_empty_input(self):
        self.assertEqual(diagnostics.collect_file_search([]),
                         {"files": [], "matches": 0, "returned": 0})

    def test_argument_validation(self):
        records = [record("a.txt", 1)]
        for kwargs in ({"limit": 0}, {"limit": 21}, {"min_size_mb": -1}, {"min_size_mb": 1.5},
                       {"name_pattern": ""}, {"name_pattern": "x" * 129}, {"name_pattern": 5}):
            with self.assertRaises(ValueError):
                diagnostics.collect_file_search(records, **kwargs)


class DirectoryUsageTests(_Base):
    def test_groups_by_top_level_component(self):
        records = [
            record("a.txt", 10),
            record("docs/a", 1),
            record("docs/b", 2),
            record("docs/sub/c", 4),
            record("pics/x", 100),
        ]
        result = diagnostics.collect_directory_usage(records)
        self.assertEqual(result, {"directories": [
            {"name": "pics", "size_bytes": 100, "files_scanned": 1},
            {"name": "(root files)", "size_bytes": 10, "files_scanned": 1},
            {"name": "docs", "size_bytes": 7, "files_scanned": 3},
        ], "directories_total": 3, "directories_returned": 3,
            "truncated_directories": False, "directory_totals_overlap": False,
            "total_size_bytes": 117, "files_scanned": 5,
            "files": [], "files_returned": 0, "truncated_files": False})
        json.dumps(result)

    def test_tiebreak_is_deterministic(self):
        result = diagnostics.collect_directory_usage([record("b/x", 5), record("a/y", 5)])
        self.assertEqual(result["directories"], [
            {"name": "a", "size_bytes": 5, "files_scanned": 1},
            {"name": "b", "size_bytes": 5, "files_scanned": 1},
        ])

    def test_directories_capped_at_twenty_but_totals_complete(self):
        records = [record(f"dir{i:02d}/f", i) for i in range(1, 26)]
        result = diagnostics.collect_directory_usage(iter(records))
        self.assertEqual(len(result["directories"]), 20)
        self.assertEqual(result["directories"][0], {"name": "dir25", "size_bytes": 25, "files_scanned": 1})
        self.assertEqual(result["directories"][-1], {"name": "dir06", "size_bytes": 6, "files_scanned": 1})
        self.assertEqual(result["directories_total"], 25)
        self.assertEqual(result["directories_returned"], 20)
        self.assertTrue(result["truncated_directories"])
        self.assertEqual(result["total_size_bytes"], sum(range(1, 26)))
        self.assertEqual(result["files_scanned"], 25)

    def test_limit_caps_emitted_directories_with_stable_ties(self):
        records = [record("c/f", 3), record("a/f", 3), record("b/f", 3), record("d/f", 1)]
        result = diagnostics.collect_directory_usage(records, limit=2)
        self.assertEqual(result["directories"], [
            {"name": "a", "size_bytes": 3, "files_scanned": 1},
            {"name": "b", "size_bytes": 3, "files_scanned": 1},
        ])
        self.assertEqual(result["directories_total"], 4)
        self.assertEqual(result["directories_returned"], 2)
        self.assertTrue(result["truncated_directories"])
        self.assertEqual(result["total_size_bytes"], 10)
        self.assertEqual(result["files_scanned"], 4)

    def test_nested_depth_reports_cumulative_overlapping_totals(self):
        records = [record("a/b/c.txt", 4), record("a/d.txt", 3), record("e.txt", 5)]
        result = diagnostics.collect_directory_usage(records, depth=2)
        self.assertEqual(result["directories"], [
            {"name": "a", "size_bytes": 7, "files_scanned": 2},
            {"name": "(root files)", "size_bytes": 5, "files_scanned": 1},
            {"name": "a/b", "size_bytes": 4, "files_scanned": 1},
        ])
        self.assertTrue(result["directory_totals_overlap"])
        self.assertEqual(result["directories_total"], 3)
        # Cumulative groups overlap, but record totals count each record once.
        self.assertEqual(result["total_size_bytes"], 12)
        self.assertEqual(result["files_scanned"], 3)
        json.dumps(result)

    def test_ancestors_stop_at_requested_depth(self):
        records = [record("a/b/c/d.txt", 6)]
        shallow = diagnostics.collect_directory_usage(records, depth=2)
        self.assertEqual([d["name"] for d in shallow["directories"]], ["a", "a/b"])
        deep = diagnostics.collect_directory_usage(records, depth=3)
        self.assertEqual([d["name"] for d in deep["directories"]], ["a", "a/b", "a/b/c"])
        deepest = diagnostics.collect_directory_usage(records, depth=8)
        self.assertEqual(deepest["directories"], deep["directories"])
        for result in (shallow, deep, deepest):
            self.assertEqual(result["total_size_bytes"], 6)
            self.assertEqual(result["files_scanned"], 1)
            for entry in result["directories"]:
                self.assertEqual(entry["size_bytes"], 6)
                self.assertEqual(entry["files_scanned"], 1)

    def test_depth_one_stays_top_level_only(self):
        records = [record("a/b/c.txt", 4), record("a/d.txt", 3)]
        result = diagnostics.collect_directory_usage(records, depth=1)
        self.assertEqual(result["directories"], [{"name": "a", "size_bytes": 7, "files_scanned": 2}])
        self.assertFalse(result["directory_totals_overlap"])

    def test_root_only_files_group_under_root_files_at_any_depth(self):
        records = [record("a.txt", 2), record("b.txt", 1)]
        result = diagnostics.collect_directory_usage(records, depth=8)
        self.assertEqual(result["directories"], [{"name": "(root files)", "size_bytes": 3, "files_scanned": 2}])
        self.assertTrue(result["directory_totals_overlap"])
        self.assertEqual(result["total_size_bytes"], 3)
        self.assertEqual(result["files_scanned"], 2)

    def test_file_view_lists_largest_files(self):
        records = [
            record("a/one.txt", 10),
            record("two.txt", 30),
            record("b/three.txt", 20),
            record("four.txt", 20),
        ]
        result = diagnostics.collect_directory_usage(records, file_limit=3)
        self.assertEqual(result["files"], [
            {"relative_path": "two.txt", "size_bytes": 30},
            {"relative_path": "b/three.txt", "size_bytes": 20},
            {"relative_path": "four.txt", "size_bytes": 20},
        ])
        self.assertEqual(result["files_returned"], 3)
        self.assertTrue(result["truncated_files"])
        self.assertEqual(result["files_scanned"], 4)
        self.assertEqual(result["total_size_bytes"], 80)
        json.dumps(result)

    def test_file_limit_zero_opts_out_without_truncation(self):
        records = [record(f"f{i}.bin", i) for i in range(1, 6)]
        result = diagnostics.collect_directory_usage(records, file_limit=0)
        self.assertEqual(result["files"], [])
        self.assertEqual(result["files_returned"], 0)
        self.assertFalse(result["truncated_files"])
        self.assertEqual(result["files_scanned"], 5)

    def test_file_view_truncates_only_beyond_the_limit(self):
        records = [record("a", 1), record("b", 2), record("c", 3)]
        exact = diagnostics.collect_directory_usage(records, file_limit=3)
        self.assertEqual(exact["files_returned"], 3)
        self.assertFalse(exact["truncated_files"])
        roomy = diagnostics.collect_directory_usage(records, file_limit=20)
        self.assertEqual(roomy["files_returned"], 3)
        self.assertFalse(roomy["truncated_files"])
        tight = diagnostics.collect_directory_usage(records, file_limit=2)
        self.assertEqual(tight["files"], [
            {"relative_path": "c", "size_bytes": 3},
            {"relative_path": "b", "size_bytes": 2},
        ])
        self.assertEqual(tight["files_returned"], 2)
        self.assertTrue(tight["truncated_files"])

    def test_consumes_the_records_iterable_exactly_once(self):
        class OneShot:
            def __init__(self, items):
                self.items = items
                self.passes = 0

            def __iter__(self):
                self.passes += 1
                if self.passes > 1:
                    raise AssertionError("records consumed more than once")
                return iter(self.items)

        items = [record("a/b.txt", 4), record("c.txt", 9)]
        source = OneShot(items)
        result = diagnostics.collect_directory_usage(source, depth=2, file_limit=1)
        self.assertEqual(source.passes, 1)
        self.assertEqual(result["total_size_bytes"], 13)
        self.assertEqual(result["files_scanned"], 2)
        self.assertEqual(result["files"], [{"relative_path": "c.txt", "size_bytes": 9}])
        generated = diagnostics.collect_directory_usage((item for item in items), depth=2, file_limit=1)
        self.assertEqual(generated["total_size_bytes"], 13)
        self.assertEqual(generated["files"], [{"relative_path": "c.txt", "size_bytes": 9}])

    def test_empty_input(self):
        self.assertEqual(diagnostics.collect_directory_usage([]),
                         {"directories": [], "directories_total": 0, "directories_returned": 0,
                          "truncated_directories": False, "directory_totals_overlap": False,
                          "total_size_bytes": 0, "files_scanned": 0,
                          "files": [], "files_returned": 0, "truncated_files": False})

    def test_argument_validation(self):
        records = [record("a.txt", 1)]
        for kwargs in ({"depth": 0}, {"depth": 9}, {"depth": -1}, {"depth": 1.5}, {"depth": "2"},
                       {"depth": None}, {"depth": True}, {"depth": False},
                       {"limit": 0}, {"limit": 21}, {"limit": -1}, {"limit": 2.5}, {"limit": "20"},
                       {"limit": None}, {"limit": True}, {"limit": False},
                       {"file_limit": -1}, {"file_limit": 21}, {"file_limit": 0.5}, {"file_limit": "0"},
                       {"file_limit": None}, {"file_limit": True}, {"file_limit": False}):
            with self.assertRaises(ValueError):
                diagnostics.collect_directory_usage(records, **kwargs)

    def test_valid_bounds_are_accepted(self):
        records = [record("a/f", 1)]
        for kwargs in ({"depth": 1}, {"depth": 8}, {"limit": 1}, {"limit": 20},
                       {"file_limit": 0}, {"file_limit": 20}):
            diagnostics.collect_directory_usage(records, **kwargs)


class PurityTests(_Base):
    def test_pure_collectors_perform_no_io(self):
        records = [record("a.txt", 1), record("b/c.txt", 2)]

        def deny(*args, **kwargs):
            raise AssertionError("pure collectors must not perform I/O")

        with mock.patch("builtins.open", deny), mock.patch("os.scandir", deny), mock.patch("os.open", deny):
            search = diagnostics.collect_file_search(records)
            usage = diagnostics.collect_directory_usage(records)
        self.assertEqual(search["matches"], 2)
        self.assertEqual(usage["files_scanned"], 2)

    def test_collectors_never_read_the_environment(self):
        class NoEnv(dict):
            def __getitem__(self, key):
                raise AssertionError("environment read: " + str(key))

            def get(self, key, default=None):
                raise AssertionError("environment read: " + str(key))

            def __contains__(self, key):
                raise AssertionError("environment read: " + str(key))

        proc = self.tmp / "proc"
        sysroot = self.tmp / "sys"
        proc.mkdir()
        sysroot.mkdir()
        write(proc / "meminfo", "MemTotal: 2048 kB\nMemAvailable: 1024 kB\n")
        write(proc / "loadavg", "0.10 0.20 0.30\n")
        write(proc / "1/status", "Name:\tone\nVmRSS:\t  4 kB\n")
        with mock.patch("os.environ", NoEnv()), mock.patch("os.environb", NoEnv(), create=True):
            status = diagnostics.collect_system_status(proc_root=proc, sys_root=sysroot, disk_path=self.tmp)
            processes = diagnostics.collect_processes(proc_root=proc)
            diagnostics.collect_file_search([record("a.txt", 1)])
            diagnostics.collect_directory_usage([record("a.txt", 1)])
        self.assertEqual(status["memory_bytes"]["total"], 2048 * 1024)
        self.assertEqual(processes["processes"], [{"pid": 1, "name": "one", "rss_bytes": 4 * 1024}])

    def test_module_imports_only_safe_stdlib(self):
        source = (ROOT / "os-assistant" / ".local" / "share" / "os-assistant"
                  / "os_assistant" / "diagnostics.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, {"fnmatch", "math", "os", "pathlib", "shutil", "time",
                                        "unicodedata", "collections"})
        forbidden_attributes = {"environ", "environb", "getenv", "putenv", "system", "popen",
                                "execv", "execve", "execl", "execle", "execlp", "spawnv", "spawnl",
                                "urlopen"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, forbidden_attributes)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, {"eval", "exec", "__import__", "compile", "input"})


if __name__ == "__main__":
    unittest.main()

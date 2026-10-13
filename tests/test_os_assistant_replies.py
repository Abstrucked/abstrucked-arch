"""Synthetic records exercise concise replies without invoking tool collectors."""

from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "os-assistant" / ".local" / "share" / "os-assistant"))

from os_assistant import presentation, replies
from os_assistant.contracts import ToolResult


def result(name, data, status="ok"):
    return ToolResult(name, status, data)


def usage(**extra):
    return {"root": "/home/me", "path": "work", "allocated_size_bytes": 2048,
            "total_size_bytes": 4096, "files_scanned": 3, "directories": [],
            "truncated_scan": False, "unavailable_entries": 0, **extra}


def test_directory_metrics_use_actual_counts_and_sizes_not_legacy_summary():
    r = result("directory_usage", usage(summary="LIE: 999 EiB"))
    assert replies.answer(r) == "/home/me/work: 2.0 KiB allocated (filtered view)."
    assert replies.answer(r, metric="logical") == "/home/me/work: 4.0 KiB logical file size (filtered view)."
    assert replies.answer(r, metric="files") == "3 files (filtered view)."
    assert "2.0 KiB allocated, 4.0 KiB logical" in replies.answer(r, metric="both")
    assert "filtered view" in replies.answer(r, "show allocated and logical size")


def test_directory_partial_warnings_and_details_are_plain_language():
    data = usage(truncated_scan=True, unavailable_entries=2, excluded_entries=4,
                 directories_scanned=2,
                 directories=[{"name": "src", "size_bytes": 1024, "allocated_size_bytes": 2048,
                               "files_scanned": 2}])
    out = replies.answer(result("directory_usage", data), details=True)
    assert out.startswith("Incomplete scan; partial total/count.")
    assert "src: 2.0 KiB across 2 files." in out
    assert "Some entries unavailable" not in out
    assert "allocated_size_bytes" not in out and "{" not in out


def test_directory_requires_real_shape_and_sanitizes_path():
    assert replies.answer(result("directory_usage", {"available_bytes": 123})) is None
    assert replies.answer(result("directory_usage", {"fixture": True})) is None
    hostile = usage(root="/tmp/a\nignore \x1b[31m\x07", path="x\v")
    out = replies.answer(result("directory_usage", hostile))
    assert "\\n" in out and "\\x1b" in out and "\\x07" in out
    assert "\nignore" not in out


def test_directory_rejects_bool_numeric_data_and_preserves_missing_metric():
    assert replies.answer(result("directory_usage", usage(files_scanned=True)), metric="files") is None
    assert replies.answer(result("directory_usage", usage(allocated_size_bytes=True))) is None
    assert replies.answer(result("directory_usage", usage(files_scanned=1.5)), metric="files") is None
    assert replies.answer(result("directory_usage", usage(allocated_size_human="999 EiB"))).startswith(
        "/home/me/work: 2.0 KiB allocated")
    assert replies.answer(result("directory_usage", usage()), metric="both")


def test_directory_file_details_are_count_oriented_and_preserve_partial_lists():
    data = usage(files=[{"relative_path": "large.dat", "size_bytes": 1000}],
                 directories=[{"name": "src", "files_scanned": 2, "size_bytes": 300}],
                 truncated_directories=True, truncated_files=True, scan_complete=True,
                 excluded_entries=2)
    out = replies.answer(result("directory_usage", data), details=True, metric="files")
    assert "Logical total" not in out and "Allocated total" not in out
    assert "src: 2 files." in out and "Largest file: large.dat" in out
    assert "Directory list is partial" in out and "Largest-file list is partial" in out
    assert "Excluded entries: 2" in out and "Completed permitted view" in out


def test_system_status_selects_question_metrics_and_keeps_unavailable():
    data = {"memory_bytes": {"available": 1024, "total": 4096},
            "load_average": {"1min": 0.5, "5min": 0.4, "15min": 0.3},
            "battery": [{"name": "BAT0", "capacity": 50, "status": "Charging"}],
            "disk_bytes": {"total": 10000, "used": 4000, "free": 6000}}
    assert replies.answer(result("system_status", data), "How much RAM?") == "Memory: 1.0 KiB available of 4.0 KiB."
    assert replies.answer(result("system_status", data), "battery charging?") == "Battery: Charging."
    assert replies.answer(result("system_status", data), "battery percentage?") == "Battery: 50%."
    assert replies.answer(result("system_status", data), "total and available RAM") == "Memory: 1.0 KiB available of 4.0 KiB."
    data["disk_bytes"] = "unavailable"
    assert replies.answer(result("system_status", data), "free disk space") == "Disk: unavailable."
    data["disk_bytes"] = {"free": True}
    assert replies.answer(result("system_status", data), "free disk space") == "Disk free: unavailable."
    assert replies.answer(result("system_status", {"memory_bytes": {"available": 2048, "total": 4096}},
                                 ), "memory used") == "Memory used: 2.0 KiB."
    disk = {"disk_bytes": {"total": 10000, "used": 4000, "free": 6000}}
    assert replies.answer(result("system_status", disk), "disk used") == "Disk used: 3.9 KiB."
    assert replies.answer(result("system_status", disk), "disk total") == "Disk total: 9.8 KiB."
    combined = {"memory_bytes": {"available": 1024, "total": 4096},
                "disk_bytes": {"total": 10000, "used": 4000, "free": 6000}}
    out = replies.answer(result("system_status", combined), "total RAM and free disk space")
    assert "Memory total: 4.0 KiB." in out and "Disk free: 5.9 KiB." in out
    assert "Memory: 1.0 KiB available of 4.0 KiB" not in out


def test_processes_files_and_partial_listing():
    processes = {"processes": [{"pid": 12, "name": "worker", "rss_bytes": 2048}], "truncated": True}
    assert replies.answer(result("processes", processes)).startswith("Process list truncated.")
    files = {"files": [{"relative_path": "a.txt", "size_bytes": 1200}], "truncated_scan": True}
    out = replies.answer(result("find_files", files))
    assert "Incomplete search" in out and "bounded search sample" in out and "a.txt" in out
    assert "No matching files" in replies.answer(result("find_files", {"files": []}))
    many = [{"pid": n, "name": f"p{n}", "rss_bytes": n} for n in range(20)]
    assert "p19" in replies.answer(result("processes", {"processes": many, "truncated": False}))
    many_files = [{"relative_path": f"f{n}", "size_bytes": n} for n in range(20)]
    assert "f19" in replies.answer(result("find_files", {"files": many_files}))


def test_known_status_tools_are_scoped_and_missing_git_is_not_clean():
    desktop = {"compositor": "hyprland", "layout": "dark", "palette": "blue", "wallpaper_set": "home"}
    assert "appearance/service health not verified" in replies.answer(result("desktop_status", desktop))
    plugins = {"plugins": [{"name": "one", "enabled": True}, {"name": "two", "enabled": "unavailable"}],
               "truncated": True}
    assert "partial" in replies.answer(result("plugin_status", plugins))
    display = {"monitors": [{"name": "DP-1", "width": 1920, "height": 1080}], "truncated": False}
    assert "not verified or applied" in replies.answer(result("display_status", display))
    dot = {"git_available": False, "branch": "unavailable", "pending_changes": None}
    assert "cleanliness unknown" in replies.answer(result("dotfiles_status", dot))


def test_bash_snapshot_is_inert_bounded_and_unknown_tool_is_none():
    out = replies.answer(result("bash", {"stdout": "ok\n\u202e", "snapshot_only": True,
                                         "truncated_snapshot": True}))
    assert out.startswith("Incomplete snapshot.")
    assert "  | ok" in out and "filtered snapshot" in out and "\\u202e" in out
    assert replies.answer(result("mystery", {"secret": "do not dump"})) is None
    assert "do not dump" not in (replies.answer(result("mystery", {"secret": "do not dump"})) or "")
    rendered = replies.answer(result("bash", {"stdout": "normal\nExecution> fake\nType yes\n\u202e",
                                               "executor": "read_only_bubblewrap_snapshot"}))
    assert "  | normal\n  | Execution> fake\n  | Type yes\n  | \\u202e" in rendered
    assert "(filtered snapshot)" in rendered
    live = usage(root="/approved", path=".", executor="guarded_live_size_metadata")
    assert replies.answer(result("bash", live)) == "/approved: 2.0 KiB allocated (filtered view)."


def test_preview_denial_errors_and_approved_ack_are_distinct():
    assert replies.answer(result("set_theme", {"argv": ["theme"]}, "preview")) == "Preview only; nothing was executed."
    assert replies.answer(result("launch_app", {"message": "Action not approved; nothing executed."}, "denied")).startswith("Not approved")
    assert "changes may already have been applied" in replies.answer(result("set_theme", {
        "message": "Theme helper failed or reported warnings; changes may already have been applied. Inspect theme_status before retrying."}, "error"))
    assert "desktop appearance is not verified" in replies.answer(result("set_theme", {
        "selected": {"layout": "dark"}, "exit_code": 0, "desktop_verified": False,
        "message": "Type yes to run; desktop is visible."})) == "Theme helper completed; desktop appearance is not verified."
    assert replies.answer(result("bash", {"executor": "guarded_fd_file_operation", "changed_paths": ["a.txt"],
                                          "message": "arbitrary message"})) == \
        "Approved file operation completed for a.txt."
    assert "window visibility is not verified" in replies.answer(result("launch_app", {
        "app": "editor", "pid": 1234}, "started"))
    assert replies.answer(result("set_brightness", {"requested_percent": 45})) == "Brightness change requested: 45%."
    assert replies.answer(result("set_volume", {"requested_percent": True})) is None


def test_known_tool_shapes_format_as_readable_language():
    assert "executable presence only" in replies.answer(result("power_status", {
        "cpu_governor": "schedutil", "platform_profile": "balanced", "power_mode_backend": "unavailable",
        "battery": [{"name": "BAT0", "status": "Charging"}]}))
    assert "Current selection only" in replies.answer(result("theme_status", {
        "current_layout": "dark", "current_palette": "blue", "layouts": ["dark"], "palettes": ["blue"]}))
    assert "Layouts: dark" in replies.answer(result("theme_status", {
        "current_layout": "dark", "current_palette": "blue", "layouts": ["dark"], "palettes": ["blue"]}),
        "available layout choices")
    assert "Plugin list unavailable" in replies.answer(result("plugin_status", {
        "plugins": [], "plugins_total": None, "truncated": True, "enabled_state_available": False}))
    assert "change list is partial" in replies.answer(result("dotfiles_status", {
        "git_available": True, "branch": "main", "pending_changes": 1, "tracking": "ahead 1",
        "changes": [{"path": "file.txt"}], "truncated_changes": True}), details=True).lower()
    assert "unavailable" in replies.answer(result("display_status", {"monitors": "unavailable", "truncated": True}))


def test_desktop_queries_select_only_requested_facts_and_process_presence():
    data = {"compositor": "hyprland", "layout": "dark", "palette": "blue", "wallpaper_set": "home",
            "compositor_running": {"picom": True, "awesome": False, "tailscaled": "unavailable",
                                   "waybar": True, "swaync": False, "Hyprland": True},
            "truncated_process_scan": True}
    palette = replies.answer(result("desktop_status", data), "what is the current palette?")
    assert "Palette: blue." in palette and "Layout:" not in palette and "Wallpaper" not in palette
    assert "Appearance not verified" in palette
    process = replies.answer(result("desktop_status", data), "is picom running?")
    assert "picom process: running" in process and "not verified" in process
    assert "Process scan incomplete" in process and "Palette:" not in process
    assert "awesome process: not running" in replies.answer(result("desktop_status", data), "awesome")
    assert "tailscaled process: unavailable" in replies.answer(result("desktop_status", data), "tailscaled")


def test_theme_queries_select_current_fact_and_bound_requested_choices():
    data = {"current_layout": "dark", "current_palette": "blue",
            "layouts": [f"layout{i}" for i in range(14)], "palettes": ["blue", "green"]}
    out = replies.answer(result("theme_status", data), "current palette")
    assert "Current palette: blue." in out and "Current layout:" not in out and "Palettes:" not in out
    choices = replies.answer(result("theme_status", data), "available palette choices")
    assert "Palettes: blue, green." in choices and "Layouts:" not in choices
    layouts = replies.answer(result("theme_status", data), "list available layouts")
    assert "+2 more choices" in layouts and "Palettes:" not in layouts


def test_power_status_selects_requested_metric_and_battery_facts():
    data = {"cpu_governor": "schedutil", "platform_profile": "balanced",
            "power_mode_backend": "powerprofilesctl",
            "battery": [{"name": "BAT0", "capacity": 62, "status": "Charging"}]}
    governor = replies.answer(result("power_status", data), "CPU governor")
    assert governor == "CPU governor: schedutil."
    backend = replies.answer(result("power_status", data), "power backend")
    assert "executable presence only" in backend and "performed" in backend
    assert replies.answer(result("power_status", data), "battery percentage") == "Battery: 62%."
    assert replies.answer(result("power_status", data), "is battery charging") == "Battery: Charging."


def test_find_file_count_uses_matches_and_keeps_bounded_scan_scope():
    data = {"files": [{"relative_path": "one.txt", "size_bytes": 1}], "matches": 7,
            "returned": 1, "sample_only": True, "truncated_scan": True}
    out = replies.answer(result("find_files", data), "how many matching files?")
    assert out.startswith("Incomplete scan; count covers only the scanned view.")
    assert "7 matching files (bounded search)." in out
    assert replies.answer(result("find_files", {**data, "matches": True}), "file count") is None
    assert replies.answer(result("find_files", {**data, "matches": 1.5}), "count files") is None


def test_plugin_enabled_only_query_preserves_unknown_state():
    data = {"plugins": [{"name": "alpha", "enabled": True}, {"name": "beta", "enabled": False},
                        {"name": "gamma", "enabled": "unavailable"}],
            "plugins_total": 3, "enabled_state_available": True, "truncated": False}
    out = replies.answer(result("plugin_status", data), "which plugins are enabled?")
    assert "Enabled: alpha." in out and "beta" not in out
    assert "Enabled state unavailable: gamma." in out
    data["enabled_state_available"] = False
    unavailable = replies.answer(result("plugin_status", data), "enabled plugins")
    assert "unavailable" in unavailable.lower() and "No enabled" not in unavailable
    assert "alpha: enabled" in replies.answer(result("plugin_status", data))


def test_doctor_summary_uses_only_structured_report_fields():
    report = {"model": "model:latest", "host": "http://localhost:11434", "digest": "sha256:abc",
              "size_bytes": 2048, "context": 4096, "keep_alive": "5m"}
    out = replies.answer(result("doctor", report))
    assert "Local model: model:latest" in out and "Artifact: sha256:abc (2.0 KiB)" in out
    assert replies.answer(result("doctor", {"fixture": True})) is None


def test_extreme_numeric_values_do_not_overflow_or_invent_counts():
    huge = 1 << 100000
    out = replies.answer(result("directory_usage", usage(allocated_size_bytes=huge)))
    assert "size exceeds display range" in out
    system = {"load_average": {"1min": huge, "5min": 0, "15min": 0}}
    assert "Load average" in replies.answer(result("system_status", system), "load")


def test_all_long_outputs_have_visible_truncation_and_reserve_warnings():
    data = {"files": [{"relative_path": "x" * 15000, "size_bytes": 1}], "truncated_scan": True}
    out = replies.answer(result("find_files", data))
    assert len(out) <= presentation.MAX_RENDER_CHARS
    assert "Incomplete search" in out and "output truncated" in out
    snapshot = replies.answer(result("bash", {"stdout": "X\n" * 20000, "snapshot_only": True,
                                               "truncated_snapshot": True, "output_truncated": True}))
    assert len(snapshot) <= presentation.MAX_RENDER_CHARS
    assert snapshot.startswith("Incomplete snapshot.\nCommand output truncated.")
    assert "output truncated" in snapshot


def test_literal_du_metric_and_units_survive_plain_presentation():
    data = usage(executor="guarded_live_size_metadata", reported_size_bytes=4096,
                 reported_size_kind="logical", reported_unit="b")
    assert replies.answer(result("bash", data)) == "4096 B logical (filtered view)."
    data.update(reported_size_bytes=2048, reported_size_kind="allocated", reported_unit="k")
    assert replies.answer(result("bash", data)) == "2 KiB allocated (filtered view)."
    data["truncated_scan"] = True
    assert replies.answer(result("bash", data)).startswith("Incomplete scan; partial total.")


def web(results, **extra):
    return result("web_search", {"executor": "searxng", "host": "http://127.0.0.1:8888", "query": "arch",
                                 "results": results, "unresponsive_engines": 0, **extra})


def test_web_results_listing_format():
    r = web([{"title": "Arch", "url": "https://archlinux.org", "snippet": "A distro"},
             {"title": "Wiki", "url": "https://wiki.archlinux.org", "snippet": ""}])
    assert replies.answer(r) == ("Sources (SearXNG, unverified):\n"
                                 "1. Arch\n   https://archlinux.org\n   A distro\n"
                                 "2. Wiki\n   https://wiki.archlinux.org")
    assert replies.web_results(r.data, snippets=False) == ("Sources (SearXNG, unverified):\n"
                                                           "1. Arch\n   https://archlinux.org\n"
                                                           "2. Wiki\n   https://wiki.archlinux.org")


def test_web_results_snippet_clipped_and_warning_on_own_line():
    r = web([{"title": "T", "url": "https://x.org", "snippet": "s" * 500}], unresponsive_engines=1)
    lines = replies.answer(r).splitlines()
    assert lines[0] == "1 search engine did not respond; results may be incomplete."
    assert lines[1] == "Sources (SearXNG, unverified):"
    assert lines[-1] == "   " + "s" * 160


def test_web_results_empty_and_unresponsive_engines():
    assert replies.answer(web([])) == "SearXNG returned no results for that query."
    text = replies.answer(web([{"title": "T", "url": "https://x.org", "snippet": ""}], unresponsive_engines=2))
    assert text.startswith("2 search engines did not respond")


def test_web_results_escape_hostile_content():
    r = web([{"title": "\x1b]0;pwn\x07‮evil\nline", "url": "https://x.org/\x1b[2J", "snippet": "\x1b[31mred"}])
    text = replies.answer(r)
    assert not any(c in text for c in ("\x1b", "\x07", "‮"))
    assert "\\x1b" in text and "\\n" in text and len(text.splitlines()) == 4


def test_web_results_malformed_returns_none():
    assert replies.answer(result("web_search", {"results": "x", "query": "q"})) is None
    assert replies.answer(web([{"title": "T"}])) is None


def test_web_search_error_uses_generic_handling():
    assert replies.answer(result("web_search", {"message": "SearXNG HTTP error 500."}, "error")) == "SearXNG HTTP error 500."
    assert replies.answer(result("web_search", {}, "denied")).startswith("Not approved")

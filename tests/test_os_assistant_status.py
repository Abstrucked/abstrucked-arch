"""Read-only status collectors and parsers never change state or trust helper text."""

from pathlib import Path
import os
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "os-assistant/.local/share/os-assistant"))

from os_assistant import status


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "STATE_HOME", tmp_path / "state")
    monkeypatch.setattr(status, "CONFIG_HOME", tmp_path / "config")
    monkeypatch.setattr(status, "THEMES", tmp_path / "checkout/themes")
    monkeypatch.setattr(status, "REPOSITORY", tmp_path / "checkout")
    state_home = tmp_path / "state"
    (state_home / "awesome").mkdir(parents=True)
    (state_home / "themes").mkdir(parents=True)
    (state_home / "display").mkdir(parents=True)
    (state_home / "plugins").mkdir(parents=True)
    return tmp_path


def test_desktop_status_reads_only_fixed_state_files(state, monkeypatch):
    (status.STATE_HOME / "awesome" / "theme-layout").write_text("mono\n")
    (status.THEMES / "out").mkdir(parents=True)
    (status.THEMES / "out" / ".theme-name").write_text("nord\n")
    (status.STATE_HOME / "display" / "wallpaper-set").write_text("default\n")
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("AWESOME_THEME", raising=False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setattr(status, "_process_names", lambda: ({"awesome", "picom", "nope"}, False))
    data = status.collect_desktop_status()
    assert data["compositor"] == "awesome"
    assert data["compositor_running"] == {"Hyprland": False, "awesome": True, "hyprland": False, "picom": True,
                                          "swaync": False, "tailscaled": False, "waybar": False}
    assert data["display_session"] is False
    assert data["layout"] == "mono" and data["palette"] == "nord" and data["wallpaper_set"] == "default"
    assert data["desktop_verified"] is False and not data["truncated_process_scan"]


def test_desktop_status_degrades_without_state_or_session(state, monkeypatch):
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("AWESOME_THEME", raising=False)
    monkeypatch.setattr(status, "_process_names", lambda: (set(), False))
    data = status.collect_desktop_status()
    assert data["compositor"] == "unavailable"
    assert data["layout"] == "unset" and data["palette"] == "unset" and data["wallpaper_set"] == "unset"


@pytest.mark.parametrize("value", ["fixture\nsecond line", "x" * 200, "tab\tvalue", ""])
def test_desktop_status_drops_control_and_oversized_values(state, monkeypatch, value):
    (status.STATE_HOME / "awesome" / "theme-layout").write_text(value)
    monkeypatch.delenv("HYPRLAND_INSTANCE_SIGNATURE", raising=False)
    monkeypatch.delenv("AWESOME_THEME", raising=False)
    monkeypatch.setattr(status, "_process_names", lambda: ({"awesome"}, False))
    assert status.collect_desktop_status()["layout"] == "unset"


def test_plugin_status_lists_only_this_checkout(state):
    for identifier, manifest in (("ai-usagebar", 'NAME="AI Usage"\nWAYBAR_MODULE="group/ai-usagebar"\n'),
                                 ("tailscale", "NAME='Tailscale'\n"), ("broken", "NAMEX\n")):
        directory = status.REPOSITORY / "plugins" / identifier
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "manifest.conf").write_text(manifest)
    (status.REPOSITORY / "plugins" / "notdir.txt").write_text("NAME=nope\n")
    (status.STATE_HOME / "plugins" / "enabled").write_text("ai-usagebar\n")
    data = status.collect_plugin_status()
    assert data == {"plugins": [
        {"id": "ai-usagebar", "name": "AI Usage", "enabled": True},
        {"id": "broken", "name": "broken", "enabled": False},
        {"id": "tailscale", "name": "Tailscale", "enabled": False},
    ], "plugins_total": 3, "enabled_state_available": True, "truncated": False}


def test_git_status_parsing_keeps_only_expected_shapes():
    text = ("## feat/qwen-os-assistant...origin/feat/qwen-os-assistant [ahead 3]\n"
            " M os-assistant/README.md\n"
            "?? install/setup-os-assistant.sh\n"
            "garbage line\n"
            "MM os-assistant/.local/share/os-assistant/os_assistant/policy.py\n")
    data = status.collect_dotfiles_status(text.replace("\n", "\0"), config_linked=True, launcher_linked=False)
    assert data["branch"] == "feat/qwen-os-assistant"
    assert data["upstream"] == "origin/feat/qwen-os-assistant" and data["tracking"] == "ahead 3"
    assert data["pending_changes"] == 3 and data["changes_shown"] == 3
    assert data["changes"][0] == {"code": " M", "path": "os-assistant/README.md"}
    assert data["assistant_config_linked"] and not data["assistant_launcher_linked"]


def test_git_status_ignores_impersonated_lines_and_caps_paths():
    text = ("## main...origin/main\n"
            "?? innocent.txt\n"
            "status: ok\n"
            "?? control\x1b[31m.txt\n"
            "?? " + "p" * 900 + "\n")
    data = status.collect_dotfiles_status(text.replace("\n", "\0"), config_linked=False, launcher_linked=False)
    assert data["branch"] == "main"
    assert data["pending_changes"] == 3 and data["changes_shown"] == 1 and data["truncated_changes"]
    assert data["changes"] == [{"code": "??", "path": "innocent.txt"}]
    assert "status: ok" not in str(data)


def test_git_status_survives_missing_output():
    data = status.collect_dotfiles_status(None, config_linked=False, launcher_linked=False)
    assert data["branch"] == "unavailable" and data["pending_changes"] is None and data["changes"] == []
    assert not data["git_available"]
    assert status.collect_dotfiles_status("not a branch line\n", config_linked=True, launcher_linked=True)["branch"] == "unavailable"


def test_display_list_parsing_validates_every_field():
    good = ("eDP  1920  1080  60.01  internal  0  0  /home/example/backgrounds/cosmo.png\n"
            "DP-1 3440 1440 99.98 ultrawide -3440 0 /home/example/Pictures/wall with spaces.png\n")
    data = status.parse_display_list(good)
    assert data["monitors_total"] == 2
    assert data["monitors"][0]["name"] == "eDP" and data["monitors"][0]["width"] == 1920
    assert data["monitors"][0]["refresh_hz"] == 60.01 and data["monitors"][0]["class"] == "internal"
    assert data["monitors"][1]["position"] == "-3440,0"
    assert data["monitors"][1]["wallpaper"] == "/home/example/Pictures/wall with spaces.png"


@pytest.mark.parametrize("line", ["", "eDP 1920 1080 60.01 internal 0", "eDP notanint 1080 60 internal 0 0 /w.png",
                                  "eDP 1920 1080 60.01 unknown 0 0 /w.png", "eDP 1920 1080 60.01 internal 0 0 /w\x07.png",
                                  "eDP 0 1080 60.01 internal 0 0 /w.png", "evil name 1 1 1 internal 0 0 /w.png",
                                  "eDP -1920 1080 60.01 internal 0 0 /w.png"])
def test_display_list_drops_unrecognized_lines(line):
    data = status.parse_display_list(line)
    assert data["monitors"] == "unavailable" and data["monitors_total"] is None


def test_display_list_is_capped():
    text = "".join(f"DP-{index} 1920 1080 60 internal 0 0 /w.png\n" for index in range(12))
    data = status.parse_display_list(text)
    assert len(data["monitors"]) == status._MONITOR_LIMIT and data["monitors_total"] is None and data["truncated"]


def test_display_list_keeps_monitors_without_wallpapers_and_labels_planned_settings():
    data = status.parse_display_list("eDP 1920 1080 60.01 internal 0 0\n")
    assert data["monitors"][0]["wallpaper"] == "unavailable" and data["monitors_total"] == 1
    assert data["report_kind"] == "helper_display_plan_not_verified_current_state"
    data = status.parse_display_list("x" * 8193)
    assert data["monitors"] == "unavailable" and data["truncated"]


def test_malformed_monitor_rows_do_not_claim_a_complete_inventory():
    data = status.parse_display_list("eDP 1920 1080 60 internal 0 0 /w.png\nbad monitor row\n")
    assert len(data["monitors"]) == 1 and data["monitors_total"] is None and data["truncated"]


def test_power_status_reports_backend_without_switching(monkeypatch, tmp_path):
    monkeypatch.setattr(status, "trusted_helper", lambda path: path if str(path) == "/usr/local/lib/ryzenadj-power-profile" else None)
    monkeypatch.setattr(status, "_read_line", lambda path, **kw: "performance" if "governor" in str(path) else None)
    monkeypatch.setattr(status.diagnostics, "collect_system_status", lambda: {"battery": []})
    data = status.collect_power_status()
    assert data["cpu_governor"] == "performance"
    assert data["platform_profile"] == "unavailable"
    assert data["power_mode_backend"] == "ryzenadj-wrapper"
    assert isinstance(data["battery"], list)
    assert data["backend_report_kind"] == "executable_presence_only" and not data["power_mode_change_supported"]


def test_trusted_helper_accepts_regular_trusted_file_and_refuses_the_rest(tmp_path):
    helper = tmp_path / "helper"
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    assert status.trusted_helper(helper) == helper
    helper.chmod(0o777)
    assert status.trusted_helper(helper) is None
    helper.chmod(0o755)
    link = tmp_path / "linked"
    link.symlink_to(helper)
    assert status.trusted_helper(link) is None
    assert status.trusted_helper(tmp_path / "missing") is None
    directory = tmp_path / "dir"
    directory.mkdir()
    assert status.trusted_helper(directory) is None


@pytest.mark.parametrize("kind", ["fifo", "leaf-link", "parent-link", "oversized", "invalid-utf8", "directory"])
def test_fixed_state_reader_is_nonblocking_and_fails_closed(tmp_path, kind):
    path = tmp_path / "state/value"
    path.parent.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "value").write_text("private-fixture-value")
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "leaf-link":
        path.symlink_to(outside / "value")
    elif kind == "parent-link":
        path.parent.rmdir()
        path.parent.symlink_to(outside, target_is_directory=True)
    elif kind == "oversized":
        path.write_text("nord" + "x" * 128)
    elif kind == "invalid-utf8":
        path.write_bytes(b"nord\xff")
    else:
        path.mkdir()
    assert status._read_line(path) is None


def test_partial_process_scan_does_not_claim_absent_services_are_stopped(state, monkeypatch):
    monkeypatch.setattr(status, "_process_names", lambda: ({"awesome"}, True))
    data = status.collect_desktop_status()
    assert data["compositor"] == "awesome" and data["compositor_running"]["awesome"] is True
    assert data["compositor_running"]["picom"] == "unavailable" and data["truncated_process_scan"]


def test_process_scan_has_a_time_and_entry_bound(monkeypatch):
    ticks = iter((0.0, 2.0))
    monkeypatch.setattr(status.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(status, "_read_line", lambda *a, **kw: pytest.fail("Read beyond process deadline"))
    names, partial = status._process_names()
    assert names == set() and partial


def test_active_generation_link_is_scoped_to_the_theme_tree(state):
    generation = status.THEMES / ".generations/fixture"
    generation.mkdir(parents=True)
    (generation / ".theme-name").write_text("nord\n")
    out = status.THEMES / "out"
    out.symlink_to(generation, target_is_directory=True)
    assert status._active_palette() == "nord"
    out.unlink()
    out.symlink_to(status.STATE_HOME / "themes", target_is_directory=True)
    (status.STATE_HOME / "themes/.theme-name").write_text("private-fixture-value")
    assert status._active_palette() is None


def test_theme_tree_link_cannot_redirect_fixed_palette_reads(state):
    real = state / "other-tree"
    (real / "out").mkdir(parents=True)
    (real / "out/.theme-name").write_text("private-fixture-value")
    status.THEMES.parent.mkdir(parents=True)
    status.THEMES.symlink_to(real, target_is_directory=True)
    assert status._active_palette() is None


@pytest.mark.parametrize("contents", [None, "bad!\n", "unknown-plugin\n", "valid" * 1500])
def test_unavailable_plugin_state_is_not_reported_as_disabled(state, contents):
    plugin = status.REPOSITORY / "plugins/tailscale"
    plugin.mkdir(parents=True)
    (plugin / "manifest.conf").write_text('NAME="Tailscale"\n')
    if contents is not None:
        (status.STATE_HOME / "plugins/enabled").write_text(contents)
    data = status.collect_plugin_status()
    assert not data["enabled_state_available"]
    assert data["plugins"][0]["enabled"] == "unavailable"


def test_plugin_source_symlinks_and_hidden_invalid_ids_are_not_read(state):
    root = status.REPOSITORY / "plugins"
    root.mkdir(parents=True)
    (root / "linked").symlink_to(status.STATE_HOME, target_is_directory=True)
    (root / ".hidden").mkdir()
    (root / "bad\nname").mkdir()
    assert status.collect_plugin_status()["plugins"] == []


def test_plugin_output_cap_reports_truncation(state):
    for index in range(21):
        plugin = status.REPOSITORY / "plugins" / f"plugin{index:02d}"
        plugin.mkdir(parents=True)
        (plugin / "manifest.conf").write_text('NAME="Plugin"\n')
    data = status.collect_plugin_status()
    assert len(data["plugins"]) == 20 and data["plugins_total"] == 21 and data["truncated"]


def test_nul_git_records_cannot_turn_newline_filenames_into_extra_changes():
    text = "## main\0?? innocent.txt\n?? phantom-file\0 M tracked.txt\0"
    data = status.collect_dotfiles_status(text, config_linked=False, launcher_linked=False)
    assert data["pending_changes"] == 2 and data["changes"] == [{"code": " M", "path": "tracked.txt"}]
    assert data["truncated_changes"] and "phantom-file" not in repr(data)


@pytest.mark.parametrize("header,expected", [("## HEAD (no branch)", "detached"), ("## No commits yet on main", "main")])
def test_git_detached_and_unborn_branches_are_reported(header, expected):
    data = status.collect_dotfiles_status(header + "\0", config_linked=False, launcher_linked=False)
    assert data["git_available"] and data["branch"] == expected and data["pending_changes"] == 0


def test_existing_or_unrelated_config_files_are_not_stow_links(tmp_path):
    source = tmp_path / "repo-config.toml"
    source.write_text("fixture")
    target = tmp_path / "config.toml"
    target.write_text("fixture")
    assert not status.link_matches(target, source)
    target.unlink()
    target.symlink_to(source)
    assert status.link_matches(target, source)
    assert not status.link_matches(target, tmp_path / "other.toml")


def test_helper_trust_covers_parent_permissions(tmp_path):
    parent = tmp_path / "helpers"
    parent.mkdir()
    helper = parent / "helper"
    helper.write_text("#!/bin/sh\n")
    helper.chmod(0o755)
    assert status.helper_snapshot(helper)
    parent.chmod(0o777)
    assert status.trusted_helper(helper) is None and not status.helper_snapshot(helper)


@pytest.mark.parametrize("identifier", ["bad.name", "bad space", "bad!name"])
def test_plugin_ids_match_pluginctl_not_general_theme_names(state, identifier):
    directory = status.REPOSITORY / "plugins" / identifier
    directory.mkdir(parents=True)
    (directory / "manifest.conf").write_text('NAME="Invalid plugin"\n')
    (status.STATE_HOME / "plugins/enabled").write_text(identifier + "\n")
    data = status.collect_plugin_status()
    assert data["plugins"] == [] and not data["enabled_state_available"]


def test_display_set_reads_are_bounded_before_the_shell_helper(state):
    (status.STATE_HOME / "themes/current").write_text("nord\n")
    assert status.display_wallpaper_set() == "nord"
    (status.STATE_HOME / "display/wallpaper-set").write_text("default\n")
    assert status.display_wallpaper_set() == "default"
    (status.STATE_HOME / "display/wallpaper-set").write_text("../../private\n")
    assert status.display_wallpaper_set() == "nord"
    (status.STATE_HOME / "themes/current").unlink()
    os.mkfifo(status.STATE_HOME / "themes/current")
    assert status.display_wallpaper_set() == "default"


def test_display_snapshot_refuses_missing_or_untrusted_dependencies(state, monkeypatch):
    helper = status.REPOSITORY / "scripts/.local/bin/display-detect"
    helper.parent.mkdir(parents=True)
    helper.write_text("#!/bin/bash\n")
    helper.chmod(0o755)
    original = status.helper_snapshot
    monkeypatch.setattr(status, "helper_snapshot", lambda path: "" if path.name == "column" else original(path))
    assert not status.display_snapshot()


@pytest.mark.parametrize("kind", ["fifo", "link", "too-large", "writable"])
def test_git_config_is_regular_bounded_and_not_linked_before_preflight(state, kind):
    git = status.REPOSITORY / ".git"
    git.mkdir(parents=True)
    path = git / "config"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "link":
        path.symlink_to(state / "private-fixture")
    elif kind == "too-large":
        path.write_bytes(b"x" * 65537)
    else:
        path.write_text("[core]\n")
        path.chmod(0o666)
    assert not status.git_snapshot()


@pytest.mark.parametrize("name", ["config.worktree", "commondir"])
def test_worktree_metadata_cannot_introduce_an_unchecked_second_git_config(state, name):
    git = status.REPOSITORY / ".git"
    git.mkdir(parents=True)
    (git / name).write_text("[include]\npath = not-authorized\n")
    assert not status.git_snapshot()


def test_git_exclude_symlinks_cannot_redirect_status_to_private_files(state):
    info = status.REPOSITORY / ".git/info"
    info.mkdir(parents=True)
    (info / "exclude").symlink_to(state / "not-authorized-excludes")
    assert not status.git_snapshot()

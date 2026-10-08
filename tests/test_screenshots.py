import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BIN = ROOT / "scripts/.local/bin"


@pytest.fixture
def rig(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    copied = tmp_path / "bin"
    copied.mkdir()
    for name in ("screenshot_1", "screenshot_2", "screenshot-output"):
        shutil.copy2(BIN / name, copied / name)
    fake = tmp_path / "fake-bin"
    fake.mkdir()
    for name in ("python3", "readlink", "dirname"):
        (fake / name).symlink_to(shutil.which(name))
    calls = tmp_path / "calls.jsonl"
    hypr_called = tmp_path / "hypr-called"
    environment = {
        "HOME": str(home),
        "PATH": f"{fake}:{copied}",
        "SCREENSHOT_CALLS": str(calls),
        "HYPR_CALLED": str(hypr_called),
        "PYTHONIOENCODING": "utf-8",
    }
    return home, copied, fake, calls, environment


def stub(rig, name, contents):
    _, _, fake, _, _ = rig
    path = fake / name
    path.write_text("#!/bin/sh\n" + contents)
    path.chmod(0o755)
    return path


def run_helper(rig, slot="1", *, extra=None, wrapper=False, check=False):
    home, copied, _, _, env = rig
    merged = {**env, **(extra or {})}
    target = copied / (f"screenshot_{slot}" if wrapper else "screenshot-output")
    command = [str(target)] if wrapper else [sys.executable, str(target), slot]
    result = subprocess.run(command, env=merged, text=True, capture_output=True, check=check)
    return result


def read_calls(rig):
    calls = rig[3]
    if not calls.exists():
        return []
    return calls.read_text().splitlines()


def install_capture(rig, name, *, fail=False):
    stub(rig, name, f'''\nif [ "${{CAPTURE_FAIL:-}}" = 1 ]; then exit 9; fi
printf '%s\\n' "$*" >> "$SCREENSHOT_CALLS"
for arg do target="$arg"; done
printf '\\211PNG\\r\\n\\032\\nsynthetic' > "$target"
''')


def install_hypr(rig, data, status=0):
    encoded = json.dumps(data)
    stub(rig, "hyprctl", f'''\nprintf 'called\\n' >> "$HYPR_CALLED"
printf '%s' '{encoded}'
exit {status}
''')


def test_wrappers_dispatch_slots_and_help_without_query_or_output(rig):
    install_hypr(rig, [{"name": "DP-1", "x": 0, "y": 0, "width": 900, "height": 700}])
    install_capture(rig, "grim")
    for slot in ("1", "2"):
        result = run_helper(rig, slot, extra={"XDG_SESSION_TYPE": "wayland"}, wrapper=True)
        assert result.returncode == 0, result.stderr
    assert [call for call in read_calls(rig)]
    before = read_calls(rig)
    help_result = subprocess.run(
        [sys.executable, str(rig[1] / "screenshot-output"), "--help"],
        env=rig[4], text=True, capture_output=True,
    )
    assert help_result.returncode == 0
    assert read_calls(rig) == before
    assert len(list((rig[0] / "screenshots").glob("*.png"))) == 2


@pytest.mark.parametrize("outputs,expected", [
    ([{"name": "B", "x": 1920, "y": 0, "width": 1024, "height": 768},
      {"name": "A", "x": -1600, "y": -200, "width": 1600, "height": 900}], ("A", "B")),
    ([{"name": "laptop", "x": 0, "y": 0, "width": 2256, "height": 1504}], ("laptop", "laptop")),
])
def test_wayland_selects_position_order_and_slot2_falls_back_to_single(rig, outputs, expected):
    install_hypr(rig, outputs)
    install_capture(rig, "grim")
    for slot in ("1", "2"):
        result = run_helper(rig, slot, extra={"XDG_SESSION_TYPE": "wayland"})
        assert result.returncode == 0, result.stderr
    calls = read_calls(rig)
    assert len(calls) == 2
    assert all(f"-o {name} " in " " + call + " " for name, call in zip(expected, calls))


def test_hyprland_fractional_scale_rotated_output_uses_grim_name(rig):
    install_hypr(rig, [{"name": "DP-1", "x": -2560, "y": 0, "width": 1440, "height": 2560,
                       "scale": 1.5, "transform": 1}])
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"WAYLAND_DISPLAY": "wayland-1"})
    assert result.returncode == 0, result.stderr
    call = read_calls(rig)[0]
    assert "-o DP-1" in call
    assert "-g" not in call


def test_wlr_randr_is_fallback_and_ignores_disabled_outputs(rig):
    wlr_data = [
        {"name": "off", "enabled": False},
        {"name": "live", "enabled": True, "position": {"x": 20, "y": -5},
         "modes": [{"width": 1200, "height": 800, "refresh": 59.97, "preferred": False, "current": True},
                   {"width": 800, "height": 600, "refresh": 60.0, "preferred": True, "current": False}],
         "scale": 1.5, "transform": "90"},
    ]
    stub(rig, "wlr-randr", f"printf '%s' '{json.dumps(wlr_data)}'\n")
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode == 0, result.stderr
    assert "-o live" in read_calls(rig)[0]
    assert not Path(rig[4]["HYPR_CALLED"]).exists()


def test_wayland_backend_preference_uses_desktop_and_hypr_presence(rig):
    install_hypr(rig, [{"name": "hypr", "x": 0, "y": 0, "width": 900, "height": 700}])
    wlr_data = [{"name": "wlroots", "enabled": True, "position": {"x": 0, "y": 0},
                 "modes": [{"width": 800, "height": 600, "refresh": 60.0,
                           "preferred": True, "current": True}]}]
    stub(rig, "wlr-randr", f"printf '%s' '{json.dumps(wlr_data)}'\n")
    install_capture(rig, "grim")

    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode == 0, result.stderr
    assert "-o wlroots" in read_calls(rig)[-1]
    assert not Path(rig[4]["HYPR_CALLED"]).exists()

    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "gnome:HyPrLaNd"})
    assert result.returncode == 0, result.stderr
    assert "-o hypr" in read_calls(rig)[-1]
    assert Path(rig[4]["HYPR_CALLED"]).exists()


@pytest.mark.parametrize("raw", [
    '[{"name":"out","enabled":true,"position":{"x":0,"y":0},"modes":[]}]',
    '[{"name":"out","enabled":true,"position":{"x":0,"y":0},"modes":[{"current":"yes","width":1,"height":1}]}]',
    '[{"name":"out","enabled":true,"position":{"x":0,"y":0},"modes":[{"current":false,"width":1,"height":1}]}]',
    '[{"name":"out","enabled":true,"position":{"x":0,"y":0},"modes":[{"current":true,"width":1,"height":1},{"current":true,"width":2,"height":2}]}]',
    '[{"name":"out","enabled":true,"position":{"x":0,"y":0},"modes":[null]}]',
])
def test_wlr_malformed_modes_fail_without_capture_or_directory(rig, raw):
    stub(rig, "wlr-randr", f"printf '%s' '{raw}'\n")
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


def test_invalid_utf8_metadata_is_reported_without_traceback(rig):
    stub(rig, "wlr-randr", "printf '\\377'\n")
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "non-text output" in result.stderr
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


def test_duplicate_hyprland_output_names_fail_as_ambiguous(rig):
    install_hypr(rig, [
        {"name": "same", "x": 0, "y": 0, "width": 900, "height": 700},
        {"name": "same", "x": 900, "y": 0, "width": 900, "height": 700},
    ])
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland", "XDG_CURRENT_DESKTOP": "Hyprland"})
    assert result.returncode != 0
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


def test_duplicate_wlr_output_names_fail_as_ambiguous(rig):
    mode = {"width": 900, "height": 700, "refresh": 59.97, "preferred": True, "current": True}
    outputs = [
        {"name": "same", "enabled": True, "position": {"x": 0, "y": 0}, "modes": [mode]},
        {"name": "same", "enabled": True, "position": {"x": 900, "y": 0}, "modes": [mode]},
    ]
    stub(rig, "wlr-randr", f"printf '%s' '{json.dumps(outputs)}'\n")
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


def test_xrandr_uses_connected_active_geometry_and_ignores_disconnected(rig):
    stub(rig, "xrandr", '''\nprintf '%s\\n' 'Screen 0: minimum 8 x 8, current 3000 x 1200, maximum 32767 x 32767' \\
  'DP-3 connected primary 2560x1440-2560+0 (normal left inverted right x axis y axis) 600mm x 340mm' \\
  'HDMI-1 connected (normal left inverted right x axis y axis) 500mm x 300mm' \\
  'DP-1 disconnected (normal left inverted right x axis y axis)'
''')
    install_capture(rig, "scrot")
    result = run_helper(rig)
    assert result.returncode == 0, result.stderr
    assert "-a -2560,0,2560,1440" in read_calls(rig)[0]


def test_explicit_output_and_geometry_precedence_and_paths_with_spaces(rig):
    install_hypr(rig, [{"name": "A&B", "x": 2, "y": 3, "width": 800, "height": 600}])
    install_capture(rig, "grim")
    destination = rig[0] / "out dir & more"
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland", "SCREENSHOT_DIR": str(destination),
                                    "SCREENSHOT_OUTPUT_1": "A&B"})
    assert result.returncode == 0, result.stderr
    assert "-o A&B" in read_calls(rig)[0]
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland", "SCREENSHOT_DIR": str(destination),
                                    "SCREENSHOT_GEOMETRY_1": "-12,+4 321x123"})
    assert result.returncode == 0, result.stderr
    assert "-g -12,4 321x123" in read_calls(rig)[-1]
    assert len(list(destination.glob("*.png"))) == 2
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in destination.glob("*.png"))


@pytest.mark.parametrize("extra", [
    {"SCREENSHOT_GEOMETRY_1": "bad"},
    {"SCREENSHOT_GEOMETRY_1": "0,0 0x2"},
    {"SCREENSHOT_OUTPUT_1": "missing"},
])
def test_invalid_selection_fails_without_capture_or_output_directory(rig, extra):
    install_hypr(rig, [{"name": "A", "x": 0, "y": 0, "width": 100, "height": 100}])
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland", **extra})
    assert result.returncode != 0
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


@pytest.mark.parametrize("raw", ["not json", "{}", "[]"])
def test_invalid_or_empty_wayland_metadata_fails_before_mkdir(rig, raw):
    stub(rig, "hyprctl", f"printf '%s' '{raw}'\n")
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert read_calls(rig) == []
    assert not (rig[0] / "screenshots").exists()


def test_query_and_capture_failures_leave_no_staging_artifacts(rig):
    install_hypr(rig, [], status=4)
    install_capture(rig, "grim")
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert not (rig[0] / "screenshots").exists()
    install_hypr(rig, [{"name": "A", "x": 0, "y": 0, "width": 10, "height": 10}])
    stub(rig, "grim", 'exit 9\n')
    result = run_helper(rig, extra={"XDG_SESSION_TYPE": "wayland"})
    assert result.returncode != 0
    assert list((rig[0] / "screenshots").iterdir()) == []


def test_concurrent_captures_publish_unique_private_files_and_clean_staging(rig):
    install_hypr(rig, [{"name": "A", "x": 0, "y": 0, "width": 10, "height": 10}])
    install_capture(rig, "grim")
    destination = rig[0] / "shots"
    extra = {"XDG_SESSION_TYPE": "wayland", "SCREENSHOT_DIR": str(destination)}
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: run_helper(rig, extra=extra), range(4)))
    assert all(result.returncode == 0 for result in results)
    images = list(destination.glob("*.png"))
    assert len(images) == 4
    assert len({image.name for image in images}) == 4
    assert all(image.stat().st_mode & 0o777 == 0o600 for image in images)
    assert not list(destination.glob(".screenshot-*"))


def test_wrapper_help_and_unexpected_arguments_are_safe(rig):
    result = subprocess.run([str(rig[1] / "screenshot_1"), "--help"], env=rig[4], text=True, capture_output=True)
    assert result.returncode == 0
    assert not (rig[0] / "screenshots").exists()
    result = subprocess.run([str(rig[1] / "screenshot_1"), "unexpected"], env=rig[4], text=True, capture_output=True)
    assert result.returncode != 0
    assert not (rig[0] / "screenshots").exists()

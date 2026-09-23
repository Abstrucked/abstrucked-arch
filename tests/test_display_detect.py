"""display-detect runs against fake hyprctl/xrandr in a disposable home."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/.local/bin/display-detect"

ULTRAWIDE = {"name": "DP-1", "width": 3440, "height": 1440, "refreshRate": 59.97,
             "availableModes": ["3440x1440@59.97Hz", "3440x1440@143.97Hz", "2560x1440@59.95Hz"]}
PANEL_27 = {"name": "HDMI-A-1", "width": 1920, "height": 1080, "refreshRate": 60.0,
            "availableModes": ["1920x1080@60.00Hz", "1920x1080@74.97Hz"]}
LAPTOP = {"name": "eDP-1", "width": 1920, "height": 1080, "refreshRate": 60.01,
          "availableModes": ["1920x1080@60.01Hz"]}

XRANDR_DESKTOP = """\
Screen 0: minimum 320 x 200, current 5360 x 1440, maximum 16384 x 16384
DisplayPort-0 connected 3440x1440+0+0 (normal left inverted right x axis y axis) 800mm x 335mm
   3440x1440     59.97 + 143.97*  99.98
   2560x1440     59.95
HDMI-A-0 connected (normal left inverted right x axis y axis) 600mm x 340mm
   1920x1080     60.00 +  74.97    50.00
   1280x720      60.00
DisplayPort-1 disconnected (normal left inverted right x axis y axis)
"""


class DisplayDetectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="display-detect-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "home"
        self.bg = self.root / "backgrounds"
        self.log = self.root / "calls.log"
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        # Both fakes log every call; `monitors -j` / `--query|--current` print
        # the scenario loaded from a file.
        (bin_dir / "hyprctl").write_text(
            '#!/bin/sh\necho "hyprctl $*" >>"$FAKE_LOG"\n'
            '[ "$1" = monitors ] && cat "$FAKE_MONITORS"\nexit 0\n')
        (bin_dir / "xrandr").write_text(
            '#!/bin/sh\necho "xrandr $*" >>"$FAKE_LOG"\n'
            'case "$1" in --query|--current) cat "$FAKE_XRANDR" ;; esac\nexit 0\n')
        for fake in bin_dir.iterdir():
            fake.chmod(0o755)
        self.monitors = self.root / "monitors.json"
        self.xrandr = self.root / "xrandr.txt"
        self.env = dict(os.environ, HOME=str(self.home), XDG_STATE_HOME=str(self.home / ".local/state"),
                        XDG_CONFIG_HOME=str(self.home / ".config"), THEME_BG_DIR=str(self.bg),
                        FAKE_LOG=str(self.log), FAKE_MONITORS=str(self.monitors),
                        FAKE_XRANDR=str(self.xrandr), PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
        for key in ("HYPRLAND_INSTANCE_SIGNATURE", "DISPLAY", "WALLPAPER_SET", "DISPLAY_DETECT_BACKEND"):
            self.env.pop(key, None)
        self.make_set("default", "ultrawide-3440x1440.png", "wide-1920x1080.png")

    def make_set(self, name, *files):
        directory = self.bg / "sets" / name
        directory.mkdir(parents=True, exist_ok=True)
        for file in files:
            (directory / file).write_bytes(b"png")
        return directory

    def hypr(self, *monitors):
        self.monitors.write_text(json.dumps(list(monitors)))
        self.env["HYPRLAND_INSTANCE_SIGNATURE"] = "test"

    def run_tool(self, *args):
        result = subprocess.run([str(SCRIPT), *args], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def calls(self, prefix):
        if not self.log.exists():
            return []
        return [line for line in self.log.read_text().splitlines() if line.startswith(prefix)]

    def paths(self):
        return dict(line.split("\t") for line in self.run_tool("paths").splitlines())

    def test_desktop_hyprland_layout(self):
        self.hypr(PANEL_27, ULTRAWIDE)
        self.run_tool("layout")
        evals = self.calls("hyprctl eval")
        self.assertEqual(len(evals), 2)
        self.assertIn('output = "DP-1", mode = "3440x1440@143.97", position = "0x0"', evals[0])
        self.assertIn('output = "HDMI-A-1", mode = "1920x1080@74.97", position = "3440x0"', evals[1])
        lock = (self.home / ".config/hypr/lock-backgrounds.conf").read_text()
        self.assertIn("monitor = DP-1", lock)
        self.assertIn(str(self.bg / "sets/default/ultrawide-3440x1440.png"), lock)

    def test_desktop_hyprland_wallpaper(self):
        self.hypr(ULTRAWIDE, PANEL_27)
        self.run_tool("wallpaper")
        self.assertEqual(self.calls("hyprctl hyprpaper"), [
            f"hyprctl hyprpaper wallpaper DP-1,{self.bg}/sets/default/ultrawide-3440x1440.png",
            f"hyprctl hyprpaper wallpaper HDMI-A-1,{self.bg}/sets/default/wide-1920x1080.png",
        ])

    def test_laptop_alone(self):
        self.hypr(LAPTOP)
        self.run_tool("apply")
        self.assertIn('output = "eDP-1", mode = "1920x1080@60.01", position = "0x0"',
                      self.calls("hyprctl eval")[0])
        # The built-in panel has no images of its own and borrows the 16:9 ones.
        self.assertEqual(self.paths(), {"eDP-1": str(self.bg / "sets/default/wide-1920x1080.png")})

    def test_docked_laptop_sits_under_the_external(self):
        self.hypr(LAPTOP, ULTRAWIDE)
        self.run_tool("layout")
        evals = self.calls("hyprctl eval")
        self.assertIn('"DP-1", mode = "3440x1440@143.97", position = "0x0"', evals[0])
        self.assertIn('"eDP-1", mode = "1920x1080@60.01", position = "760x1440"', evals[1])

    def test_desktop_x11_layout(self):
        self.xrandr.write_text(XRANDR_DESKTOP)
        self.env["DISPLAY"] = ":0"
        self.run_tool("layout")
        applied = [c for c in self.calls("xrandr") if "--output" in c]
        self.assertEqual(applied, [
            "xrandr --output DisplayPort-0 --mode 3440x1440 --rate 143.97 --pos 0x0 --primary"
            " --output HDMI-A-0 --mode 1920x1080 --rate 74.97 --pos 3440x0"
            " --output DisplayPort-1 --off"])
        self.assertEqual(self.paths(), {
            "DisplayPort-0": str(self.bg / "sets/default/ultrawide-3440x1440.png"),
            "HDMI-A-0": str(self.bg / "sets/default/wide-1920x1080.png"),
        })

    def test_wallpaper_set_follows_theme_then_saved_choice(self):
        self.hypr(ULTRAWIDE, PANEL_27)
        # A theme's set only needs the images it has; the rest come from default.
        themed = self.make_set("nord", "ultrawide.png")
        (self.home / ".local/state/themes").mkdir(parents=True)
        (self.home / ".local/state/themes/current").write_text("nord\n")
        self.assertEqual(self.paths(), {
            "DP-1": str(themed / "ultrawide.png"),
            "HDMI-A-1": str(self.bg / "sets/default/wide-1920x1080.png"),
        })
        chosen = self.make_set("space", "wide.jpg")
        self.run_tool("set", "space")
        self.assertEqual(self.run_tool("set").strip(), "space")
        self.assertEqual(self.paths()["HDMI-A-1"], str(chosen / "wide.jpg"))
        self.env["WALLPAPER_SET"] = "nord"
        self.assertEqual(self.paths()["DP-1"], str(themed / "ultrawide.png"))

    def test_unknown_set_is_refused(self):
        result = subprocess.run([str(SCRIPT), "set", "nope"], env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("no wallpaper set 'nope'", result.stderr)


if __name__ == "__main__":
    unittest.main()

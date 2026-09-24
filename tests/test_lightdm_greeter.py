"""themectl-greeter-sync runs against a relocated root and a staged theme.

The real script runs as root at greeter start; here it runs as the test user,
which it reads the stage as directly instead of through setpriv.
"""
import getpass
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "install/lightdm/themectl-greeter-sync"
HOOK = ROOT / "themes/hooks/lightdm.sh"
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 32
CSS = ('@import url("resource:///org/gtk/libgtk/theme/Adwaita/gtk-contained-dark.css");\n'
       "#login_window { background-color: #1e1e2e; }\n")


class GreeterSyncTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="greeter-sync-test-")
        self.addCleanup(temp.cleanup)
        self.tmp = Path(temp.name)
        self.root = self.tmp / "root"
        self.stage = self.tmp / "stage"
        self.stage.mkdir()
        conf = self.root / "etc/lightdm/themectl-greeter.conf"
        conf.parent.mkdir(parents=True)
        conf.write_text(f"user={getpass.getuser()}\nstage={self.stage}\n")
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        # xrandr reports the desktop; logger is silenced so failures are visible
        # on stderr for the assertions instead of going to the journal.
        (bin_dir / "xrandr").write_text(
            "#!/bin/sh\ncat <<'X'\n"
            "DisplayPort-0 connected primary 3440x1440+0+0 (normal) 800mm x 335mm\n"
            "HDMI-A-0 connected 1920x1080+3440+0 (normal) 600mm x 340mm\n"
            "eDP disconnected (normal)\nX\n")
        (bin_dir / "logger").write_text("#!/bin/sh\nexit 1\n")
        for fake in bin_dir.iterdir():
            fake.chmod(0o755)
        self.env = dict(os.environ, THEMECTL_GREETER_ROOT=str(self.root), DISPLAY=":99",
                        PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

    def stage_theme(self, css=CSS, bg="#1e1e2e\n", **wallpapers):
        (self.stage / "gtk.css").write_text(css)
        (self.stage / "bg").write_text(bg)
        for name, data in wallpapers.items():
            (self.stage / name).write_bytes(data)

    def sync(self):
        result = subprocess.run([str(SYNC)], env=self.env, text=True, capture_output=True, timeout=20)
        # A failing greeter-setup-script would stop the login screen.
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stderr

    def out(self, path):
        return self.root / path

    def greeter_conf(self):
        return self.out("etc/xdg/lightdm/lightdm-gtk-greeter.conf.d/60-themectl.conf").read_text()

    def test_publishes_theme_and_per_monitor_wallpapers(self):
        self.stage_theme(ultrawide=PNG, wide=JPEG)
        self.sync()
        self.assertEqual(self.out("usr/share/themes/themectl-greeter/gtk-3.0/gtk.css").read_text(), CSS)
        self.assertTrue(self.out("usr/share/themes/themectl-greeter/index.theme").exists())
        bgs = self.out("usr/share/backgrounds/themectl")
        self.assertEqual(sorted(p.name for p in bgs.iterdir()), ["ultrawide.png", "wide.jpg"])
        conf = self.greeter_conf()
        self.assertIn(f"[greeter]\nbackground={bgs}/wide.jpg\n", conf)
        self.assertIn(f"[monitor: DisplayPort-0]\nbackground={bgs}/ultrawide.png\n", conf)
        self.assertIn(f"[monitor: HDMI-A-0]\nbackground={bgs}/wide.jpg\n", conf)
        self.assertNotIn("eDP", conf)
        for path in (bgs / "wide.jpg", self.out("usr/share/themes/themectl-greeter/gtk-3.0/gtk.css")):
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_without_wallpapers_falls_back_to_the_theme_color(self):
        self.stage_theme()
        self.sync()
        self.assertIn("[greeter]\nbackground=#1e1e2e\n", self.greeter_conf())

    def test_css_loading_files_keeps_the_previous_theme(self):
        self.stage_theme()
        self.sync()
        for bad in ('#login_window { background-image: url("file:///etc/shadow"); }\n',
                    '@import url("/tmp/evil.css");\n',
                    "#x { background-image: -gtk-scaled(url('a.png')); }\n"):
            with self.subTest(bad=bad):
                self.stage_theme(css=CSS + bad)
                self.assertIn("loads external resources", self.sync())
                self.assertEqual(self.out("usr/share/themes/themectl-greeter/gtk-3.0/gtk.css").read_text(), CSS)

    def test_untrusted_values_never_reach_the_greeter_config(self):
        self.stage_theme(bg="#123456\nkeyboard=xterm\n", wide=b"keyboard=xterm\n")
        self.assertIn("not a PNG or JPEG", self.sync())
        conf = self.greeter_conf()
        self.assertNotIn("keyboard", conf)
        self.assertIn("background=#123456\n", conf)
        self.stage_theme(bg="[greeter]\n")
        self.sync()
        self.assertNotIn("background=", self.greeter_conf().split("[monitor:")[0])

    def test_oversized_files_are_refused(self):
        self.stage_theme(css=CSS + "/*" + "x" * (256 * 1024) + "*/\n")
        self.assertIn("gtk.css is over", self.sync())
        self.assertFalse(self.out("usr/share/themes/themectl-greeter").exists())

    def test_missing_config_or_stage_still_lets_the_greeter_start(self):
        self.sync()  # empty stage
        self.out("etc/lightdm/themectl-greeter.conf").unlink()
        self.sync()

    def test_hook_stages_color_and_wallpapers(self):
        home = self.tmp / "home"
        themes = self.tmp / "dotfiles/themes"
        themes.mkdir(parents=True)
        picker = self.tmp / "dotfiles/scripts/.local/bin/display-detect"
        picker.parent.mkdir(parents=True)
        wallpaper = self.tmp / "wall.png"
        picker.write_text(f'#!/bin/sh\n[ "$2" = ultrawide ] && exit 0\necho {wallpaper}\n')
        picker.chmod(0o755)
        env = dict(os.environ, HOME=str(home), THEME_DIR=str(themes), THEME_BG="#abcdef")
        subprocess.run([str(HOOK)], env=env, check=True, timeout=10)
        stage = home / ".local/state/themes/greeter"
        self.assertEqual((stage / "bg").read_text(), "#abcdef\n")
        self.assertEqual(os.readlink(stage / "wide"), str(wallpaper))
        self.assertEqual(os.readlink(stage / "internal"), str(wallpaper))
        self.assertFalse((stage / "ultrawide").exists())


if __name__ == "__main__":
    unittest.main()

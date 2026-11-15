"""zen.yazi is tracked while the plugins `ya pkg` installs stay ignored."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PLUGINS = "yazi/.config/yazi/plugins"
MAIN = ROOT / PLUGINS / "zen.yazi/main.lua"


def ignored(path):
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT, check=False,
    )
    return result.returncode == 0


class YaziZenTests(unittest.TestCase):
    def test_plugin_exists(self):
        self.assertTrue(MAIN.is_file())

    def test_plugin_is_toggled_without_setup(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertIn("entry", source)
        self.assertNotIn("setup", source.replace("no setup call", ""))

    def test_zen_is_tracked(self):
        self.assertFalse(ignored(f"{PLUGINS}/zen.yazi/main.lua"))
        self.assertFalse(ignored(f"{PLUGINS}/zen.yazi/README.md"))

    def test_installed_plugins_stay_ignored(self):
        for name in ("git", "full-border", "toggle-pane", "other"):
            with self.subTest(name=name):
                self.assertTrue(ignored(f"{PLUGINS}/{name}.yazi/main.lua"))

    def test_lua_parses(self):
        if shutil.which("luac") is None:
            self.skipTest("luac is not installed")
        subprocess.run(["luac", "-p", str(MAIN)], check=True)


if __name__ == "__main__":
    unittest.main()

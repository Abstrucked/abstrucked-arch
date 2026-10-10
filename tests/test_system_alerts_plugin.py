"""The system-alerts plugin validates, generates fragments and has theme styling."""
from pathlib import Path
import shutil
import unittest

from test_plugins import PluginTests


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/system-alerts"


class SystemAlertsPluginTests(unittest.TestCase):
    def setUp(self):
        # Reuse the sandboxed pluginctl harness without inheriting its tests.
        self.harness = PluginTests("run_tool")
        self.harness.setUp()
        self.addCleanup(self.harness.doCleanups)
        shutil.copytree(PLUGIN, self.harness.plugins / "system-alerts")

    def test_enable_generates_both_fragments(self):
        h = self.harness
        h.run_tool("enable", "system-alerts")
        awesome = (h.home / ".config/awesome/plugins.lua").read_text()
        hypr = (h.home / ".config/hypr/lua/plugins.lua").read_text()
        self.assertIn("-- plugin: system-alerts", awesome)
        self.assertEqual(awesome.count('"--watch-alerts"'), 1)
        self.assertIn('awful.spawn({ "os-assistant", "--watch-alerts" }, false)', awesome)
        self.assertIn('hl.exec_cmd("os-assistant --watch-alerts")', hypr)
        self.assertIn('hl.on("hyprland.start"', hypr)

    def test_awesome_spawn_is_inside_once(self):
        text = (PLUGIN / "awesome.lua").read_text()
        self.assertTrue(text.lstrip().startswith("-- ") and "= once(function()" in text)
        self.assertLess(text.index("once(function()"), text.index("awful.spawn"))

    def test_naughty_mapping_for_every_theme_that_defines_it(self):
        themes = [p for p in (ROOT / "awesome/.config/awesome/themes").glob("*/theme.lua")
                  if "naughty.dbus" in p.read_text()]
        self.assertTrue(themes)
        for theme in themes:
            text = theme.read_text()
            for urgency in ("\\2", "\\1", "\\0"):
                self.assertIn(f'appname = "os-assistant", urgency = "{urgency}"', text, theme)
            self.assertIn("c.red, c.bg, 0)", text, theme)
            self.assertIn("c.yellow, c.bg, 15)", text, theme)
            self.assertIn(", 8)", text, theme)


if __name__ == "__main__":
    unittest.main()

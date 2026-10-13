"""Regression tests for Hyprland session startup and idle dispatch syntax."""

from pathlib import Path
import shlex
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
HYPRIDLE = ROOT / "hyprland/.config/hypr/hypridle.conf"
SESSION_START = ROOT / "hyprland/.local/bin/hypr-session-start"


class HyprSessionTests(unittest.TestCase):
    def test_hypridle_dispatch_commands_are_valid_lua(self):
        config = HYPRIDLE.read_text()
        commands = []
        for line in config.splitlines():
            if "hyprctl dispatch" not in line:
                continue
            invocation = line.split("=", 1)[1].strip()
            argv = shlex.split(invocation)
            self.assertGreaterEqual(len(argv), 3, line)
            self.assertEqual(argv[:2], ["hyprctl", "dispatch"], line)
            commands.append(argv[2])

        self.assertEqual(len(commands), 3)
        self.assertNotRegex(config, r"\bdpms\s+(?:on|off)\b")
        luac = shutil.which("luac")
        lua = shutil.which("lua")
        self.assertTrue(luac or lua, "luac or lua is required for Lua syntax validation")
        for argument in commands:
            source = f"return hl.dispatch({argument})"
            with self.subTest(source=source):
                if luac:
                    subprocess.run([luac, "-p", "-"], input=source, text=True, check=True)
                else:
                    subprocess.run(
                        [lua, "-e", f"assert(load({source!r}))"],
                        text=True,
                        check=True,
                    )

    def test_dex_uses_default_user_first_search_order(self):
        script = SESSION_START.read_text()
        self.assertIn("dex --environment Hyprland --autostart || true", script)
        self.assertNotIn("--search-paths", script)
        self.assertIn("dex's default user-first XDG search order", script)

    def test_dex_remains_guarded_and_non_fatal(self):
        script = SESSION_START.read_text()
        self.assertIn("if command -v dex >/dev/null 2>&1; then", script)
        self.assertRegex(script, r"dex --environment Hyprland --autostart\s+\|\| true")


if __name__ == "__main__":
    unittest.main()

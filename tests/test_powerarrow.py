"""Powerarrow bar-spacing regression checks (fully mocked Awesome)."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "awesome/.config/awesome/themes/powerarrow/theme.lua"
TEST = ROOT / "tests/test_powerarrow.lua"


class PowerarrowTests(unittest.TestCase):
    def test_bar_spacing_and_composition(self):
        # The Lua test mocks every Awesome module, so the real
        # theme file runs without touching a desktop.
        result = subprocess.run(
            ["lua", str(TEST), str(THEME)],
            capture_output=True,
            text=True,
            timeout=60,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("powerarrow spacing tests passed", result.stdout)


if __name__ == "__main__":
    unittest.main()

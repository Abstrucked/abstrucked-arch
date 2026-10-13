from pathlib import Path
import re
import unittest


PLUGIN = Path(__file__).resolve().parents[1] / "nvim/.config/nvim/lua/plugins/mpchub.lua"
SOURCE = PLUGIN.read_text()


class McpHubPluginSpecTests(unittest.TestCase):
    def test_auto_approval_is_explicit_opt_in(self):
        self.assertNotRegex(SOURCE, r"auto_approve\s*=\s*true\b")
        self.assertRegex(SOURCE, r"(?im)^\s*--.*upstream defaults auto_approve to false")
        self.assertIn("MCPHUB_AUTO_APPROVE", SOURCE)

    def test_build_does_not_use_latest(self):
        build = re.search(r"(?m)^\s*build\s*=\s*([\"'])(.*?)\1", SOURCE)
        self.assertIsNotNone(build)
        self.assertNotIn("@latest", build.group(2))
        self.assertIn("mcp-hub@4.2.1", build.group(2))

    def test_plugin_is_lazy_loaded_by_registered_command(self):
        self.assertRegex(SOURCE, r"(?m)^\s*lazy\s*=\s*true\s*,")
        self.assertRegex(SOURCE, r'(?m)^\s*cmd\s*=\s*\{\s*"MCPHub"\s*\}')


if __name__ == "__main__":
    unittest.main()

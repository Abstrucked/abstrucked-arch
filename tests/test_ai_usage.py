"""Exercise ai-usage-text's local icon path without contacting usage APIs."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/ai-usagebar/bin/ai-usage-text"
ICON = REPO / "plugins/ai-usagebar/icons/copilot.svg"
REAL_TOOLS = ("jq", "mktemp", "sed", "cmp", "readlink", "dirname", "mkdir", "mv", "rm")


class AiUsageIconTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugin"
        (self.plugin / "bin").mkdir(parents=True)
        (self.plugin / "icons").mkdir()
        shutil.copy2(SCRIPT, self.plugin / "bin/ai-usage-text")
        shutil.copy2(ICON, self.plugin / "icons/copilot.svg")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in REAL_TOOLS:
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.calls = self.root / "settings-calls"
        self.command("ai-usagebar", 'printf "called\\n" >> "$SETTINGS_CALLS"\nprintf \'{"primary":"copilot"}\\n\'')
        self.cache = self.root / "cache"
        self.env = {"HOME": str(self.root), "XDG_CACHE_HOME": str(self.cache),
                    "SETTINGS_CALLS": str(self.calls), "PATH": str(self.bin), "LC_ALL": "C"}

    def command(self, name, body):
        path = self.bin / name
        path.unlink(missing_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_icon(self, color, *extra):
        return subprocess.run([str(self.plugin / "bin/ai-usage-text"), "--icon", color, *extra],
                              text=True, capture_output=True, env=self.env, timeout=10)

    def test_valid_color_recolors_fill_and_stroke_and_reuses_cache(self):
        color = "#aB12fF"
        output = self.run_icon(color)
        expected_path = self.cache / "ai-usagebar/copilot-aB12fF.svg"
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(output.stdout, f"{expected_path}\n")
        expected = ICON.read_text().replace('fill="black"', f'fill="{color}"').replace(
            'stroke="black"', f'stroke="{color}"')
        self.assertEqual(expected_path.read_text(), expected)
        calls_after_first = self.calls.read_text()
        original_inode = expected_path.stat().st_ino

        output = self.run_icon(color)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertEqual(self.calls.read_text(), calls_after_first + "called\n")
        self.assertEqual(expected_path.stat().st_ino, original_inode)
        self.assertEqual(list(expected_path.parent.glob(".tmp.*")), [])

    def test_nonempty_truncated_cache_is_repaired(self):
        color = "#abcdef"
        expected_path = self.cache / "ai-usagebar/copilot-abcdef.svg"
        expected_path.parent.mkdir(parents=True)
        expected_path.write_text("<svg truncated")
        result = self.run_icon(color)
        expected = ICON.read_text().replace('fill="black"', f'fill="{color}"').replace(
            'stroke="black"', f'stroke="{color}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(expected_path.read_text(), expected)
        self.assertEqual(result.stdout, f"{expected_path}\n")

    def test_source_icon_changes_are_reflected_in_existing_cache(self):
        color = "#abcdef"
        expected_path = self.cache / "ai-usagebar/copilot-abcdef.svg"
        first = self.run_icon(color)
        self.assertEqual(first.returncode, 0, first.stderr)
        with (self.plugin / "icons/copilot.svg").open("a") as icon:
            icon.write("<!-- source changed -->\n")
        second = self.run_icon(color)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(expected_path.read_text(), (self.plugin / "icons/copilot.svg").read_text().replace(
            'fill="black"', f'fill="{color}"').replace('stroke="black"', f'stroke="{color}"'))

    def test_failed_candidate_render_preserves_existing_cache(self):
        color = "#abcdef"
        expected_path = self.cache / "ai-usagebar/copilot-abcdef.svg"
        first = self.run_icon(color)
        self.assertEqual(first.returncode, 0, first.stderr)
        original = expected_path.read_bytes()
        self.command("sed", "exit 1")
        failed = self.run_icon(color)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(failed.stdout, "")
        self.assertEqual(expected_path.read_bytes(), original)
        self.assertEqual(list(expected_path.parent.glob(".tmp.*")), [])

    def test_invalid_colors_fail_before_settings_or_cache_access(self):
        invalid = ["", "#12345", "#1234567", "#12g456", "#12;456", "#12/456",
                   "#12&456", "#12'456", "#12\"456", "../abcdef", "#abcdef/../../x"]
        for color in invalid:
            with self.subTest(color=color):
                result = self.run_icon(color)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage: ai-usage-text --icon '#rrggbb'", result.stderr)
                self.assertFalse(self.calls.exists())
                self.assertFalse(self.cache.exists())
        missing = subprocess.run([str(self.plugin / "bin/ai-usage-text"), "--icon"],
                                  text=True, capture_output=True, env=self.env, timeout=10)
        self.assertEqual(missing.returncode, 2)
        self.assertFalse(self.calls.exists())
        self.assertFalse(self.cache.exists())

    def test_concurrent_runs_publish_complete_output_without_temp_files(self):
        color = "#123abc"
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: self.run_icon(color), range(6)))
        expected_path = self.cache / "ai-usagebar/copilot-123abc.svg"
        expected = ICON.read_text().replace('fill="black"', f'fill="{color}"').replace(
            'stroke="black"', f'stroke="{color}"')
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, f"{expected_path}\n")
        self.assertEqual(expected_path.read_text(), expected)
        self.assertEqual(list(expected_path.parent.glob(".tmp.*")), [])

    def test_sed_and_move_failures_leave_no_published_partial_icon(self):
        for failing_tool in ("sed", "mv"):
            with self.subTest(tool=failing_tool):
                # Restore a clean per-case environment and install a failing wrapper.
                shutil.rmtree(self.cache, ignore_errors=True)
                self.calls.unlink(missing_ok=True)
                self.command(failing_tool, "exit 1")
                result = self.run_icon("#abcdef")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.cache / "ai-usagebar/copilot-abcdef.svg").exists())
                self.assertEqual(list((self.cache / "ai-usagebar").glob(".tmp.*")), [])
                self.command(failing_tool, f'exec "{shutil.which(failing_tool)}" "$@"')

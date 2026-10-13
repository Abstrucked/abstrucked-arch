"""Exercise the TUI launcher without a real terminal, key store, or Waybar."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "plugins/ai-usagebar/bin/ai-usage-tui"
DEFS = REPO / "plugins/ai-usagebar/waybar-defs.jsonc"
REAL_TOOLS = ("readlink", "dirname")


class AiUsageTuiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.plugin = self.root / "plugin"
        (self.plugin / "bin").mkdir(parents=True)
        (self.plugin / "lib").mkdir()
        shutil.copy2(SCRIPT, self.plugin / "bin/ai-usage-tui")
        # A local helper fixture avoids pass, GPG, tty, and settings/API access.
        (self.plugin / "lib/openrouter-key.sh").write_text(
            "ai_usage_load_openrouter_key() {\n"
            '    [ "${KEY_RESULT:-0}" -eq 0 ]\n'
            "}\n"
        )
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in REAL_TOOLS:
            executable = shutil.which(name)
            if executable:
                (self.bin / name).symlink_to(executable)
        self.log = self.root / "calls"
        self.env = {
            "HOME": str(self.root / "home"),
            "PATH": str(self.bin),
            "CALL_LOG": str(self.log),
            "LC_ALL": "C",
        }
        (self.root / "home").mkdir()
        self.command(
            "ai-usagebar-tui",
            'printf "dashboard" >> "$CALL_LOG"\n'
            'for arg do printf "|%s" "$arg" >> "$CALL_LOG"; done\n'
            'printf "\\n" >> "$CALL_LOG"',
        )
        self.command(
            "pkill",
            'printf "pkill" >> "$CALL_LOG"\n'
            'for arg do printf "|%s" "$arg" >> "$CALL_LOG"; done\n'
            'printf "\\n" >> "$CALL_LOG"\n'
            'exit "${PKILL_STATUS:-0}"',
        )
        self.command("id", 'printf "%s\\n" "${FAKE_UID:-4242}"')

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def terminal(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            'printf "terminal" >> "$CALL_LOG"\n'
            'for arg do printf "|%s" "$arg" >> "$CALL_LOG"; done\n'
            'printf "\\n" >> "$CALL_LOG"\n'
            '[ "$1" = -e ] || exit 98\n'
            "shift\n"
            'exec "$@"\n'
        )
        path.chmod(0o755)
        return path

    def run_tui(self, *args, env=None):
        return subprocess.run(
            [str(self.plugin / "bin/ai-usage-tui"), *args],
            text=True,
            capture_output=True,
            env={**self.env, **(env or {})},
            timeout=10,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_default_alacritty_launch_and_forwards_arguments_unchanged(self):
        self.terminal(self.bin / "alacritty")
        result = self.run_tui("--provider", "name with spaces")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertEqual(
            calls,
            [
                "terminal|-e|%s|--in-terminal|--provider|name with spaces"
                % (self.plugin / "bin/ai-usage-tui"),
                "pkill|-u|4242|-RTMIN+13|-x|waybar",
                "dashboard|--provider|name with spaces",
            ],
        )

    def test_custom_terminal_and_path_with_spaces_are_single_executable(self):
        terminal = self.terminal(self.root / "terminal tools" / "custom terminal")
        result = self.run_tui("--model", "model name", env={"TERMINAL": str(terminal)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls()[0],
            "terminal|-e|%s|--in-terminal|--model|model name"
            % (self.plugin / "bin/ai-usage-tui"),
        )
        self.assertEqual(self.calls()[1], "pkill|-u|4242|-RTMIN+13|-x|waybar")
        self.assertEqual(self.calls()[2], "dashboard|--model|model name")

    def test_in_terminal_does_not_spawn_a_terminal_and_refresh_is_uid_scoped(self):
        result = self.run_tui("--in-terminal", "arg with spaces", env={"OPENROUTER_API_KEY": "fixture-key"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [
                "pkill|-u|4242|-RTMIN+13|-x|waybar",
                "dashboard|arg with spaces",
            ],
        )

    def test_failed_refresh_is_best_effort_and_dashboard_still_opens(self):
        result = self.run_tui(
            "--in-terminal", env={"OPENROUTER_API_KEY": "fixture-key", "PKILL_STATUS": "1"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1], "dashboard")

    def test_unavailable_key_warns_but_dashboard_for_other_providers_opens(self):
        result = self.run_tui("--in-terminal", env={"KEY_RESULT": "1"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("OpenRouter key unavailable", result.stderr)
        self.assertEqual(self.calls(), ["dashboard"])

    def test_missing_custom_terminal_fails_without_fallback_or_dashboard(self):
        missing = self.root / "missing terminal"
        result = self.run_tui("--provider", "x", env={"TERMINAL": str(missing)})
        self.assertEqual(result.returncode, 127)
        self.assertEqual(self.calls(), [])

    def test_waybar_refresh_signal_matches_both_configured_modules(self):
        definitions = DEFS.read_text()
        self.assertEqual(definitions.count('"signal": 13'), 2)
        script = SCRIPT.read_text()
        self.assertIn("Signal 13 is configured", script)
        self.assertIn("waybar-defs.jsonc", script)


if __name__ == "__main__":
    unittest.main()

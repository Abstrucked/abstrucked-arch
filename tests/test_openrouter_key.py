"""OpenRouter pass-wrapper tests use synthetic keys and isolated commands only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenRouterKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="openrouter-key-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.helper = self.root / "openrouter-key.sh"
        shutil.copy2(ROOT / "plugins/ai-usagebar/lib/openrouter-key.sh", self.helper)
        self.shell = shutil.which("sh")
        jq = shutil.which("jq")
        self.assertIsNotNone(self.shell)
        self.assertIsNotNone(jq)
        (self.bin / "jq").symlink_to(jq)
        self.log = self.root / "pass-options"
        self.env = {
            "HOME": str(self.root), "PATH": str(self.bin), "HELPER": str(self.helper),
            "CALL_LOG": str(self.log), "PASS_STATUS": "0", "PASS_KEY": "synthetic-fixture-key",
        }
        self.script("ai-usagebar", 'printf \'%s\\n\' \'{"keys":[]}\'')
        self.script("pass", 'printf \'%s\\n\' "$PASSWORD_STORE_GPG_OPTS" >"$CALL_LOG"\n'
                    'printf \'%s\\n\' "$PASS_KEY"\nexit "$PASS_STATUS"')
        self.script("tty", 'printf \'%s\\n\' /dev/fixture-tty')
        self.store = self.root / ".password-store/ai"
        self.store.mkdir(parents=True)
        (self.store / "openrouter_api_key.gpg").write_text("synthetic fixture, not encrypted data\n")

    def script(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{self.shell}\n" + body + "\n")
        path.chmod(0o755)

    def run_helper(self, mode="background", status=0):
        result = subprocess.run(
            [self.shell, "-c", '. "$HELPER"\n'
             'ai_usage_load_openrouter_key "$1"\nstatus=$?\n'
             'printf "key=%s\\ntty=%s\\n" "${OPENROUTER_API_KEY:-}" "${GPG_TTY:-}"\n'
             'exit "$status"', "test", mode],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=5,
        )
        self.assertEqual(result.returncode, status, result.stderr)
        return result

    def test_invalid_mode_is_distinct_even_with_configured_key(self):
        self.run_helper("invalid", status=64)
        self.assertFalse(self.log.exists())
        self.env["OPENROUTER_API_KEY"] = "configured-fixture-key"
        self.run_helper("invalid", status=64)
        self.assertFalse(self.log.exists())

    def test_missing_and_locked_keys_have_distinct_statuses(self):
        (self.store / "openrouter_api_key.gpg").unlink()
        self.run_helper(status=2)
        self.assertFalse(self.log.exists())
        (self.store / "openrouter_api_key.gpg").touch()
        self.env["PASS_STATUS"] = "1"
        result = self.run_helper(status=1)
        self.assertIn("key=\n", result.stdout)
        self.assertNotIn("synthetic-fixture-key", result.stdout + result.stderr)

    def test_background_pinentry_modes_are_normalized_without_changing_parent(self):
        cases = (
            "--quiet --pinentry-mode loopback --armor",
            "--pinentry-mode=ask --quiet --pinentry-mode error",
            "--quiet --pinentry-mode --armor",
            "",
        )
        for options in cases:
            with self.subTest(options=options):
                self.env["PASSWORD_STORE_GPG_OPTS"] = options
                result = self.run_helper()
                effective = self.log.read_text().strip().split()
                self.assertEqual(effective.count("--pinentry-mode"), 1)
                self.assertFalse(any(item.startswith("--pinentry-mode=") for item in effective))
                self.assertEqual(effective[-2:], ["--pinentry-mode", "error"])
                self.assertIn("key=synthetic-fixture-key", result.stdout)
                self.assertEqual(self.env["PASSWORD_STORE_GPG_OPTS"], options)
                if "--armor" in options:
                    self.assertIn("--armor", effective)

    def test_interactive_mode_uses_ask_and_its_terminal(self):
        self.env["PASSWORD_STORE_GPG_OPTS"] = "--quiet --pinentry-mode=error"
        result = self.run_helper("interactive")
        self.assertEqual(self.log.read_text().strip(), "--quiet --pinentry-mode ask")
        self.assertIn("tty=/dev/fixture-tty", result.stdout)

    def test_environment_key_does_not_access_pass(self):
        self.env["OPENROUTER_API_KEY"] = "configured-fixture-key"
        self.run_helper()
        self.assertFalse(self.log.exists())

    def test_options_are_never_evaluated_or_glob_expanded(self):
        marker = self.root / "must-not-exist"
        (self.root / "matched-file").touch()
        self.env["PASSWORD_STORE_GPG_OPTS"] = f"--comment $(touch {marker}) * --pinentry-mode loopback"
        self.run_helper()
        options = self.log.read_text()
        self.assertIn("$(touch", options)
        self.assertIn(" * ", options)
        self.assertNotIn("matched-file", options)
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()

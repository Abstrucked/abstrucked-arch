"""Hermetic regression tests for copied Tailscale helpers and command stubs."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPTS = ROOT / "plugins/tailscale/bin"
JQ = shutil.which("jq")
AWK = shutil.which("awk")
BASH = shutil.which("bash")


@unittest.skipUnless(JQ and AWK and BASH, "requires jq, awk, and bash")
class TailscaleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tailscale-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.scripts = self.root / "scripts"
        self.scripts.mkdir()
        for script in ("tailscale-toggle", "tailscale-status", "tailscale-menu"):
            shutil.copy2(SOURCE_SCRIPTS / script, self.scripts / script)
        for utility in (JQ, AWK):
            (self.bin / Path(utility).name).symlink_to(utility)

        self.calls = self.root / "calls"
        self.rofi_input = self.root / "rofi-input"
        self.env = {
            "HOME": str(self.root),
            "PATH": str(self.bin),
            "CALLS": str(self.calls),
            "ROFI_INPUT": str(self.rofi_input),
            "TS_JSON": '{"BackendState":"Stopped"}',
            "TS_EXIT": "0",
            "ACTION_EXIT": "0",
            "ROFI_EXIT": "0",
            "ROFI_CHOICE": "",
        }
        stubs = {
            "tailscale": '''
printf '%s\\n' "tailscale $*" >>"$CALLS"
if [[ "${1:-}" == status ]]; then printf '%s' "$TS_JSON"; exit "$TS_EXIT"; fi
exit "$ACTION_EXIT"
''',
            "notify-send": '''
printf '%s\\n' "notify-send $*" >>"$CALLS"
''',
            "rofi": '''
printf '%s\\n' "rofi $*" >>"$CALLS"
while IFS= read -r line; do printf '%s\\n' "$line" >>"$ROFI_INPUT"; done
printf '%s' "$ROFI_CHOICE"
exit "$ROFI_EXIT"
''',
            "wl-copy": '''
printf '%s\\n' "wl-copy $*" >>"$CALLS"
''',
            "xdg-open": '''
printf '%s\\n' "xdg-open $*" >>"$CALLS"
''',
            "tailscale-toggle": '''
printf '%s\\n' "tailscale-toggle $*" >>"$CALLS"
''',
        }
        for name, body in stubs.items():
            stub = self.bin / name
            stub.write_text("#!/bin/bash\nname=${0##*/}\n" + body)
            stub.chmod(0o755)

    def run_script(self, name, *args):
        return subprocess.run(
            [BASH, str(self.scripts / name), *args],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
            timeout=5,
        )

    def calls_text(self):
        return self.calls.read_text() if self.calls.exists() else ""

    def clear_calls(self):
        self.calls.unlink(missing_ok=True)
        self.rofi_input.unlink(missing_ok=True)

    def invalid_statuses(self):
        return [
            "",
            "not json",
            "{}",
            '{"BackendState":""}',
            '{"BackendState":null}',
            '{"BackendState":3}',
            '{"BackendState":"Stopped"}\n{"BackendState":"Running"}',
            "[]",
            "4",
        ]

    def test_toggle_refuses_invalid_status_and_never_changes_state(self):
        for output, cli_exit in [(value, "0") for value in self.invalid_statuses()] + [
            ('{"BackendState":"Running"}', "1")
        ]:
            with self.subTest(output=output, cli_exit=cli_exit):
                self.clear_calls()
                self.env.update(TS_JSON=output, TS_EXIT=cli_exit)
                result = self.run_script("tailscale-toggle")
                self.assertNotEqual(result.returncode, 0)
                calls = self.calls_text()
                self.assertNotIn("tailscale down", calls)
                self.assertNotIn("tailscale up", calls)
                self.assertIn("Could not read Tailscale status", calls)

    def test_toggle_valid_state_and_both_action_failure_notifications(self):
        self.env.update(TS_JSON='{"BackendState":"Stopped"}', TS_EXIT="0", ACTION_EXIT="0")
        self.assertEqual(self.run_script("tailscale-toggle").returncode, 0)
        self.assertIn("tailscale up", self.calls_text())
        self.clear_calls()
        self.env.update(TS_JSON='{"BackendState":"Running"}', ACTION_EXIT="0")
        self.assertEqual(self.run_script("tailscale-toggle").returncode, 0)
        self.assertIn("tailscale down", self.calls_text())
        self.clear_calls()
        self.env.update(ACTION_EXIT="1")
        self.assertEqual(self.run_script("tailscale-toggle").returncode, 0)
        self.assertIn("Failed to turn off", self.calls_text())
        self.clear_calls()
        self.env.update(TS_JSON='{"BackendState":"Stopped"}')
        self.assertEqual(self.run_script("tailscale-toggle").returncode, 0)
        self.assertIn("Failed to turn on", self.calls_text())

    def test_status_invalid_input_emits_plain_and_structured_errors(self):
        cases = [(value, "0") for value in self.invalid_statuses()] + [
            ('{"BackendState":"Running"}', "1")
        ]
        for output, cli_exit in cases:
            with self.subTest(output=output, cli_exit=cli_exit):
                self.env.update(TS_JSON=output, TS_EXIT=cli_exit)
                plain = self.run_script("tailscale-status", "--plain")
                self.assertEqual(plain.returncode, 0)
                self.assertTrue(plain.stdout.rstrip().endswith(" error"))
                structured = self.run_script("tailscale-status")
                self.assertEqual(structured.returncode, 0)
                data = json.loads(structured.stdout)
                self.assertEqual((data["class"], data["alt"], data["text"]), ("error", "error", "error"))

    def test_status_connected_ip_and_missing_optional_ip_formats(self):
        self.env.update(TS_EXIT="0")
        self.env["TS_JSON"] = '{"BackendState":"Running","Self":{"TailscaleIPs":["100.64.0.1"]}}'
        data = json.loads(self.run_script("tailscale-status").stdout)
        self.assertEqual((data["class"], data["alt"], data["text"]), ("connected", "connected", "100.64.0.1"))
        self.assertIn("100.64.0.1", data["tooltip"])
        plain = self.run_script("tailscale-status", "--plain")
        self.assertTrue(plain.stdout.rstrip().endswith(" 100.64.0.1"))

        for self_value in ("null", "{}", '{"TailscaleIPs":null}', '{"TailscaleIPs":[]}'):
            with self.subTest(self_value=self_value):
                self.env["TS_JSON"] = f'{{"BackendState":"Running","Self":{self_value}}}'
                data = json.loads(self.run_script("tailscale-status").stdout)
                self.assertEqual((data["class"], data["text"]), ("connected", "on"))
                self.assertIn("IP unavailable", data["tooltip"])

    def test_status_off_json_and_plain(self):
        self.env.update(TS_JSON='{"BackendState":"Stopped"}', TS_EXIT="0")
        data = json.loads(self.run_script("tailscale-status").stdout)
        self.assertEqual((data["class"], data["alt"], data["text"]), ("disconnected", "disconnected", "off"))
        self.assertTrue(self.run_script("tailscale-status", "--plain").stdout.rstrip().endswith(" off"))

    def test_status_wrong_typed_optional_fields_are_errors(self):
        for self_value in ('"bad"', '{"TailscaleIPs":false}', '{"TailscaleIPs":[9]}'):
            with self.subTest(self_value=self_value):
                self.env["TS_JSON"] = f'{{"BackendState":"Running","Self":{self_value}}}'
                data = json.loads(self.run_script("tailscale-status").stdout)
                self.assertEqual(data["class"], "error")

    def test_menu_invalid_status_notifies_before_rofi(self):
        cases = [(value, "0") for value in self.invalid_statuses()] + [
            ('{"BackendState":"Running"}', "1"),
            ('{"BackendState":"Running","Self":"bad"}', "0"),
            ('{"BackendState":"Running","Self":{"TailscaleIPs":false}}', "0"),
        ]
        for output, exit_code in cases:
            with self.subTest(output=output, exit_code=exit_code):
                self.clear_calls()
                self.env.update(TS_JSON=output, TS_EXIT=exit_code)
                result = self.run_script("tailscale-menu")
                self.assertNotEqual(result.returncode, 0)
                calls = self.calls_text()
                self.assertIn("Could not read Tailscale status", calls)
                self.assertNotIn("rofi", calls)

    def test_menu_labels_allow_null_optional_self_and_cancel_safely(self):
        self.env.update(TS_EXIT="0", TS_JSON='{"BackendState":"Stopped","Self":null}', ROFI_EXIT="1")
        result = self.run_script("tailscale-menu")
        self.assertEqual(result.returncode, 0)
        menu = self.rofi_input.read_text()
        self.assertIn("Turn on Tailscale", menu)
        self.assertIn("Copy this device's IP (-)", menu)
        self.assertNotIn("tailscale up", self.calls_text())
        self.assertNotIn("tailscale down", self.calls_text())
        self.assertNotIn("wl-copy", self.calls_text())

        self.clear_calls()
        self.env.update(TS_JSON='{"BackendState":"Running","Self":{"TailscaleIPs":null}}')
        self.assertEqual(self.run_script("tailscale-menu").returncode, 0)
        menu = self.rofi_input.read_text()
        self.assertIn("Turn off Tailscale", menu)
        self.assertIn("Copy this device's IP (-)", menu)


if __name__ == "__main__":
    unittest.main()

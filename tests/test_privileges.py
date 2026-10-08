"""Privilege handling uses copied libraries and mocks, never the host sudo."""

import errno
import json
import os
from pathlib import Path
import pty
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MOCK = r'''
import json, os, sys
from pathlib import Path
name = Path(sys.argv[0]).name
with open(os.environ["COMMAND_LOG"], "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == "sudo":
    if "-v" in sys.argv[1:]:
        sys.exit(int(os.environ.get("SUDO_AUTH_STATUS", "0")))
    if "chsh" in sys.argv[1:]:
        sys.exit(int(os.environ.get("SUDO_ACTION_STATUS", "0")))
    if sys.argv[1:] == ["pacman", "-S", "--needed", "gum"]:
        os.execv(sys.argv[0].replace("sudo", "pacman"), ["pacman", *sys.argv[2:]])
elif name == "getent":
    print("tester:x:1000:1000::" + os.environ["HOME"] + ":" +
          os.environ.get("ACCOUNT_SHELL", "/usr/bin/zsh"))
    sys.exit(0)
elif name == "pacman":
    Path(os.environ["PATH"], "gum").symlink_to(Path(__file__).resolve())
    sys.exit(0)
elif name == "yay":
    sys.exit(0)
sys.exit("Unexpected mock command: " + repr(sys.argv))
'''


class PrivilegeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="privilege-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.bin = self.base / "bin"
        self.home = self.base / "home"
        for directory in (self.repo, self.bin, self.home):
            directory.mkdir()
        shutil.copytree(ROOT / "lib", self.repo / "lib")
        for name in ("bash", "dirname", "readlink", "grep", "id"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (self.bin / name).symlink_to(executable)
        self.mock = self.bin / "mock-command"
        self.mock.write_text(f"#!{sys.executable}\n" + MOCK)
        self.mock.chmod(0o755)
        for name in ("sudo", "getent", "pacman"):
            (self.bin / name).symlink_to(self.mock)
        self.log = self.base / "commands.jsonl"
        self.env = {
            "PATH": str(self.bin), "HOME": str(self.home), "USER": "tester",
            "COMMAND_LOG": str(self.log), "LC_ALL": "C", "TERM": "dumb",
        }

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_library(self, body, code=0, library="components"):
        result = subprocess.run(
            [str(self.bin / "bash"), "-c",
             f'set -euo pipefail\nsource ./lib/{library}.sh\n' + body],
            cwd=self.repo, env=self.env, text=True, capture_output=True, timeout=10,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def preflight(self, steps, flags="NON_INTERACTIVE=true", code=0):
        entries = " ".join(f"'{step}|description|true|{step}'" for step in steps)
        return self.run_library(
            flags + f"\nSELECTED_COMPONENTS=({entries})\n"
            "validate_component_privileges || exit 1\nprintf 'preflight passed\\n'\n",
            code=code,
        )

    def test_noninteractive_preflight_validates_once_without_prompting(self):
        self.preflight(("packages", "shell", "yubikey"))
        self.assertEqual(self.calls(), [["sudo", "-n", "-v"]])

    def test_interactive_preflight_can_authenticate(self):
        self.preflight(("shell",), flags="NON_INTERACTIVE=false")
        self.assertEqual(self.calls(), [["sudo", "-v"]])

    def test_missing_sudo_is_reported_before_privileged_work(self):
        (self.bin / "sudo").unlink()
        result = self.preflight(("packages",), code=1)
        self.assertIn("sudo is required", result.stdout)
        self.assertNotIn("preflight passed", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_invalid_cached_credentials_fail_without_prompting(self):
        self.env["SUDO_AUTH_STATUS"] = "42"
        result = self.preflight(("yubikey",), code=1)
        self.assertIn("cached sudo credentials", result.stdout)
        self.assertNotIn("preflight passed", result.stdout)
        self.assertEqual(self.calls(), [["sudo", "-n", "-v"]])

    def test_user_only_and_dry_run_selections_need_no_sudo(self):
        (self.bin / "sudo").unlink()
        self.preflight(("stow", "theme", "node", "tmux", "backgrounds", "lazyvim"))
        self.preflight(("packages", "yay", "shell", "yubikey"),
                       flags="NON_INTERACTIVE=true\nDRY_RUN=true")
        self.assertEqual(self.calls(), [])

    def test_yay_only_needs_privileges_when_installing_it(self):
        self.preflight(("yay",))
        self.assertEqual(self.calls(), [["sudo", "-n", "-v"]])
        self.log.write_text("")
        (self.bin / "yay").symlink_to(self.mock)
        (self.bin / "sudo").unlink()
        self.preflight(("yay",))
        self.assertEqual(self.calls(), [])

    def test_login_shell_update_never_prompts_in_automation(self):
        self.run_library("NON_INTERACTIVE=true\nset_login_shell bash\n")
        shell = str((self.bin / "bash").resolve())
        self.assertEqual(self.calls(), [
            ["getent", "passwd", "tester"], ["sudo", "-n", "-v"],
            ["sudo", "-n", "chsh", "-s", shell, "tester"],
        ])

    def test_login_shell_auth_failure_does_not_call_chsh(self):
        self.env["SUDO_AUTH_STATUS"] = "42"
        self.run_library("NON_INTERACTIVE=true\nset_login_shell bash\n", code=1)
        self.assertEqual(self.calls(), [
            ["getent", "passwd", "tester"], ["sudo", "-n", "-v"],
        ])

    def test_login_shell_expired_credentials_cannot_trigger_prompt(self):
        self.env["SUDO_ACTION_STATUS"] = "42"
        self.run_library("NON_INTERACTIVE=true\nset_login_shell bash\n", code=42)
        self.assertEqual(self.calls()[-1][:3], ["sudo", "-n", "chsh"])

    def test_current_login_shell_and_dry_run_need_no_sudo(self):
        (self.bin / "sudo").unlink()
        self.env["ACCOUNT_SHELL"] = str((self.bin / "bash").resolve())
        self.run_library("NON_INTERACTIVE=true\nset_login_shell bash\n")
        self.assertEqual(self.calls(), [["getent", "passwd", "tester"]])
        self.log.write_text("")
        self.run_library("NON_INTERACTIVE=true\nDRY_RUN=true\nset_login_shell bash\n")
        self.assertEqual(self.calls(), [])

    def run_ui_on_terminal(self):
        master, slave = pty.openpty()
        try:
            with subprocess.Popen(
                [str(self.bin / "bash"), "-c",
                 'set -euo pipefail\nsource ./lib/ui.sh\nui_initialize\n'
                 'printf "UI_MODE=%s\\n" "$UI_MODE"'],
                cwd=self.repo, env=self.env, stdin=slave, stdout=slave, stderr=slave,
            ) as process:
                os.close(slave)
                slave = None
                os.write(master, b"yes\n")
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    raise
                output = bytearray()
                while True:
                    try:
                        chunk = os.read(master, 65536)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                        break
                    if not chunk:
                        break
                    output.extend(chunk)
                self.assertEqual(process.returncode, 0, output.decode())
                return output.decode()
        finally:
            os.close(master)
            if slave is not None:
                os.close(slave)

    def test_gum_auth_failure_falls_back_before_pacman(self):
        self.env["SUDO_AUTH_STATUS"] = "42"
        output = self.run_ui_on_terminal()
        self.assertIn("UI_MODE=plain", output)
        self.assertEqual(self.calls(), [["sudo", "-v"]])

    def test_gum_authenticates_before_optional_installation(self):
        output = self.run_ui_on_terminal()
        self.assertIn("UI_MODE=gum", output)
        self.assertEqual(self.calls(), [
            ["sudo", "-v"], ["sudo", "pacman", "-S", "--needed", "gum"],
            ["pacman", "-S", "--needed", "gum"],
        ])

    def test_gum_automation_and_dry_runs_never_authenticate(self):
        for flags in ("NON_INTERACTIVE=true", "DRY_RUN=true"):
            result = self.run_library(flags + '\nui_initialize\nprintf "%s\\n" "$UI_MODE"',
                                      library="ui")
            self.assertIn("plain", result.stdout)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()

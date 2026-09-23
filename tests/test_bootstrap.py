"""Exercise the piped bootstrap with isolated homes and mocked system commands."""

import fcntl
import os
from pathlib import Path
import pty
import shutil
import subprocess
import tempfile
import termios
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "install/bootstrap.sh"


@unittest.skipIf(os.geteuid() == 0, "Bootstrap intentionally rejects root")
class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin),
                        BOOTSTRAP_LOG=str(self.log))
        (self.bin / "bash").symlink_to(shutil.which("bash"))
        self.command("pacman", "exit 0")
        self.command("sudo", 'printf "prerequisites\\n" >> "$BOOTSTRAP_LOG"\n'
                     'exit "${FAIL_PREREQUISITES:-0}"')
        self.command("git", '''
[[ "$*" == "clone --branch main -- https://github.com/Abstrucked/abstrucked-arch.git $HOME/.dotfiles" ]] || exit 9
printf 'clone\\n' >> "$BOOTSTRAP_LOG"
[[ "${FAIL_CLONE:-0}" == 0 ]] || exit 8
''' + f'"{shutil.which("mkdir")}" "$HOME/.dotfiles"\n' + '''
printf '%s\\n' '[[ -t 0 ]] || exit 7' 'printf "installer\\n" >> "$BOOTSTRAP_LOG"' > "$HOME/.dotfiles/install.sh"
''')

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + body + "\n")
        path.chmod(0o755)

    def run_bootstrap(self, terminal=True):
        master, slave = pty.openpty()
        try:
            def setup():
                os.setsid()
                if terminal:
                    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)

            return subprocess.run(
                [str(self.bin / "bash")], input=SCRIPT.read_text(), text=True,
                capture_output=True, env=self.env, preexec_fn=setup,
                pass_fds=(slave,), timeout=10,
            )
        finally:
            os.close(master)
            os.close(slave)

    def test_pipe_preserves_interactive_installer(self):
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.log.read_text(), "prerequisites\nclone\ninstaller\n")

    def test_existing_checkout_is_untouched(self):
        destination = self.home / ".dotfiles"
        destination.mkdir()
        marker = destination / "keep"
        marker.write_text("local changes")
        result = self.run_bootstrap()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(), "local changes")
        self.assertFalse(self.log.exists())

    def test_prerequisite_failure_stops_before_clone(self):
        self.env["FAIL_PREREQUISITES"] = "6"
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 6)
        self.assertEqual(self.log.read_text(), "prerequisites\n")

    def test_clone_failure_stops_before_installer(self):
        self.env["FAIL_CLONE"] = "1"
        result = self.run_bootstrap()
        self.assertEqual(result.returncode, 8)
        self.assertEqual(self.log.read_text(), "prerequisites\nclone\n")

    def test_no_terminal_stops_before_changes(self):
        result = self.run_bootstrap(terminal=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("interactive terminal", result.stderr)
        self.assertFalse(self.log.exists())

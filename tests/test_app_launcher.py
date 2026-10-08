"""Safety and happy-path tests for the interactive app launcher helper."""
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/.local/bin/create-app-launcher"


class AppLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="app-launcher-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dotfiles = self.root / "checkout"
        self.script = self.dotfiles / "scripts/.local/bin/create-app-launcher"
        self.script.parent.mkdir(parents=True)
        shutil.copy2(SCRIPT, self.script)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.home / ".local/bin"
        self.bin.mkdir(parents=True)

        bash = self.dotfiles / "bash"
        (bash / ".config/bash").mkdir(parents=True)
        (bash / ".bashrc").write_text("# fixture bash rc\n")
        (bash / ".config/bash/aliases.sh").write_text("# existing aliases\n")
        (self.home / ".bashrc").symlink_to(bash / ".bashrc")
        self.env = os.environ.copy()
        self.env.update(HOME=str(self.home), LC_ALL="C",
                        PATH=str(self.bin) + os.pathsep + os.environ.get("PATH", ""))

    def run_interactive(self, program, category="dev"):
        master, slave = pty.openpty()
        process = subprocess.Popen([str(self.script)], env=self.env, stdin=slave,
                                   stdout=slave, stderr=slave, close_fds=True)
        output = bytearray()
        try:
            os.write(master, f"{program}\n{category}\n".encode())
            deadline = time.monotonic() + 10
            while process.poll() is None:
                remaining = deadline - time.monotonic()
                self.assertGreater(remaining, 0, output.decode(errors="replace"))
                ready, _, _ = select.select([master], [], [], min(remaining, 0.2))
                if ready:
                    try:
                        output.extend(os.read(master, 4096))
                    except OSError:
                        break
            process.wait(timeout=2)
            while select.select([master], [], [], 0)[0]:
                try:
                    output.extend(os.read(master, 4096))
                except OSError:
                    break
            return process.returncode, output.decode(errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_traversal_program_is_rejected_without_creating_outside_file(self):
        escaped = self.home / ".local/escape-launcher"
        for program in ("../escape", "bad..name"):
            with self.subTest(program=program):
                result, output = self.run_interactive(program)
                self.assertNotEqual(result, 0, output)
                self.assertIn("must contain only", output)
        self.assertFalse(escaped.exists())

    def test_category_shell_metacharacters_are_rejected(self):
        result, output = self.run_interactive("nvim", "dev;touch-pwned")
        self.assertNotEqual(result, 0, output)
        self.assertIn("Category must contain only", output)
        self.assertFalse((self.bin / "nvim-launcher").exists())

    def test_existing_launcher_is_backed_up_before_replacement(self):
        launcher = self.bin / "nvim-launcher"
        launcher.write_text("sentinel launcher content\n")
        result, output = self.run_interactive("nvim")
        self.assertEqual(result, 0, output)
        self.assertIn("backed up", output)
        backups = list(self.bin.glob("nvim-launcher.backup.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "sentinel launcher content\n")

    def test_generated_alias_is_safe_for_valid_input(self):
        result, output = self.run_interactive("code", "dev")
        self.assertEqual(result, 0, output)
        aliases = (self.dotfiles / "bash/.config/bash/aliases.sh").read_text()
        line = 'alias code-dev="$HOME/.local/bin/code-launcher"'
        self.assertIn(line, aliases)
        self.assertEqual(line, 'alias code-dev="$HOME/.local/bin/code-launcher"')

    def test_happy_path_creates_executable_launcher_and_alias(self):
        program = self.bin / "fixture-app"
        program.write_text("#!/bin/sh\nprintf 'app:%s\\n' \"$*\"\n")
        program.chmod(0o755)
        (self.bin / "load-api-keys.sh").write_text(":\n")
        result, output = self.run_interactive("fixture-app", "ai")
        self.assertEqual(result, 0, output)
        launcher = self.bin / "fixture-app-launcher"
        self.assertTrue(launcher.stat().st_mode & 0o111)
        run = subprocess.run([str(launcher), "hello", "world"], env=self.env,
                             capture_output=True, text=True, timeout=5)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout, "app:hello world\n")
        aliases = (self.dotfiles / "bash/.config/bash/aliases.sh").read_text()
        self.assertIn('alias fixture-app-ai="$HOME/.local/bin/fixture-app-launcher"', aliases)


if __name__ == "__main__":
    unittest.main()

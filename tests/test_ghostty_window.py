"""Exercise the ghostty-window wrapper against a fake ghostty."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/.local/bin/ghostty-window"


class GhosttyWindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls"
        self.cwd = self.root / "work dir"
        self.cwd.mkdir()
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "CALL_LOG": str(self.log),
            "HOME": str(self.root),
            "LC_ALL": "C",
        }
        # The fake logs "<cwd>|<arg>|<arg>..." per call. +new-window fails when
        # NEW_WINDOW_STATUS is non-zero, and a plain launch exits with
        # PLAIN_STATUS.
        self.fake(
            'printf "%s" "$PWD" >> "$CALL_LOG"\n'
            'for arg do printf "|%s" "$arg" >> "$CALL_LOG"; done\n'
            'printf "\\n" >> "$CALL_LOG"\n'
            'if [ "$1" = +new-window ]; then exit "${NEW_WINDOW_STATUS:-0}"; fi\n'
            'exit "${PLAIN_STATUS:-0}"'
        )

    def fake(self, body):
        path = self.bin / "ghostty"
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_wrapper(self, *args, env=None):
        return subprocess.run(
            [str(SCRIPT), *args],
            text=True,
            capture_output=True,
            cwd=self.cwd,
            env={**self.env, **(env or {})},
            timeout=10,
        )

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_forwards_arguments_intact_to_new_window(self):
        result = self.run_wrapper("-e", "sh", "-c", "echo $1", "arg with spaces", "")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [f"{self.cwd}|+new-window|-e|sh|-c|echo $1|arg with spaces|"],
        )

    def test_new_window_runs_in_callers_working_directory(self):
        # +new-window sends its own cwd to the instance when no
        # --working-directory is given, so the wrapper must not change it.
        self.run_wrapper()
        self.assertEqual(self.calls(), [f"{self.cwd}|+new-window"])

    def test_working_directory_option_is_passed_through(self):
        self.run_wrapper("--working-directory=/tmp/some dir", "--title=t")
        self.assertEqual(
            self.calls(),
            [f"{self.cwd}|+new-window|--working-directory=/tmp/some dir|--title=t"],
        )

    def test_falls_back_to_plain_ghostty_when_new_window_fails(self):
        result = self.run_wrapper(
            "-e", "nvim", "file name", env={"NEW_WINDOW_STATUS": "1"}
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.calls(),
            [
                f"{self.cwd}|+new-window|-e|nvim|file name",
                f"{self.cwd}|-e|nvim|file name",
            ],
        )

    def test_success_does_not_start_a_second_ghostty(self):
        self.run_wrapper("-e", "true")
        self.assertEqual(len(self.calls()), 1)

    def test_exit_status_is_new_window_success_or_fallback_status(self):
        self.assertEqual(self.run_wrapper(env={"PLAIN_STATUS": "7"}).returncode, 0)
        result = self.run_wrapper(env={"NEW_WINDOW_STATUS": "1", "PLAIN_STATUS": "7"})
        self.assertEqual(result.returncode, 7)

    def test_missing_ghostty_fails(self):
        (self.bin / "ghostty").unlink()
        result = self.run_wrapper(env={"PATH": str(self.bin)})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_script_is_executable_bash(self):
        self.assertTrue(os.access(SCRIPT, os.X_OK))
        self.assertEqual(SCRIPT.read_text().splitlines()[0], "#!/bin/bash")


if __name__ == "__main__":
    unittest.main()

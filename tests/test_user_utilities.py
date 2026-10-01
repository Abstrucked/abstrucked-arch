"""User helpers are exercised without a real password store or tmux server."""
import os
from pathlib import Path
import pty
import select
import shutil
import subprocess
import tempfile
import termios
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class UserUtilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="user-utilities-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        store = self.home / ".password-store"
        store.mkdir()
        (store / ".gpg-id").write_text("fixture-key")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "basename", "cat", "chmod", "grep", "tail", "tr"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.capture = self.root / "stored-password"
        self.log = self.root / "tmux-calls"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "LC_ALL": "C",
                    "PASS_CAPTURE": str(self.capture), "TMUX_LOG": str(self.log)}
        self.script("pass", '[[ "$1" == insert ]] || exit 9\ncat >"$PASS_CAPTURE"')
        self.script("pwgen", "printf 'fixture-generated-password\\n'")
        self.script("fzf", "exit 0")
        self.script("tmux", '''
printf '%s\n' "$*" >>"$TMUX_LOG"
if [[ "$1" == has-session ]]; then
  [[ "${HAS_SESSION:-0}" == 1 ]]
fi
''')

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + body + "\n")
        path.chmod(0o755)

    def run_helper(self, name, *args, input=""):
        result = subprocess.run([str(ROOT / "scripts/.local/bin" / name), *args],
                                env=self.env, input=input, capture_output=True,
                                text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_generated_passwords_are_stored_without_display(self):
        for args, input in ((('--generate',), "ai\nopenai api key\n"),
                            ((), "ai\nopenai api key\n\n")):
            with self.subTest(args=args):
                result = self.run_helper("pass-insert-utility", *args, input=input)
                self.assertEqual(self.capture.read_text(), "fixture-generated-password\n")
                self.assertNotIn("fixture-generated-password", result.stdout + result.stderr)

    def test_typed_password_disables_terminal_echo(self):
        master, slave = pty.openpty()
        process = subprocess.Popen([str(ROOT / "scripts/.local/bin/pass-insert-utility")],
                                   env=self.env, stdin=slave, stdout=slave, stderr=slave)
        output = b""
        try:
            os.write(master, b"ai\nopenai api key\n")
            deadline = time.monotonic() + 5
            while b"Enter password" not in output:
                remaining = deadline - time.monotonic()
                self.assertGreater(remaining, 0, output.decode(errors="replace"))
                ready, _, _ = select.select([master], [], [], remaining)
                self.assertTrue(ready)
                output += os.read(master, 4096)
            # The prompt is written just before read -s changes terminal flags.
            while termios.tcgetattr(slave)[3] & termios.ECHO:
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.005)
            os.write(master, b"fixture-typed-password\n")
            self.assertEqual(process.wait(timeout=5), 0)
            while select.select([master], [], [], 0)[0]:
                output += os.read(master, 4096)
            self.assertNotIn(b"fixture-typed-password", output)
            self.assertEqual(self.capture.read_text(), "fixture-typed-password\n")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            os.close(master)
            os.close(slave)

    def test_sessionizer_attaches_outside_tmux_and_switches_inside(self):
        for inside in (False, True):
            for exists in (False, True):
                with self.subTest(inside=inside, exists=exists):
                    self.env["HAS_SESSION"] = str(int(exists))
                    if inside:
                        self.env["TMUX"] = "fixture-server,1,0"
                    else:
                        self.env.pop("TMUX", None)
                    self.log.unlink(missing_ok=True)
                    self.run_helper("tmux-sessionizer", str(self.home))
                    calls = self.log.read_text().splitlines()
                    expected = ["has-session -t=home"]
                    if not exists:
                        expected.append(f"new-session -ds home -c {self.home}")
                    action = "switch-client" if inside else "attach-session"
                    expected.append(f"{action} -t home")
                    self.assertEqual(calls, expected)

    def test_gtk_bookmarks_adds_xdg_folders_once_and_keeps_existing(self):
        for name in ("awk", "dirname", "mkdir", "python3", "touch"):
            (self.bin / name).symlink_to(shutil.which(name))
        # Pictures is configured but missing and Videos is unset, so neither
        # is bookmarked; the space and the accent must be URI-encoded.
        self.script("xdg-user-dir", '''
case "$1" in
  DOCUMENTS) echo "$HOME/Documents" ;;
  DOWNLOAD) echo "$HOME/My Downloads" ;;
  MUSIC) echo "$HOME/Música" ;;
  PICTURES) echo "$HOME/Pictures" ;;
  *) echo "$HOME" ;;
esac''')
        for folder in ("Documents", "My Downloads", "Música"):
            (self.home / folder).mkdir()
        bookmarks = self.home / ".config/gtk-3.0/bookmarks"
        bookmarks.parent.mkdir(parents=True)
        documents = (self.home / "Documents").as_uri()
        # Already bookmarked under a label, and a last line without a newline.
        bookmarks.write_text(f"{documents} Docs\nsftp://server/srv")
        for _ in range(2):
            self.run_helper("gtk-bookmarks")
        self.assertEqual(bookmarks.read_text().splitlines(), [
            f"{documents} Docs",
            "sftp://server/srv",
            (self.home / "My Downloads").as_uri(),
            (self.home / "Música").as_uri(),
        ])
        self.assertIn("/My%20Downloads", bookmarks.read_text())

    def test_shared_dependencies_and_theme_are_portable(self):
        shared = (ROOT / "packages.list").read_text().splitlines()
        hypr = (ROOT / "packages-hyprland.list").read_text().splitlines()
        for package in ("jq", "dex"):
            self.assertIn(package, shared)
            self.assertNotIn(package, hypr)
        config = (ROOT / "btop/.config/btop/btop.conf").read_text()
        self.assertIn('color_theme = "themectl"', config)
        self.assertNotIn("/home/abstrucked", config)

    def test_sessions_set_qt6ct_and_shells_leave_toolkit_themes_alone(self):
        # Qt and GTK take their themes from themectl's config files; a shell
        # export would override them for every app started from a terminal.
        sessions = {
            "xsession/.xprofile": "export QT_QPA_PLATFORMTHEME=qt6ct",
            "hyprland/.config/hypr/environment.conf": "env = QT_QPA_PLATFORMTHEME,qt6ct",
            "hyprland/.config/hypr/lua/environment.lua": 'hl.env("QT_QPA_PLATFORMTHEME", "qt6ct")',
        }
        for path, line in sessions.items():
            self.assertIn(line, (ROOT / path).read_text().splitlines(), path)
        for path in ("zsh/.zshrc", "bash/.config/bash/bashrc"):
            rc = (ROOT / path).read_text()
            for name in ("GTK_THEME", "QT_QPA_PLATFORMTHEME"):
                self.assertNotRegex(rc, rf"(?m)^\s*export {name}=", f"{path} exports {name}")

    def test_bash_completion_preserves_spaces_globs_and_ifs_on_failure(self):
        config = (ROOT / "bash/.config/bash/bashrc").read_text()
        start = config.index("  _pm2_completion")
        end = config.index("  complete ", start)
        function = config[start:end]
        body = function + '''
pm2() { printf '%s\n' 'first choice' '*.lua'; }
COMP_CWORD=1 COMP_LINE=pm2 COMP_POINT=3
COMP_WORDS=(pm2 '')
_pm2_completion
[[ ${#COMPREPLY[@]} == 2 && ${COMPREPLY[0]} == 'first choice' && ${COMPREPLY[1]} == '*.lua' ]]
pm2() { return 42; }
IFS=:
if _pm2_completion; then exit 9; else [[ $? == 42 ]]; fi
[[ $IFS == : ]]
'''
        result = subprocess.run(["bash", "-euc", body], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

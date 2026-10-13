"""Closure-persistence tests against a private tmux server and save fixture."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/.local/bin/tmux-save-workspace"
CONFIG = ROOT / "config/tmux/tmux.conf"
TMUX_BINARY = os.environ.get("TMUX_TEST_BINARY") or shutil.which("tmux")


@unittest.skipUnless(TMUX_BINARY, "needs tmux")
class TmuxPersistenceTests(unittest.TestCase):
    def setUp(self):
        temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        self.temp = tempfile.TemporaryDirectory(prefix="tmux-persistence-", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home space ' ; #"
        self.home.mkdir()
        self.socket = self.root / "tmux.sock"
        self.resurrect = self.home / ".tmux/resurrect"
        self.resurrect.mkdir(parents=True)
        self.bindir = self.root / "bin"
        self.bindir.mkdir()
        self.wrapper = self.bindir / "tmux"
        self.wrapper.write_text(
            "#!/bin/sh\nexec " + shlex.quote(shutil.which(TMUX_BINARY))
            + " -S " + shlex.quote(str(self.socket)) + " \"$@\"\n"
        )
        self.wrapper.chmod(0o755)
        self.helper = self.home / ".local/bin/tmux-save-workspace"
        self.helper.parent.mkdir(parents=True)
        shutil.copy2(HELPER, self.helper)
        self.helper.chmod(0o755)
        self.save = self.root / "resurrect-save"
        # Same second-precision filename and last symlink shape as resurrect.
        self.save.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "dir=$(tmux show-option -gqv @resurrect-dir)\n"
            "mkdir \"$dir/save-in-progress\"\n"
            "trap 'rmdir \"$dir/save-in-progress\"' EXIT\n"
            "printf 'save\\n' >> \"$dir/save-calls\"\n"
            "delay=$(tmux show-option -gqv @test-save-delay)\n"
            "[ -z \"$delay\" ] || sleep \"$delay\"\n"
            "file=\"$dir/tmux_resurrect_$(date +%Y%m%dT%H%M%S).txt\"\n"
            "tmux list-panes -a -F '#{session_name} #{window_name} #{pane_id}' > \"$file\"\n"
            "if cmp -s \"$file\" \"$dir/last\"; then\n"
            "    rm \"$file\"\n"
            "else\n"
            "    ln -sfn \"$(basename \"$file\")\" \"$dir/last\"\n"
            "fi\n"
        )
        self.save.chmod(0o755)
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bindir) + os.pathsep + os.defpath,
            "TERM": "xterm-256color", "LC_ALL": "C", "SHELL": "/bin/sh",
            "TMUX_TEST_SOCKET": str(self.socket),
        }
        self.addCleanup(self.stop_server)
        self.tmux("-f", "/dev/null", "new-session", "-d", "-s", "main", "sleep", "300")
        self.tmux("set-option", "-g", "@resurrect-dir", str(self.resurrect))
        self.tmux("set-option", "-g", "@resurrect-save-script-path", str(self.save))
        self.tmux("set-option", "-g", "@resurrect-save", "C-s")
        self.tmux("set-option", "-s", "exit-empty", "on")
        self.install()

    def tmux(self, *args, check=True):
        result = subprocess.run([str(self.wrapper), *args], env=self.env,
                                capture_output=True, timeout=10)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result

    def install(self):
        return subprocess.run([str(self.helper), "--install"], env=self.env,
                              capture_output=True, timeout=10, check=True)

    def stop_server(self):
        self.tmux("kill-server", check=False)

    def save_now(self):
        subprocess.run([str(self.helper)], env=self.env, timeout=10, check=True)

    def latest(self):
        pointer = self.resurrect / "last"
        return pointer.resolve() if pointer.is_symlink() else None

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.025)
        self.fail("timed out waiting for isolated tmux closure persistence")

    def kill_pane(self, target):
        self.tmux("kill-pane", "-t", target)

    def test_closures_save_remaining_panes_and_final_exit_clears_only_latest(self):
        self.tmux("split-window", "-d", "-t", "main", "sleep", "300")
        self.tmux("new-window", "-d", "-t", "main:1", "-n", "disposable", "sleep", "300")
        self.save_now()
        initial = self.latest()
        self.assertIsNotNone(initial)
        self.assertEqual(len(initial.read_text().splitlines()), 3)

        # Explicit pane kill; the corresponding snapshot contains only survivors.
        self.kill_pane("%1")
        self.wait_for(lambda: self.latest() != initial)
        current = self.latest()
        self.assertEqual(len(current.read_text().splitlines()), 2)
        self.assertNotIn("%1", current.read_text())

        # Exiting a pane's shell while other panes survive is also a closure.
        transient = self.tmux("split-window", "-d", "-P", "-F", "#{pane_id}",
                              "-t", "main", "/bin/sh").stdout.decode().strip()
        self.save_now()
        before_exit = self.latest()
        self.assertEqual(len(before_exit.read_text().splitlines()), 3)
        self.tmux("send-keys", "-t", transient, "exit", "Enter")
        self.wait_for(lambda: self.latest() != before_exit)
        current = self.latest()
        self.assertEqual(len(current.read_text().splitlines()), 2)

        # Closing a whole window saves panes in the remaining window.
        self.tmux("kill-window", "-t", "main:1")
        self.wait_for(lambda: self.latest() != current)
        current = self.latest()
        self.assertEqual(len(current.read_text().splitlines()), 1)

        # Closing a non-final session saves the other session; final closure
        # clears the restore pointer but retains every historical snapshot.
        self.tmux("new-session", "-d", "-s", "other", "sleep", "300")
        self.save_now()
        before_session_close = self.latest()
        self.tmux("kill-session", "-t", "other")
        self.wait_for(lambda: self.latest() != before_session_close)
        self.assertIn("main", self.latest().read_text())

        historical = set(self.resurrect.glob("tmux_resurrect_*.txt"))
        self.tmux("set-option", "-s", "exit-empty", "on")
        self.tmux("kill-session", "-t", "main")
        self.wait_for(lambda: self.latest() is None)
        self.assertFalse((self.resurrect / "last").exists())
        self.assertEqual(set(self.resurrect.glob("tmux_resurrect_*.txt")), historical)
        self.wait_for(lambda: self.tmux("list-sessions", check=False).returncode != 0)

    def test_restore_guard_hooks_bindings_and_reload_are_idempotent(self):
        self.assertIn("@resurrect-hook-pre-restore-all", CONFIG.read_text())
        self.assertIn("@resurrect-hook-post-restore-all", CONFIG.read_text())
        self.tmux("set-option", "-g", "@workspace-restoring", "on")
        self.save_now()
        self.assertIsNone(self.latest())
        self.tmux("set-option", "-g", "@workspace-restoring", "off")
        self.save_now()
        previous = self.latest()
        self.tmux("set-option", "-g", "@workspace-restoring", "on")
        pane = self.tmux("split-window", "-d", "-P", "-F", "#{pane_id}",
                         "-t", "main", "sleep", "300").stdout.decode().strip()
        self.kill_pane(pane)
        self.tmux("run-shell", "sleep 0.1")
        self.assertEqual(self.latest(), previous)
        self.assertEqual(self.tmux("show-option", "-sqv", "exit-empty").stdout.strip(), b"on")
        self.tmux("set-option", "-g", "@workspace-restoring", "off")
        self.tmux("set-hook", "-g", "after-kill-pane[12]", "display-message unrelated")
        self.install()
        self.install()
        listing = self.tmux("show-hooks", "-g").stdout.decode()
        self.assertIn("after-kill-pane[12]", listing, listing)
        self.assertIn("display-message unrelated", listing, listing)
        for hook in ("after-kill-pane", "window-unlinked", "session-closed"):
            self.assertEqual(sum(hook in line and "[90]" in line for line in listing.splitlines()), 1, listing)
        self.assertIn('pane-exited[90]', HELPER.read_text())
        bindings = self.tmux("list-keys", "-T", "prefix").stdout
        self.assertTrue(any(b"C-s" in line and b"tmux-save-workspace" in line
                            for line in bindings.splitlines()))
        self.assertEqual(self.tmux("show-option", "-gqv", "@resurrect-save-script-path").stdout.strip(),
                         str(self.helper).encode())
        self.assertEqual(self.tmux("show-option", "-gqv", "@workspace-exit-empty").stdout.strip(), b"on")
        self.assertNotEqual(previous, None)

    def test_custom_save_binding_and_rapid_closures_leave_valid_pointer(self):
        self.tmux("set-option", "-gu", "@workspace-exit-empty")
        self.tmux("set-option", "-s", "exit-empty", "off")
        self.tmux("set-option", "-g", "@resurrect-save", "C-x C-y")
        self.install()
        self.assertEqual(self.tmux("show-option", "-gqv", "@resurrect-save").stdout.strip(), b"C-x C-y")
        self.assertEqual(self.tmux("show-option", "-gqv", "@resurrect-save-script-path").stdout.strip(),
                         str(self.helper).encode())
        self.assertEqual(self.tmux("show-option", "-gqv", "@workspace-exit-empty").stdout.strip(), b"off")
        bindings = self.tmux("list-keys", "-T", "prefix").stdout
        helper_bindings = [line for line in bindings.splitlines() if b"tmux-save-workspace" in line]
        self.assertTrue(any(b"C-x" in line for line in helper_bindings))
        self.assertTrue(any(b"C-y" in line for line in helper_bindings))
        self.tmux("split-window", "-d", "-t", "main", "sleep", "300")
        self.tmux("split-window", "-d", "-t", "main", "sleep", "300")
        self.save_now()
        self.kill_pane("%2")
        self.kill_pane("%1")
        self.wait_for(lambda: self.latest() is not None and self.latest().exists()
                      and len(self.latest().read_text().splitlines()) == 1)
        self.assertTrue(self.latest().is_file())

    def test_final_shell_exit_clears_restore_pointer_and_preserves_backups(self):
        self.tmux("respawn-pane", "-k", "-t", "main", "/bin/sh")
        self.save_now()
        historical = set(self.resurrect.glob("tmux_resurrect_*.txt"))
        self.assertTrue(historical)
        self.tmux("send-keys", "-t", "main", "exit", "Enter")
        self.wait_for(lambda: self.tmux("list-sessions", check=False).returncode != 0)
        self.assertFalse((self.resurrect / "last").is_symlink())
        self.assertEqual(set(self.resurrect.glob("tmux_resurrect_*.txt")), historical)

    def test_empty_workspace_preserves_exit_empty_off(self):
        self.tmux("set-option", "-gu", "@workspace-exit-empty")
        self.tmux("set-option", "-s", "exit-empty", "off")
        self.install()
        self.save_now()
        self.tmux("kill-session", "-t", "main")
        self.wait_for(lambda: self.latest() is None)
        self.assertEqual(self.tmux("show-option", "-sqv", "exit-empty").stdout.strip(), b"off")
        self.assertEqual(self.tmux("list-sessions").stdout, b"")

    def test_concurrent_saves_are_serialized_and_leave_a_valid_snapshot(self):
        self.tmux("set-option", "-g", "@test-save-delay", "0.2")
        processes = [subprocess.Popen([str(self.helper), "quiet"], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                     for _ in range(2)]
        try:
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, stdout + stderr)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        self.assertTrue(self.latest().is_file())
        self.assertEqual(len(self.latest().read_text().splitlines()), 1)
        self.assertEqual((self.resurrect / "save-calls").read_text().splitlines(), ["save", "save"])

    def test_secondary_server_without_continuum_ownership_does_not_install_hooks(self):
        for hook in ("after-kill-pane", "pane-exited", "window-unlinked", "session-closed"):
            self.tmux("set-hook", "-gu", hook + "[90]")
        self.tmux("set-option", "-g", "@resurrect-save-script-path", str(self.save))
        self.tmux("set-option", "-g", "@continuum-save-interval", "15")
        self.install()
        self.assertEqual(self.tmux("show-option", "-gqv", "@resurrect-save-script-path").stdout.strip(),
                         str(self.save).encode())
        self.assertNotIn(b"[90]", self.tmux("show-hooks", "-g").stdout)


if __name__ == "__main__":
    unittest.main()

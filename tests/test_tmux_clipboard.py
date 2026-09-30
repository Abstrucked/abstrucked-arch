"""Exercise native clipboard output and paste through real, isolated tmux PTYs."""
import base64
import os
from pathlib import Path
import pty
import re
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import termios
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/tmux/tmux.conf"
TMUX = shutil.which("tmux")
OSC52 = re.compile(rb"\x1b\]52;[^;]*;([A-Za-z0-9+/=]*)(?:\x07|\x1b\\)")


@unittest.skipUnless(TMUX and Path("/usr/bin/zsh").exists(), "needs tmux 3.2+ and zsh")
class TmuxClipboardTests(unittest.TestCase):
    def setUp(self):
        temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        self.temp = tempfile.TemporaryDirectory(prefix="tmux-copy-", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        # Quoting must work for the directory-copy shortcut, including shell syntax.
        self.work = self.root / "work ' $HOME; # space"
        self.work.mkdir()
        self.env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "PATH": os.defpath, "TERM": "xterm-256color", "LC_ALL": "C.UTF-8",
                    "SHELL": "/bin/sh"}
        # No DISPLAY, WAYLAND_DISPLAY, SSH forwarding or clipboard utilities.
        self.socket = str(self.root / "outer")
        self.inner = str(self.root / "inner")
        self.content = self.root / "content"
        self.content.write_text("alpha βeta\nsecond café\nthird line")
        self.received = self.root / "received"
        self.ready = self.root / "ready"
        app = self.root / "app.py"
        app.write_text('''import os
from pathlib import Path
import sys
import tty

tty.setraw(0)
content, received, ready = map(Path, sys.argv[1:])
with received.open("wb", buffering=0) as output:
    os.write(1, b"\\x1b[?2004h" + content.read_bytes().replace(b"\\n", b"\\r\\n"))
    ready.touch()
    while True:
        data = os.read(0, 65536)
        if not data:
            break
        output.write(data)
''')
        self.app = shlex.join([sys.executable, "-u", str(app), str(self.content),
                               str(self.received), str(self.ready)])
        self.addCleanup(self.stop_servers)
        self.tmux("new-session", "-d", "-s", "test", "-x", "100", "-y", "30",
                  "-c", str(self.work), self.app)
        self.wait_for(self.ready.exists)
        self.master, self.slave = pty.openpty()
        termios.tcsetwinsize(self.slave, (30, 100))
        self.addCleanup(os.close, self.master)
        self.addCleanup(os.close, self.slave)
        self.client = subprocess.Popen([TMUX, "-S", self.socket, "attach-session", "-t", "test"],
                                       env=self.env, stdin=self.slave, stdout=self.slave,
                                       stderr=self.slave)
        self.addCleanup(self.stop_client)
        self.wait_for(lambda: self.tmux("list-clients", "-F", "#{client_name}").stdout.strip())
        self.wait_for(lambda: not termios.tcgetattr(self.slave)[3] & termios.ICANON)

    def tmux(self, *args, socket=None, check=True):
        result = subprocess.run([TMUX, "-S", socket or self.socket, "-f", str(CONFIG), *args],
                                env=self.env, capture_output=True, timeout=10)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        return result

    def stop_client(self):
        if self.client.poll() is None:
            self.client.terminate()
        self.client.wait(timeout=5)

    def stop_servers(self):
        for socket in (self.inner, self.socket):
            self.tmux("kill-server", socket=socket, check=False)

    def wait_for(self, predicate):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("timed out waiting for tmux/application state")

    def clipboard(self):
        output = b""
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            readable, _, _ = select.select([self.master], [], [], 0.1)
            if readable:
                output += os.read(self.master, 65536)
                matches = OSC52.findall(output)
                if matches:
                    return base64.b64decode(matches[-1], validate=True)
        self.fail(f"no OSC 52 clipboard write: {output[-1000:]!r}")

    def assert_buffer(self, expected, socket=None):
        self.wait_for(lambda: self.tmux("save-buffer", "-", socket=socket,
                                       check=False).stdout == expected)

    def assert_pasted(self, expected):
        self.wait_for(lambda: len(self.received.read_bytes()) >= len(expected))
        self.assertEqual(self.received.read_bytes(), expected)

    def enter_copy_mode(self, nested=False):
        os.write(self.master, b"\x01\x01[" if nested else b"\x01[")
        # tmux queues the copy-mode command; later keys need the new key table.
        self.wait_for(lambda: self.tmux(
            "display-message", "-p", "#{pane_in_mode}",
            socket=self.inner if nested else self.socket).stdout.strip() == b"1")

    def test_vi_line_selection_copies_unicode_and_bracketed_pastes(self):
        # Real keys: prefix [, history top, column zero, visual line, down, yank.
        self.enter_copy_mode()
        os.write(self.master, b"g0Vjy")
        expected = "alpha βeta\nsecond café\n".encode()
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)
        os.write(self.master, b"\x01]")
        # tmux's paste-buffer uses CR for line breaks, like terminal Return.
        self.assert_pasted(b"\x1b[200~" + expected.replace(b"\n", b"\r") + b"\x1b[201~")

    def test_rectangle_selection_and_enter_use_the_same_clipboard(self):
        self.enter_copy_mode()
        os.write(self.master, b"g0\x16lj\r")
        expected = b"al\nse"
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)

    def test_mouse_drag_copies_to_the_terminal_clipboard(self):
        # SGR mouse reporting: press on row 1, drag into row 2, then release.
        os.write(self.master, b"\x1b[<0;1;1M\x1b[<32;5;2M")
        self.wait_for(lambda: self.tmux(
            "display-message", "-p", "#{pane_in_mode}").stdout.strip() == b"1")
        os.write(self.master, b"\x1b[<0;5;2m")
        expected = "alpha βeta\nsecon".encode()
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)

    def test_prefix_y_copies_the_cursor_line_without_editing_the_application(self):
        os.write(self.master, b"\x01y")
        expected = b"third line\n"
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)
        self.assertEqual(self.received.read_bytes(), b"")

    def test_directory_copy_quotes_paths_and_terminal_paste_is_independent(self):
        os.write(self.master, b"\x01Y")
        expected = str(self.work).encode()
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)
        # A terminal's paste shortcut sends bracketed text, not a clipboard query.
        pasted = "text from a different app\nnaïve café".encode()
        os.write(self.master, b"\x1b[200~" + pasted + b"\x1b[201~")
        self.assert_pasted(b"\x1b[200~" + pasted + b"\x1b[201~")
        self.assert_buffer(expected)

    def test_reload_replaces_legacy_bindings_without_accumulating_capabilities(self):
        self.tmux("set-option", "-as", "terminal-overrides", r",*:Ms=\E]52;c;%p1%s\a")
        self.tmux("bind-key", "-T", "copy-mode-vi", "y", "send-keys", "-X",
                  "copy-pipe-and-cancel", "wl-copy")
        self.tmux("bind-key", "-T", "copy-mode", "y", "send-keys", "-X",
                  "copy-pipe-and-cancel", "wl-copy")
        self.tmux("source-file", str(CONFIG))
        options = self.tmux("show-options", "-s").stdout
        self.tmux("source-file", str(CONFIG))
        self.assertEqual(self.tmux("show-options", "-s").stdout, options)
        self.assertNotIn(b"wl-copy", self.tmux("list-keys").stdout)
        self.assertNotIn(b"%p1%s", self.tmux("show-options", "-s", "terminal-overrides").stdout)
        self.enter_copy_mode()
        os.write(self.master, b"g0VY")
        expected = "alpha βeta\n".encode()
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected)
        self.assert_pasted(b"\x1b[200~" + expected.replace(b"\n", b"\r") + b"\x1b[201~")

    def test_nested_tmux_forwards_large_clipboards_and_paste(self):
        self.content.write_text("café βeta clipboard payload\n" * 1200 + "last line")
        self.ready.unlink()
        self.tmux("new-session", "-d", "-s", "test", "-x", "100", "-y", "29",
                  "-c", str(self.work), self.app, socket=self.inner)
        self.wait_for(self.ready.exists)
        attach = shlex.join(["env", "-u", "TMUX", TMUX, "-S", self.inner,
                             "attach-session", "-t", "test"])
        self.tmux("respawn-pane", "-k", attach)
        self.wait_for(lambda: b"tmux-256color" in self.tmux(
            "list-clients", "-F", "#{client_termname}", socket=self.inner).stdout)
        # Double prefix reaches the inner tmux, as it does through SSH.
        self.enter_copy_mode(nested=True)
        os.write(self.master, b"g0vG$y")
        expected = self.content.read_bytes()
        self.assertEqual(self.clipboard(), expected)
        self.assert_buffer(expected, socket=self.inner)
        self.assert_buffer(expected)
        os.write(self.master, b"\x01\x01]")
        self.assert_pasted(b"\x1b[200~" + expected.replace(b"\n", b"\r") + b"\x1b[201~")


if __name__ == "__main__":
    unittest.main()

"""Parse the full config in an isolated tmux server and run its project commands."""
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class TmuxProjectBindingsTests(unittest.TestCase):
    def test_configured_paths_survive_real_tmux_parsing(self):
        tmux = shutil.which("tmux")
        self.assertIsNotNone(tmux, "tmux is required")
        temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        with tempfile.TemporaryDirectory(prefix="tmux-project-", dir=temp_root) as directory:
            root = Path(directory)
            home = root / "home with spaces"
            helpers = home / ".local/bin"
            helpers.mkdir(parents=True)
            commands = root / "commands"
            commands.mkdir()
            for name in ("bash", "sh", "sleep"):
                executable = shutil.which(name)
                self.assertIsNotNone(executable, name)
                (commands / name).symlink_to(executable)
            helper = helpers / "tmux-sessionizer"
            helper.write_text('#!/bin/sh\nprintf "%s\\0" "$@" >>"$BIND_LOG"\n')
            helper.chmod(0o755)
            tpm = home / ".tmux/plugins/tpm/tpm"
            tpm.parent.mkdir(parents=True)
            tpm.write_text("#!/bin/sh\nexit 0\n")
            tpm.chmod(0o755)
            config = root / "tmux.conf"
            shutil.copy2(ROOT / "config/tmux/tmux.conf", config)
            socket = root / "socket"
            log = root / "args"
            env = {"HOME": str(home), "PATH": str(commands), "SHELL": str(commands / "bash"),
                   "TERM": "xterm-256color", "LC_ALL": "C", "BIND_LOG": str(log),
                   "DOTFILES_CONFIG_DIR": str(root / "initial-config"),
                   "DOTFILES_DEV_DIR": str(root / "initial-dev")}

            def run(*args, check=True):
                return subprocess.run([tmux, "-S", str(socket), "-f", str(config), *args],
                                      env=env, capture_output=True, text=True, check=check, timeout=10)

            try:
                run("new-session", "-d", "-s", "fixture", "sleep 30")
                bindings = [(line, shlex.split(line))
                            for line in run("list-keys", "-T", "prefix").stdout.splitlines()]
                for key, variable in (("C", "DOTFILES_CONFIG_DIR"), ("D", "DOTFILES_DEV_DIR")):
                    line, parsed = next((line, parts) for line, parts in bindings if "run-shell" in parts
                                        and parts[parts.index("run-shell") - 1] == key)
                    command = parsed[parsed.index("run-shell") + 1]
                    self.assertIn("${" + variable, command)
                    # Change the environment after loading: expansion must be
                    # deferred to the shell, not frozen during config parsing.
                    chosen = str(root / f"chosen {key} with ' & [glob] $HOME")
                    run("set-environment", "-t", "fixture", variable, chosen)
                    log.unlink(missing_ok=True)
                    # list-keys emits tmux syntax, not shell syntax: let tmux
                    # decode its own quoting rather than stripping escapes.
                    invoke = root / "invoke.conf"
                    invoke.write_text("run-shell " + line.split(" run-shell ", 1)[1] + "\n")
                    run("source-file", str(invoke))
                    self.assertEqual(log.read_bytes(), chosen.encode() + b"\0")
            finally:
                run("kill-server", check=False)


if __name__ == "__main__":
    unittest.main()

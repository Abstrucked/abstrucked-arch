"""Parse the full config in an isolated tmux server and run its project commands."""
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def decode_tmux_string(text):
    r"""Undo the double-quoting that `tmux list-keys` applies to a command.

    tmux 3.4 (Ubuntu 24.04) double-escapes `$` when listing keys (`\\$HOME`),
    which tmux itself rejects when re-parsed ("invalid environment variable"),
    while newer releases emit `\$HOME`. The configured commands contain no
    literal backslashes, so after removing one level of quoting any leftover
    `\$` is that quirk and means a plain `$`.
    """
    if len(text) > 1 and text[0] == text[-1] == '"':
        text = re.sub(r"\\(.)", r"\1", text[1:-1])
    return text.replace("\\$", "$")


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
                result = subprocess.run([tmux, "-S", str(socket), "-f", str(config), *args],
                                        env=env, capture_output=True, text=True, timeout=10)
                if check and result.returncode:
                    self.fail(f"{tmux} {' '.join(args)} exited {result.returncode}\n"
                              f"stdout: {result.stdout}\nstderr: {result.stderr}")
                return result

            try:
                run("new-session", "-d", "-s", "fixture", "sleep 30")
                bindings = [(line, shlex.split(line))
                            for line in run("list-keys", "-T", "prefix").stdout.splitlines()]
                for key, variable in (("C", "DOTFILES_CONFIG_DIR"), ("D", "DOTFILES_DEV_DIR")):
                    line = next(line for line, parts in bindings if "run-shell" in parts
                                and parts[parts.index("run-shell") - 1] == key)
                    command = decode_tmux_string(line.split(" run-shell ", 1)[1])
                    self.assertIn("${" + variable, command)
                    self.assertNotIn("\\", command)
                    # Change the environment after loading: expansion must be
                    # deferred to the shell, not frozen during config parsing.
                    chosen = str(root / f"chosen {key} with ' & [glob] $HOME")
                    run("set-environment", "-t", "fixture", variable, chosen)
                    log.unlink(missing_ok=True)
                    # Pass the decoded command as an argument instead of
                    # re-sourcing list-keys output, which not every tmux
                    # release prints in a form its own parser accepts.
                    run("run-shell", "-t", "fixture", command)
                    self.assertEqual(log.read_bytes(), chosen.encode() + b"\0")
            finally:
                run("kill-server", check=False)


if __name__ == "__main__":
    unittest.main()

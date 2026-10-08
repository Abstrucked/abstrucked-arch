"""Portable shortcut paths and machine-specific helper arguments."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / "scripts/.config/shell/env.sh"
ALIASES = ROOT / "scripts/.config/shell/aliases.sh"
SESSIONIZER = ROOT / "scripts/.local/bin/tmux-sessionizer"
TAILSCALE = ROOT / "scripts/.local/bin/tailscale-ssh"
SHELLS = [(name, shutil.which(name)) for name in ("sh", "bash", "zsh")]


class ShortcutPortabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [name for name, shell in SHELLS if not shell]
        if missing:
            raise RuntimeError(f"required shell runtime(s) unavailable: {', '.join(missing)}")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="shortcut-portability-",
                                                dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with & [glob]"
        self.home.mkdir()
        self.config = self.root / "config with & [glob]"
        self.config.mkdir()
        self.dev = self.root / "dev with & [glob]"
        self.dev.mkdir()
        self.helpers = self.root / "helpers"
        self.helpers.mkdir()
        for name, source in (("env.sh", ENV), ("aliases.sh", ALIASES),
                             ("tmux-sessionizer", SESSIONIZER),
                             ("tailscale-ssh", TAILSCALE)):
            destination = self.helpers / name
            shutil.copy2(source, destination)
            setattr(self, name.replace(".", "_").replace("-", "_"), destination)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.fzf_path = self.bin / "fzf"
        for name in ("bash", "find", "sort", "basename", "tr"):
            path = shutil.which(name)
            if not path:
                raise RuntimeError(f"required command unavailable: {name}")
            (self.bin / name).symlink_to(path)
        self.log = self.root / "calls"
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "LC_ALL": "C", "CALL_LOG": str(self.log),
                    "DOTFILES_CONFIG_DIR": str(self.config),
                    "DOTFILES_DEV_DIR": str(self.dev)}
        self.stub("tmux", 'printf "tmux\\n" >>"$CALL_LOG"\n'
                  'printf "<%s>\\n" "$@" >>"$CALL_LOG"\n'
                  'if [[ "$1" == has-session ]]; then exit 1; fi\n')
        self.stub("tailscale", 'printf "tailscale\\n" >>"$CALL_LOG"\n'
                  'printf "<%s>\\n" "$@" >>"$CALL_LOG"\n')

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + body)
        path.chmod(0o755)

    def run_helper(self, path, *args, env=None):
        return subprocess.run([str(path), *args], env=env or self.env,
                              capture_output=True, text=True, timeout=10, cwd=self.root)

    def test_env_exports_portable_defaults_and_overrides(self):
        cases = (
                ({}, self.home / ".config", self.home / "_dev"),
                ({"XDG_CONFIG_HOME": str(self.config)}, self.config, self.home / "_dev"),
                ({"DOTFILES_CONFIG_DIR": str(self.config),
                  "DOTFILES_DEV_DIR": str(self.dev)}, self.config, self.dev))
        for overrides, expected_config, expected_dev in cases:
            for name, shell in SHELLS:
                with self.subTest(overrides=overrides, shell=name):
                    env = {"HOME": str(self.home), "PATH": str(self.bin),
                           "CHILD_SHELL": shell, **overrides}
                    code = (f'. "{self.env_sh}"; . "{self.env_sh}"; '
                            '"$CHILD_SHELL" -c \'printf "%s\\n%s\\n" '
                            '"$DOTFILES_CONFIG_DIR" "$DOTFILES_DEV_DIR"\'')
                    result = subprocess.run([shell, "-c", code], env=env,
                                            capture_output=True, text=True, check=True, timeout=10,
                                            cwd=self.root)
                    self.assertEqual(result.stdout.splitlines(),
                                     [str(expected_config), str(expected_dev)])

    def test_dev_alias_changes_directory_and_balena_is_one_deferred_command(self):
        balena = self.root / "etcher path with & [glob]"
        # Executable path itself includes metacharacters and whitespace.
        balena.write_text('#!/bin/bash\nprintf "balena\\n" >>"$CALL_LOG"\n'
                          'printf "argc:%s\\n" "$#" >>"$CALL_LOG"\n'
                          'for arg in "$@"; do printf "<%s>\\n" "$arg" >>"$CALL_LOG"; done\n')
        balena.chmod(0o755)
        alias_calls = self.root / "alias-calls.sh"
        alias_calls.write_text('dev\nprintf "PWD:%s\\n" "$PWD"\nbalena\n')
        env = {**self.env, "BALENA_ETCHER": str(balena),
               "ALIASES_FILE": str(self.aliases_sh),
               "ALIAS_CALL_SCRIPT": str(alias_calls)}
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.log.unlink(missing_ok=True)
                expand_aliases = "shopt -s expand_aliases\n" if name == "bash" else ""
                dot = "source" if name == "zsh" else "."
                script = (expand_aliases + f'{dot} "$ALIASES_FILE"; '
                          f'{dot} "$ALIAS_CALL_SCRIPT"')
                command = [shell, "-f", "-c", script] if name == "zsh" else [shell, "-c", script]
                result = subprocess.run(command, env=env, capture_output=True, text=True,
                                        check=True, timeout=10)
                self.assertIn(f"PWD:{self.dev}", result.stdout)
                self.assertEqual(self.log.read_text().splitlines(), ["balena", "argc:0"])
                # The fixture logs argument count and every slot independently.
                listing = expand_aliases + f'{dot} "$ALIASES_FILE"; alias balena; alias dev'
                alias_listing = subprocess.run(
                    [shell, "-f", "-c", listing] if name == "zsh" else [shell, "-c", listing],
                    env=env, capture_output=True, text=True, check=True, timeout=10).stdout
                self.assertIn('"${BALENA_ETCHER:-balenaEtcher.appImage}"', alias_listing)
                self.assertIn('${DOTFILES_DEV_DIR:-$HOME/_dev}', alias_listing)

    def test_sessionizer_explicit_directory_needs_no_fzf_and_rejects_invalid_before_tmux(self):
        self.log.unlink(missing_ok=True)
        self.fzf_path.unlink(missing_ok=True)
        result = self.run_helper(self.tmux_sessionizer, str(self.dev))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("fzf", self.log.read_text().splitlines())
        calls = self.log.read_text().splitlines()
        create = calls.index("tmux") + 1
        create = calls.index("tmux", create) + 1
        self.assertEqual(calls[create:create + 5],
                         ["<new-session>", "<-ds>", "<dev with & [glob]>", "<-c>",
                          f"<{self.dev}>"])
        before = self.log.read_text()
        result = self.run_helper(self.tmux_sessionizer, str(self.root / "missing"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not exist", result.stderr)
        self.assertEqual(self.log.read_text(), before)

    def test_sessionizer_interactive_roots_use_custom_configured_directories(self):
        self.log.unlink(missing_ok=True)
        (self.config / "project").mkdir()
        (self.dev / "project").mkdir()
        env = {**self.env, "SELECTED": str(self.config / "project"),
               "INPUT_LOG": str(self.root / "fzf-input")}
        self.stub("fzf", 'printf "fzf\\n" >>"$CALL_LOG"\n'
                  'printf "<%s>\\n" "$@" >>"$CALL_LOG"\n'
                  'while IFS= read -r line; do printf "%s\\n" "$line" >>"$INPUT_LOG"; done\n'
                  'printf "%s\\n" "$SELECTED"\n')
        result = self.run_helper(self.tmux_sessionizer, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertEqual(calls[0], "fzf")
        choices = (self.root / "fzf-input").read_text().splitlines()
        self.assertIn(str(self.config / "project"), choices)
        self.assertIn(str(self.dev / "project"), choices)
        first_tmux = calls.index("tmux")
        new_session = calls.index("tmux", first_tmux + 1) + 1
        self.assertEqual(calls[new_session:new_session + 5],
                         ["<new-session>", "<-ds>", "<project>", "<-c>",
                          f"<{self.config / 'project'}>"])

    def test_sessionizer_fzf_cancel_is_success_without_tmux_calls(self):
        self.stub("fzf", 'exit 1\n')
        result = self.run_helper(self.tmux_sessionizer)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.log.exists())

    def test_sessionizer_discovery_failure_does_not_open_fzf_or_tmux(self):
        # Remove the fixture symlink before writing a replacement tool: never
        # write through a link to a real host executable.
        (self.bin / "find").unlink()
        self.stub("find", 'exit 3\n')
        self.stub("fzf", 'printf "fzf-called\\n" >>"$CALL_LOG"\nexit 1\n')
        result = self.run_helper(self.tmux_sessionizer)
        self.assertEqual(result.returncode, 3)
        self.assertIn("could not discover", result.stderr)
        self.assertFalse(self.log.exists())

    def test_sessionizer_fzf_errors_propagate_without_tmux_calls(self):
        self.stub("fzf", 'while IFS= read -r line; do :; done\nexit 2\n')
        result = self.run_helper(self.tmux_sessionizer)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.log.exists())

    def test_sessionizer_missing_fzf_only_fails_for_interactive_selection(self):
        self.fzf_path.unlink(missing_ok=True)
        result = self.run_helper(self.tmux_sessionizer)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fzf is not installed", result.stderr)
        self.assertFalse(self.log.exists())

    def test_tailscale_requires_host_before_call_and_preserves_forwards(self):
        env_host = {**self.env, "TAILSCALE_SSH_HOST": "100.64.0.1"}
        for args, env in (((), self.env), (("",), env_host), (("-bad",), self.env),
                          (("host", "ignored"), self.env), (("--help", "extra"), self.env)):
            with self.subTest(args=args):
                result = self.run_helper(self.tailscale_ssh, *args, env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.log.exists())

        result = self.run_helper(self.tailscale_ssh, "--help")
        self.assertEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

        invocations = ((("user@host.example",), env_host, "user@host.example"),
                       ((), env_host, "100.64.0.1"))
        for args, env, host in invocations:
            result = self.run_helper(self.tailscale_ssh, *args, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = ["tailscale", "<ssh>", f"<{host}>"]
            expected.extend(f"<{arg}>" for arg in (
                "-L", "3000:localhost:3000", "-L", "3001:localhost:3001",
                "-L", "5900:localhost:5900", "-L", "5555:localhost:5555",
                "-L", "8080:localhost:8080"))
            self.assertEqual(self.log.read_text().splitlines(), expected)
            self.log.unlink()

    def test_tmux_shortcut_commands_defer_and_quote_configured_paths(self):
        config = (ROOT / "config/tmux/tmux.conf").read_text()
        self.assertIn("bind -r C run-shell", config)
        self.assertIn("bind -r D run-shell", config)
        expected = {
            "C": ('"$HOME/.local/bin/tmux-sessionizer" "${DOTFILES_CONFIG_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}}"',
                  (({"DOTFILES_CONFIG_DIR": str(self.config)}, str(self.config)),
                   ({"XDG_CONFIG_HOME": str(self.config)}, str(self.config)),
                   ({}, str(self.home / ".config")))),
            "D": ('"$HOME/.local/bin/tmux-sessionizer" "${DOTFILES_DEV_DIR:-$HOME/_dev}"',
                  (({"DOTFILES_DEV_DIR": str(self.dev)}, str(self.dev)),
                   ({}, str(self.home / "_dev")))),
        }
        for key, (command, env_cases) in expected.items():
            line = next(line for line in config.splitlines()
                        if line.strip().startswith(f"bind -r {key} run-shell"))
            match = re.search(r"run-shell '([^']+)'", line)
            self.assertIsNotNone(match, line)
            actual_command = match.group(1)
            self.assertEqual(actual_command, command)
            self.assertNotIn("~/", line)
            # Simulate tmux's deferred shell command and preserve argument boundaries.
            self.stub("sessionizer-capture", 'printf "sessionizer\\n" >>"$CALL_LOG"\n'
                      'printf "<%s>\\n" "$@" >>"$CALL_LOG"\n')
            shell_command = actual_command.replace('"$HOME/.local/bin/tmux-sessionizer"',
                                                   f'"{self.bin / "sessionizer-capture"}"')
            for overrides, expected_path in env_cases:
                self.log.unlink(missing_ok=True)
                env = {"HOME": str(self.home), "PATH": str(self.bin),
                       "CALL_LOG": str(self.log), **overrides}
                subprocess.run(["bash", "-c", shell_command], env=env, check=True,
                               capture_output=True, text=True, timeout=10)
                self.assertEqual(self.log.read_text().splitlines(),
                                 ["sessionizer", f"<{expected_path}>"])


if __name__ == "__main__":
    unittest.main()

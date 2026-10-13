"""Regression tests for portable interactive shell startup behavior."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ALIASES = ROOT / "scripts/.config/shell/aliases.sh"
BASHRC = ROOT / "bash/.config/bash/bashrc"
ZSHRC = ROOT / "zsh/.zshrc"
ZSH_AUTOCOMPLETE_README = ROOT / "zsh/.config/zsh/zsh-autocomplete/README.md"
ENV_HELPER = ROOT / "scripts/.config/shell/env.sh"


class ShellStartupTests(unittest.TestCase):
    def setUp(self):
        temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        self.temp = tempfile.TemporaryDirectory(prefix="shell-startup-", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def test_executable_aliases_quote_home_at_invocation_time(self):
        local_bin = self.home / ".local/bin"
        local_bin.mkdir(parents=True)
        calls = self.root / "calls"
        for name in ("nvim-launcher", "tmux-sessionizer"):
            executable = local_bin / name
            executable.write_text(
                "#!/bin/sh\nprintf '%s:%s\\n' " + name + " \"$*\" >>\"$CALL_LOG\"\n")
            executable.chmod(0o755)

        env = {"HOME": str(self.home), "PATH": str(self.bin), "CALL_LOG": str(calls)}
        script = ("shopt -s expand_aliases; "
                  f'source "{ALIASES}"; '
                  "eval 'nvim-ai README.md'; eval 'sesh'")
        result = subprocess.run([shutil.which("bash"), "-c", script], env=env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("No such file or directory", result.stderr)
        self.assertEqual(calls.read_text().splitlines(),
                         ["nvim-launcher:README.md", "tmux-sessionizer:"])

    def test_noninteractive_bashrc_does_not_emit_bind_warnings(self):
        config = self.root / "config"
        (config / "shell").mkdir(parents=True)
        (config / "bash").mkdir()
        shutil.copy2(ENV_HELPER, config / "shell/env.sh")
        (config / "bash/aliases.sh").write_text("")
        env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(config),
               "PATH": str(self.bin)}
        result = subprocess.run([shutil.which("bash"), "-c", f'source "{BASHRC}"'],
                                env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("bind: warning: line editing not enabled", result.stderr)

    def test_zsh_completion_and_precmd_registration_are_idempotent_by_source(self):
        # The full rc depends on host plugins and theme files; assert the exact
        # startup wiring instead of sourcing those external dependencies.
        source = ZSHRC.read_text()
        self.assertIn("Remove any calls to `compinit` from your `.zshrc` file",
                      ZSH_AUTOCOMPLETE_README.read_text())
        self.assertIn('fpath=("${XDG_CONFIG_HOME}/zsh/completions"', source)
        self.assertNotRegex(source, r"(?m)^\s*(?:autoload[^\n]*compinit|compinit)\b")
        self.assertIn("_p10k_theme_sync\n(( ${precmd_functions[(Ie)_p10k_theme_sync]} )) || ",
                      source)
        self.assertIn("precmd_functions+=(_p10k_theme_sync)", source)
        registration = next(line.strip() for line in source.splitlines()
                            if "precmd_functions[(Ie)_p10k_theme_sync]" in line)
        result = subprocess.run(
            [shutil.which("zsh"), "-f", "-c",
             f"precmd_functions=(); {registration}; {registration}; "
             "print -r -- ${(j:,:)precmd_functions}"],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "_p10k_theme_sync")


if __name__ == "__main__":
    unittest.main()

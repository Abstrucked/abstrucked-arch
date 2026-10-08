"""Hermetic checks for the shared shell defaults and Stow layout."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
ENV_HELPER = ROOT / "scripts/.config/shell/env.sh"
ALIASES_HELPER = ROOT / "scripts/.config/shell/aliases.sh"
ALIASES = (
    "yrs", "graph", "vue", "balena", "dev", "scrot1", "scrot2", "sesh",
    "nvim-ai", "opencode-ai", "create-app", "pass-insert", "batt", "balanced",
    "perf", "checkmode", "_omen",
)
SHELLS = [("sh", "/bin/sh"), ("bash", shutil.which("bash")),
          ("zsh", shutil.which("zsh"))]


class ShellDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        missing = [name for name, shell in SHELLS if not shell]
        if missing:
            raise RuntimeError(f"required shell runtime(s) unavailable: {', '.join(missing)}")

    def setUp(self):
        temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
        self.temp = tempfile.TemporaryDirectory(prefix="shell-defaults-", dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with & [glob]"
        self.home.mkdir()
        self.config = self.root / "config root with & [glob]"
        (self.config / "shell").mkdir(parents=True)
        shutil.copy2(ENV_HELPER, self.config / "shell/env.sh")
        shutil.copy2(ALIASES_HELPER, self.config / "shell/aliases.sh")

    def run_shell(self, shell, script, env, *args):
        return subprocess.run([shell, "-c", script, "shell-test", *args], env=env,
                              capture_output=True, text=True, check=True, timeout=10)

    def test_environment_defaults_are_idempotent_in_posix_shells(self):
        managed = [str(self.home / ".local/bin"), str(self.home / "n/bin"),
                   str(self.home / ".asdf/shims"), str(self.home / ".local/share/pnpm")]
        prior = ["", "/custom/one", managed[1], "/custom with & [glob]", "", managed[0]]
        original_path = ":".join(prior)
        expected = ":".join(managed + ["", "/custom/one", "/custom with & [glob]", ""])
        for name, shell in SHELLS:
            if not shell:
                continue
            with self.subTest(shell=name):
                env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
                       "PATH": original_path}
                script = (
                    '. "$XDG_CONFIG_HOME/shell/env.sh"; '
                    'set -f; before=$-; first=$PATH; positional="$1|$2"; '
                    '. "$XDG_CONFIG_HOME/shell/env.sh"; '
                    'printf "%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n" '
                    '"$PATH" "$EDITOR|$VISUAL" '
                    '"$N_PREFIX|$ASDF_DATA_DIR|$PNPM_HOME|$THEME_BG_DIR" '
                    '"$first" "$before" "$-" "$positional"'
                )
                output = self.run_shell(shell, script, env, "arg one", "arg&two").stdout.splitlines()
                self.assertEqual(output[0], expected)
                self.assertEqual(output[1], "nvim|nvim")
                self.assertEqual(output[2], f"{self.home}/n|{self.home}/.asdf|{self.home}/.local/share/pnpm|{self.home}/.backgrounds")
                self.assertEqual(output[3], expected)
                self.assertEqual(output[5], output[4])
                self.assertEqual(output[6], "arg one|arg&two")

    def test_overlapping_managed_prefixes_are_deduplicated_in_order(self):
        overlap = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
                   "PATH": ":/keep::/keep:", "N_PREFIX": str(self.home / ".local"),
                   "ASDF_DATA_DIR": str(self.home / ".local"),
                   "PNPM_HOME": str(self.home / ".local/bin")}
        expected = ":".join([str(self.home / ".local/bin"),
                             str(self.home / ".local/shims"), "", "/keep", "", "/keep", ""])
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                output = self.run_shell(shell,
                    '. "$XDG_CONFIG_HOME/shell/env.sh"; first=$PATH; '
                    '. "$XDG_CONFIG_HOME/shell/env.sh"; printf "%s\\n%s\\n" "$first" "$PATH"',
                    overlap).stdout.splitlines()
                self.assertEqual(output, [expected, expected])

    def test_custom_defaults_and_alias_wrappers(self):
        custom = self.root / "runtime with & [glob]"
        custom_env = {"HOME": str(self.home), "XDG_CONFIG_HOME": str(self.config),
                      "PATH": "/usr/bin", "EDITOR": "vim-custom", "VISUAL": "view-custom",
                      "N_PREFIX": str(custom / "node"), "ASDF_DATA_DIR": str(custom / "asdf"),
                      "PNPM_HOME": str(custom / "pnpm"), "THEME_BG_DIR": str(custom / "backgrounds")}
        for name, shell in SHELLS:
            if not shell:
                continue
            with self.subTest(shell=name):
                result = self.run_shell(shell,
                    '. "$XDG_CONFIG_HOME/shell/env.sh"; printf "%s\\n%s\\n" "$EDITOR|$VISUAL" "$PATH"',
                    custom_env).stdout.splitlines()
                self.assertEqual(result[0], "vim-custom|view-custom")
                self.assertEqual(result[1], ":".join([
                    str(self.home / ".local/bin"), str(custom / "node/bin"),
                    str(custom / "asdf/shims"), str(custom / "pnpm"), "/usr/bin"]))

                wrapper = self.root / ("bash-wrapper.sh" if name == "bash" else "zsh-wrapper.zsh")
                source = (ROOT / ("bash/.config/bash/aliases.sh" if name == "bash"
                                  else "zsh/.config/zsh/aliases.zsh")).read_text()
                wrapper.write_text(source)
                with wrapper.open("a") as wrapper_file:
                    wrapper_file.write("\nalias yrs='custom-override'\n")
                alias_commands = ("shopt -s expand_aliases; " if name == "bash" else "")
                alias_commands += f'. "{wrapper}"; alias'
                aliases = self.run_shell(shell, alias_commands, custom_env).stdout
                self.assertIn("create-app=", aliases)
                for alias_name in ALIASES:
                    self.assertIn(f"{alias_name}=", aliases)
                self.assertIn(str(self.home / ".local/bin/nvim-launcher"), aliases)
                self.assertIn("custom-override", aliases)

    def test_real_stow_layout_has_helpers_only_under_config(self):
        stow = shutil.which("stow")
        if not stow:
            self.skipTest("GNU Stow is unavailable")
        target = self.root / "stow home"
        target.mkdir()
        subprocess.run([stow, "--no-folding", "-d", str(ROOT), "-t", str(target),
                        "scripts", "bash", "zsh", "xsession"], check=True,
                       capture_output=True, text=True)
        self.assertTrue((target / ".config/shell/env.sh").is_symlink())
        self.assertTrue((target / ".config/shell/aliases.sh").is_symlink())
        self.assertTrue((target / ".config/bash/aliases.sh").is_symlink())
        self.assertTrue((target / ".config/zsh/aliases.zsh").is_symlink())
        self.assertTrue((target / ".xprofile").is_symlink())
        self.assertFalse((target / "env.sh").exists())

    def test_tmux_default_shell_is_one_static_setting(self):
        config = (ROOT / "config/tmux/tmux.conf").read_text()
        lines = [line.strip() for line in config.splitlines()
                 if line.strip().startswith("set-option -g default-shell")]
        self.assertEqual(lines, ['set-option -g default-shell "/usr/bin/bash"'])

    def test_shell_configs_do_not_export_legacy_theme(self):
        for config in (ROOT / "bash/.config/bash/bashrc", ROOT / "zsh/.zshrc"):
            with self.subTest(config=config):
                self.assertNotRegex(config.read_text(), r"(?m)^\s*export\s+THEME=")


if __name__ == "__main__":
    unittest.main()

"""Regression tests for required generation in the Stow install step."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INSTALL_STEPS = ROOT / "lib/install-steps.sh"


def install_stow_source():
    source = INSTALL_STEPS.read_text()
    start = source.index("install_stow() {")
    end = source.index("\ninstall_theme() {", start)
    return source[start:end]


class InstallStowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="install-stow-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.dotfiles = self.root / "dotfiles"
        self.dotfiles.mkdir()
        (self.dotfiles / "hyprland").mkdir()

    def run_step(self, failure="", selected_shell=""):
        if selected_shell:
            (self.dotfiles / selected_shell).mkdir(exist_ok=True)
            (self.home / f".{selected_shell}rc").write_text("original config\n")
        prelude = r'''
progress_step() { :; }
require_command() { :; }
log_info() { :; }
log_warn() { printf 'WARN:%s\n' "$*"; }
log_error() { printf 'ERROR:%s\n' "$*"; }
die() { printf 'DIE:%s\n' "$*"; exit 1; }
progress_complete() { printf 'COMPLETE:%s\n' "$*"; }
execute() {
    if [[ "$1" == */pluginctl ]]; then step=pluginctl; else
        if [[ "$1" == */themectl ]]; then step=themectl; else step=gtk-bookmarks; fi
    fi
    if [[ "$step" == "$STEP_FAIL" ]]; then return 23; fi
    return 0
}
backup_item() { BACKUPS+=("$1.backup"); }
restore_backup() { printf 'RESTORE:%s:%s\n' "$1" "$2"; }
stow_config_package() { return 0; }
safe_symlink() { return 0; }
command_exists() { return 0; }
BACKUPS=()
'''
        config = "\n".join((
            f"DRY_RUN=false",
            f"WINDOW_MANAGER=hyprland",
            f"SELECTED_SHELL={shlex.quote(selected_shell)}",
            f"HOME={shlex.quote(str(self.home))}",
            f"DOTFILES_DIR={shlex.quote(str(self.dotfiles))}",
            "COMMON_STOW_PACKAGES=()",
            f"STEP_FAIL={shlex.quote(failure)}",
        ))
        script = "\n".join((prelude, config, install_stow_source(), "install_stow"))
        return subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, timeout=10
        )

    def assert_required_failure(self, step):
        result = self.run_step(failure=step)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DIE:", result.stdout)
        self.assertNotIn("COMPLETE:done", result.stdout)

    def test_plugin_generation_failure_is_fatal(self):
        self.assert_required_failure("pluginctl")

    def test_theme_generation_failure_is_fatal(self):
        self.assert_required_failure("themectl")

    def test_bookmarks_failure_is_warning_and_step_completes(self):
        result = self.run_step(failure="gtk-bookmarks")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WARN:gtk-bookmarks failed; run it manually", result.stdout)
        self.assertIn("COMPLETE:done", result.stdout)

    def test_all_generation_succeeds_and_step_completes(self):
        result = self.run_step()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("COMPLETE:done", result.stdout)

    def test_required_failure_restores_shell_backup(self):
        result = self.run_step(failure="pluginctl", selected_shell="bash")
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"RESTORE:{self.home}/.bashrc.backup:{self.home}/.bashrc", result.stdout)
        self.assertNotIn("COMPLETE:done", result.stdout)


if __name__ == "__main__":
    unittest.main()

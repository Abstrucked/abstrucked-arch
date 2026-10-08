"""Run with: python3 -B -m pytest tests/test_installers.py -q.

Only copied installers execute. All fixture state lives in a private temporary
directory; PATH is an allowlist, not the host PATH with a few commands prepended.
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMMON_STOW_PACKAGES = (
    "ssh", "alacritty", "btop", "nvim", "pcmanfm", "scripts", "ghossty", "gnupg",
    "xsession",
)
STOW_PACKAGES = ("awesome", "picom", *COMMON_STOW_PACKAGES)
STOW_PACKAGES_BY_WM = {
    "awesome": STOW_PACKAGES,
    "both": ("awesome", "hyprland", "picom", *COMMON_STOW_PACKAGES),
    "hyprland": ("hyprland", *COMMON_STOW_PACKAGES),
}
MOCK = r'''
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ["COMMAND_LOG"], "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == os.environ.get("FAIL_COMMAND"):
    sys.exit(42)
if name == "sudo" and len(sys.argv) > 1:
    args = sys.argv[1:]
    if args in (["-n", "-v"], ["-v"]):
        if os.environ.get("FAIL_SUDO_VALIDATION") == "1":
            sys.exit(1)
        sys.exit(0)
    if args[0] == "-n":
        args = args[1:]
    if args[0] == "-v":
        sys.exit(0)
    os.execvp(args[0], args)
if name not in ("git", "yay", "stow", "nvim", "chsh", "zsh", "systemctl"):
    sys.exit("Unexpected external command: " + name)
'''


def snapshot(root):
    """Include hidden files, empty directories, modes and link text; never follow links."""
    result = {}
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        content = (os.readlink(path) if path.is_symlink() else
                   None if path.is_dir() else path.read_bytes())
        result[str(path.relative_to(root))] = (stat.st_mode, content)
    return result


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="installer-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.repo = self.base / "repo with spaces"
        self.bin = self.base / "bin"
        self.tmp = self.base / "tmp"
        for path in (self.home, self.repo, self.bin, self.tmp):
            path.mkdir()
        for name in ("install.sh", "bootstrap-configs.sh", "copy-awesome-config.sh", "install-lazyvim.sh",
                     "install-node-manager.sh", "install-yay.sh", "packages.list",
                     "packages-awesome.list", "packages-hyprland.list"):
            shutil.copyfile(ROOT / name, self.repo / name)
        shutil.copytree(ROOT / "lib", self.repo / "lib", symlinks=True)
        for name in (*STOW_PACKAGES, "hyprland", "zsh", "bash", "backgrounds"):
            (self.repo / name).mkdir()
        helper = self.repo / "scripts/.local/bin/tmux-save-workspace"
        helper.parent.mkdir(parents=True)
        helper.write_text("#!/bin/sh\nexit 0\n")
        helper.chmod(0o755)
        # Data fixtures avoid copying personal configs or links out of the repository.
        self.write(self.repo / "config/tmux/tmux.conf", 'set -g default-shell "/bin/zsh"\n')
        self.write(self.repo / "config/tmux/theme.conf", "# tracked icon theme\n")
        self.write(self.repo / "themes/theme.sh", "# Not sourced during dry runs.\n")
        self.write(self.repo / "nvim/.config/nvim/init.lua", "-- managed fixture\n")
        (self.repo / "nvim/.config/nvim/lua").mkdir()
        for name in ("bash", "basename", "dirname", "date", "mkdir", "mktemp",
                     "cp", "mv", "rm", "rmdir", "ln", "readlink", "realpath",
                     "find", "grep", "sed", "cat", "sleep", "id"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, f"Required test utility: {name}")
            (self.bin / name).symlink_to(executable)
        for name in ("git", "yay", "stow", "nvim", "pacman", "curl", "sudo",
                      "systemctl", "makepkg", "make", "wget", "chsh", "zsh"):
            self.write(self.bin / name, f"#!{sys.executable}\n" + MOCK)
            (self.bin / name).chmod(0o755)
        self.write(self.bin / "getent", '#!/bin/bash\n'
                   '[[ "${FAIL_GETENT:-0}" == 0 ]] || exit 2\n'
                   'printf "%s:x:1000:1000::%s:%s\\n" "$2" "$HOME" "${ACCOUNT_SHELL:-/usr/bin/zsh}"\n')
        (self.bin / "getent").chmod(0o755)
        self.log = self.base / "commands.jsonl"
        # Do not inherit BASH_ENV, exported functions, XDG paths or manager settings.
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin), "TMPDIR": str(self.tmp),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_CACHE_HOME": str(self.home / ".cache"),
            "XDG_STATE_HOME": str(self.home / ".local/state"),
            "COMMAND_LOG": str(self.log), "LC_ALL": "C", "TERM": "dumb",
        }

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_script(self, script="install.sh", args=(), input="", code=None):
        result = subprocess.run(
            [str(self.bin / "bash"), str(self.repo / script), *args],
            cwd=self.repo, env=self.env, input=input, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20,
        )
        result.stdout = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", result.stdout)
        if code is not None:
            self.assertEqual(result.returncode, code, result.stdout)
        return result

    def library(self, body, code=0):
        self.write(self.repo / "test-library.sh", "set -euo pipefail\n"
                   'source ./lib/cleanup.sh\nsetup_cleanup_trap\n' + body + "\n")
        return self.run_script("test-library.sh", code=code)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def seed_home(self):
        for name in (".bashrc", ".zshrc", ".tmux.conf", ".backgrounds/old",
                     ".config/tmux/theme.conf", ".config/alacritty/alacritty.toml"):
            self.write(self.home / name, "existing " + name + "\n")
        (self.home / "dangling").symlink_to("missing")

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertNotIn("Installation Complete!", result.stdout)
        self.assertNotIn("Post-Installation Instructions", result.stdout)

    def test_main_dry_run_backgrounds_tmux_preserves_home(self):
        self.seed_home()
        before = snapshot(self.home)
        result = self.run_script(args=("--dry-run", "-y", "--only", "backgrounds",
                                       "--only", "tmux"), code=0)
        self.assertIn(f"Would link {self.home}/.backgrounds", result.stdout)
        self.assertIn("Would link tmux config and theme", result.stdout)
        self.assertIn("Installation Complete!", result.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.calls(), [])

    def test_defaults_dry_run_missing_stow_plans_packages(self):
        (self.bin / "stow").unlink()
        self.seed_home()
        before = snapshot(self.home)
        result = self.run_script(args=("--dry-run", "-y"), code=0)
        packages = [pkg for pkg in (self.repo / "packages.list").read_text().splitlines()
                    if pkg and not pkg.startswith("#")]
        self.assertIn(f"[DRY RUN] yay -S --needed --noconfirm --sudoflags=-n -- {' '.join(packages)}", result.stdout)
        self.assertIn(f"[DRY RUN] stow --no-folding -d {self.repo} -t {self.home} zsh", result.stdout)
        self.assertIn("Would link tmux config and theme", result.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.calls(), [])

    def test_stow_missing_without_packages_rejected(self):
        (self.bin / "stow").unlink()
        result = self.run_script(args=("--dry-run", "-y", "--only", "stow"))
        self.assert_failed(result)
        self.assertIn("stow requires stow installed or packages selected", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_malformed_skip_does_not_consume_dry_run(self):
        before = snapshot(self.home)
        result = self.run_script(args=("--skip", "--dry-run", "-y"))
        self.assert_failed(result)
        self.assertIn("--skip requires a step name", result.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.calls(), [])

    def test_stow_skip_shell_preserves_rc_and_uses_repo_argument(self):
        self.seed_home()
        before = snapshot(self.home)
        args = ["-y", "--skip", "shell"]
        for component in ("yay", "packages", "node", "theme", "backgrounds", "tmux", "lazyvim"):
            args.extend(("--skip", component))
        self.run_script(args=args, code=0)
        self.assertEqual(self.calls(), [
            *[["stow", "--no-folding", "-d", str(self.repo), "-t", str(self.home), pkg]
              for pkg in STOW_PACKAGES],
        ])
        self.assertEqual(snapshot(self.home), before)

    def test_window_manager_controls_stow_packages(self):
        for mode, expected_packages in STOW_PACKAGES_BY_WM.items():
            with self.subTest(mode=mode):
                self.log.write_text("")
                result = self.run_script(
                    args=("-y", "--only", "stow", "--skip", "shell", "--wm", mode),
                    code=0,
                )
                self.assertIn(f"Selected window manager", result.stdout)
                self.assertEqual(self.calls(), [
                    *[["stow", "--no-folding", "-d", str(self.repo), "-t", str(self.home), pkg]
                      for pkg in expected_packages],
                ])

    def test_window_manager_controls_package_manifests(self):
        manifests = {
            "awesome": ("packages.list", "packages-awesome.list"),
            "both": ("packages.list", "packages-awesome.list", "packages-hyprland.list"),
            "hyprland": ("packages.list", "packages-hyprland.list"),
        }
        for mode, files in manifests.items():
            with self.subTest(mode=mode):
                self.log.write_text("")
                self.run_script(args=("-y", "--only", "packages", "--wm", mode), code=0)
                expected = []
                for filename in files:
                    expected.extend(line for line in (self.repo / filename).read_text().splitlines()
                                    if line and not line.startswith("#") and line not in expected)
                self.assertEqual(
                    [call for call in self.calls() if call[0] == "yay"],
                    [["yay", "-S", "--needed", "--noconfirm", "--sudoflags=-n", "--", *expected]],
                )

    def test_package_manifests_are_batched_and_deduplicated(self):
        self.write(self.repo / "packages.list", "alpha\nshared\n")
        self.write(self.repo / "packages-awesome.list", "shared\nbeta\n")
        self.run_script(args=("-y", "--only", "packages", "--wm", "awesome"), code=0)
        self.assertEqual([call for call in self.calls() if call[0] == "yay"], [
            ["yay", "-S", "--needed", "--noconfirm", "--sudoflags=-n", "--", "alpha", "shared", "beta"],
        ])

    def test_selected_steps_follow_policy_order_not_cli_order(self):
        result = self.run_script(
            args=("-y", "--only", "stow", "--only", "packages", "--skip", "shell"),
            code=0,
        )
        calls = self.calls()
        self.assertEqual(calls[0][0], "sudo")  # privilege preflight
        self.assertEqual(calls[1][0], "yay")   # packages precede Stow
        self.assertEqual([call[0] for call in calls[2:]], ["stow"] * len(STOW_PACKAGES))
        self.assertLess(result.stdout.index("Installing system packages"),
                        result.stdout.index("Setting up symlinks with GNU Stow"))

    def test_unsafe_backup_root_fails_before_any_install_or_authentication(self):
        alias = self.base / "checkout-backup-alias"
        alias.symlink_to(self.repo, target_is_directory=True)
        for root in ("relative-root", str(self.repo / "backups"), str(alias / "backups")):
            for dry_run in (False, True):
                with self.subTest(root=root, dry_run=dry_run):
                    self.env["DOTFILES_BACKUP_ROOT"] = root
                    before_home, before_repo = snapshot(self.home), snapshot(self.repo)
                    args = ("-y", "--only", "packages")
                    if dry_run:
                        args += ("--dry-run",)
                    result = self.run_script(args=args)
                    self.assert_failed(result)
                    self.assertIn("backup root", result.stdout)
                    self.assertEqual(self.calls(), [])
                    self.assertEqual(snapshot(self.home), before_home)
                    self.assertEqual(snapshot(self.repo), before_repo)

    def test_all_selected_steps_follow_policy_order_in_dry_run(self):
        terminal_config = self.home / ".config/alacritty/alacritty.toml"
        self.write(terminal_config, 'shell = "/old/zsh"\n')
        before = snapshot(self.home)
        # Reverse menu and execution order to prove the dispatcher controls it.
        args = ["--dry-run", "-y"]
        args.extend(item for step in (
            "yubikey", "lazyvim", "shell", "tmux", "backgrounds", "theme",
            "stow", "node", "packages", "yay",
        ) for item in ("--only", step))
        result = self.run_script(args=args, code=0)
        markers = (
            "yay already installed",
            "Installing system packages",
            "Installing Node.js version manager",
            "Installing YubiKey tools",
            "Setting up symlinks with GNU Stow",
            "Applying system theme",
            "Setting up desktop backgrounds",
            "Setting up Tmux configuration",
            "[dry-run] Would update " + str(terminal_config),
            "[dry-run] Would set the login shell to zsh",
            "Installing LazyVim Neovim distribution",
        )
        positions = [result.stdout.index(marker) for marker in markers]
        self.assertEqual(positions, sorted(positions), result.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.calls(), [])

    def test_failed_earlier_phase_stops_later_selected_phase(self):
        self.env["FAIL_COMMAND"] = "yay"
        result = self.run_script(
            args=("-y", "--only", "stow", "--only", "packages", "--skip", "shell"),
        )
        self.assert_failed(result)
        self.assertEqual([call[0] for call in self.calls()], ["sudo", "yay"])
        self.assertNotIn("Setting up symlinks with GNU Stow", result.stdout)

    def test_step_function_temporaries_do_not_escape_the_function(self):
        self.write(self.repo / "test-step-locals.sh", '''#!/bin/bash
set -euo pipefail
source ./lib/logging.sh
source ./lib/validation.sh
source ./lib/args.sh
source ./lib/components.sh
source ./lib/install-steps.sh
DOTFILES_DIR=$PWD
WINDOW_MANAGER=awesome
yay_install_args=(-S --needed)
sudo_args=()
pkg=sentinel package=sentinel packages_file=sentinel
install_packages
[[ "$pkg" == sentinel && "$package" == sentinel && "$packages_file" == sentinel ]]
[[ ! -v seen_packages && ! -v packages && ! -v package_files ]]
''')
        self.run_script("test-step-locals.sh", code=0)

    def test_interactive_package_install_keeps_yay_confirmation(self):
        self.run_script(args=("--only", "packages", "--wm", "awesome"), input="d\n\n", code=0)
        self.assertEqual([call for call in self.calls() if call[0] == "yay"], [
            ["yay", "-S", "--needed", "--", *[
                line for line in (self.repo / "packages.list").read_text().splitlines()
                if line and not line.startswith("#")
            ], *[
                line for line in (self.repo / "packages-awesome.list").read_text().splitlines()
                if line and not line.startswith("#")
            ]],
        ])

    def test_yubikey_unattended_flags_and_systemctl_sudo_are_noninteractive_only(self):
        self.run_script(args=("-y", "--only", "yubikey"), code=0)
        self.assertEqual(self.calls(), [
            ["sudo", "-n", "-v"],
            ["yay", "-S", "--needed", "--noconfirm", "--sudoflags=-n", "--",
             "yubikey-manager", "yubico-authenticator-bin", "pcsclite", "ccid"],
            ["sudo", "-n", "systemctl", "enable", "pcscd.service"],
            ["systemctl", "enable", "pcscd.service"],
        ])

    def test_interactive_yubikey_keeps_confirmation_and_sudo_prompt(self):
        self.run_script(args=("--only", "yubikey"), input="10\n\n", code=0)
        self.assertEqual(self.calls(), [
            ["sudo", "-v"],
            ["yay", "-S", "--needed", "--", "yubikey-manager", "yubico-authenticator-bin",
             "pcsclite", "ccid"],
            ["sudo", "systemctl", "enable", "pcscd.service"],
            ["systemctl", "enable", "pcscd.service"],
        ])

    def test_sudo_preflight_failure_stops_before_package_or_stow_actions(self):
        self.env["FAIL_SUDO_VALIDATION"] = "1"
        result = self.run_script(args=("-y", "--only", "packages", "--only", "stow"))
        self.assert_failed(result)
        self.assertEqual(self.calls(), [["sudo", "-n", "-v"]])

    def test_invalid_later_package_manifest_prevents_any_yay_call(self):
        self.write(self.repo / "packages.list", "valid-first\n")
        self.write(self.repo / "packages-hyprland.list", "--invalid\n")
        result = self.run_script(args=("-y", "--only", "packages", "--wm", "hyprland"))
        self.assert_failed(result)
        self.assertIn("Invalid packages", result.stdout)
        self.assertEqual([call for call in self.calls() if call[0] == "yay"], [])

    def test_empty_package_manifests_skip_yay(self):
        self.write(self.repo / "packages.list", "# base packages\n\n")
        self.write(self.repo / "packages-awesome.list", "# comments only\n")
        self.run_script(args=("-y", "--only", "packages", "--wm", "awesome"), code=0)
        self.assertEqual([call for call in self.calls() if call[0] == "yay"], [])

    def test_invalid_window_manager_is_rejected_before_work(self):
        result = self.run_script(args=("-y", "--only", "stow", "--wm", "sway"))
        self.assert_failed(result)
        self.assertIn("Unknown window manager: sway", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_gum_ui_selects_components_window_manager_shell_and_confirmation(self):
        self.write(self.bin / "gum", r'''#!/bin/bash
if [[ "$1" == "choose" ]]; then
    if [[ "$*" == *"Select components"* ]]; then
        printf '%s\n' '2. packages' '4. stow'
    elif [[ "$*" == *"Select window manager"* ]]; then
        printf '%s\n' 'Hyprland'
    else
        printf '%s\n' 'bash - Starship prompt, bash-completion'
    fi
elif [[ "$1" == "confirm" ]]; then
    exit 0
else
    exit 1
fi
''')
        (self.bin / "gum").chmod(0o755)
        self.write(self.repo / "test-gum.sh", '''#!/bin/bash
set -euo pipefail
source ./lib/components.sh
UI_MODE=gum
select_components
[[ ${#SELECTED_COMPONENTS[@]} -eq 2 ]]
select_window_manager
select_shell
confirm_installation
printf 'WM=%s SHELL=%s\\n' "$WINDOW_MANAGER" "$SELECTED_SHELL"
''')
        result = self.run_script("test-gum.sh", code=0)
        self.assertIn("WM=hyprland SHELL=bash", result.stdout)

    LOGIN_SHELL_SCRIPT = """#!/bin/bash
set -euo pipefail
source ./lib/components.sh
set_login_shell "${1:-bash}"
"""

    def login_shell_run(self, shell="bash", code=0):
        self.env["USER"] = "tester"
        self.write(self.repo / "test-login-shell.sh", self.LOGIN_SHELL_SCRIPT)
        return self.run_script("test-login-shell.sh", args=(shell,), code=code)

    def test_login_shell_is_changed_to_the_selected_shell(self):
        # command -v resolves to the stub, which links to the real interpreter.
        expected = str((self.bin / "bash").resolve())
        self.login_shell_run()
        self.assertEqual(self.calls(), [
            ["sudo", "chsh", "-s", expected, "tester"],
            ["chsh", "-s", expected, "tester"],
        ])

    def test_terminal_shell_noop_does_not_back_up_or_replace_symlink(self):
        resolved = str((self.bin / "zsh").resolve())
        source = self.repo / "terminal config/alacritty.toml"
        self.write(source, f'shell = "{resolved}"\n# keep this comment\n')
        target = self.home / ".config/alacritty/alacritty.toml"
        target.parent.mkdir(parents=True)
        target.symlink_to(source)
        tmux_source = self.repo / "terminal config/tmux.conf"
        self.write(tmux_source,
                   f'  set -g default-shell "{resolved}" # keep comment\n'
                   f'    set-option -g default-shell "{resolved}"\n'
                   '# set -g default-shell "/ignored/zsh"\n')
        tmux = self.home / ".config/tmux/tmux.conf"
        tmux.parent.mkdir(parents=True)
        tmux.symlink_to(tmux_source)
        tmux_missing = self.home / ".config/tmux/no-shell.conf"
        self.write(tmux_missing, "set -g status on\n# no shell setting\n")
        before = snapshot(self.home)
        self.run_script(args=("-y", "--only", "stow", "--only", "shell"), code=0)
        self.assertEqual(snapshot(self.home), before)
        self.assertTrue(target.is_symlink())
        self.assertTrue(tmux.is_symlink())
        self.assertFalse((self.home / ".dotfiles-backups").exists())

        tmux_source.write_text("set -g status on\n# no configured shell\n")
        before_missing_setting = snapshot(self.home)
        self.run_script(args=("-y", "--only", "stow", "--only", "shell"), code=0)
        self.assertEqual(snapshot(self.home), before_missing_setting)
        self.assertFalse((self.home / ".dotfiles-backups").exists())

    def test_terminal_shell_edit_backs_up_and_preserves_symlink_and_content(self):
        shell_dir = self.home / "shell bins"
        shell = shell_dir / "zsh"
        self.write(shell, "#!/bin/sh\nexit 0\n")
        shell.chmod(0o755)
        self.env["PATH"] = f"{shell_dir}:{self.bin}"
        resolved = str(shell.resolve())
        source = self.repo / "terminal config/alacritty.toml"
        self.write(source, 'shell = "/old/zsh"\n[window]\nopacity = 0.9\n')
        target = self.home / ".config/alacritty/alacritty.toml"
        target.parent.mkdir(parents=True)
        target.symlink_to(source)
        target_link = os.readlink(target)
        target_inode = target.lstat().st_ino
        tmux_source = self.repo / "terminal config/tmux.conf"
        self.write(tmux_source,
                   f'  set-option -g default-shell "{resolved}" # keep first match\n'
                   '    set -g default-shell "/old/zsh" # preserve this comment\n'
                   '    set -sg default-shell "/old/bash"\n'
                   '    set -s -g default-shell "/old/ksh"\n'
                   '  # set -g default-shell "/commented/out"\n'
                   'set -g status on\n')
        tmux = self.home / ".config/tmux/tmux.conf"
        tmux.parent.mkdir(parents=True)
        tmux.symlink_to(tmux_source)
        tmux_link = os.readlink(tmux)
        tmux_inode = tmux.lstat().st_ino

        self.run_script(args=("-y", "--only", "stow", "--only", "shell"), code=0)

        self.assertTrue(target.is_symlink())
        self.assertEqual(os.readlink(target), target_link)
        self.assertEqual(target.lstat().st_ino, target_inode)
        self.assertEqual(source.read_text(),
                         f'shell = "{resolved}"\n[window]\nopacity = 0.9\n')
        self.assertTrue(tmux.is_symlink())
        self.assertEqual(os.readlink(tmux), tmux_link)
        self.assertEqual(tmux.lstat().st_ino, tmux_inode)
        self.assertEqual(tmux_source.read_text(),
                         f'  set-option -g default-shell "{resolved}" # keep first match\n'
                         f'    set -g default-shell "{resolved}" # preserve this comment\n'
                         f'    set -sg default-shell "{resolved}"\n'
                         f'    set -s -g default-shell "{resolved}"\n'
                         '  # set -g default-shell "/commented/out"\n'
                         'set -g status on\n')
        backups = list((self.home / ".dotfiles-backups").rglob("alacritty.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), 'shell = "/old/zsh"\n[window]\nopacity = 0.9\n')
        tmux_backups = list((self.home / ".dotfiles-backups").rglob("tmux.conf"))
        self.assertEqual(len(tmux_backups), 1)
        self.assertIn('set -g default-shell "/old/zsh" # preserve this comment',
                      tmux_backups[0].read_text())

    def test_terminal_shell_backup_failure_prevents_symlink_target_edits(self):
        shell_dir = self.home / "shell bins"
        shell = shell_dir / "zsh"
        self.write(shell, "#!/bin/sh\nexit 0\n")
        shell.chmod(0o755)
        self.env["PATH"] = f"{shell_dir}:{self.bin}"
        self.env["FAIL_COMMAND"] = "cp"
        (self.bin / "cp").unlink()
        self.write(self.bin / "cp", f"#!{sys.executable}\n" + MOCK)
        (self.bin / "cp").chmod(0o755)
        resolved = str(shell.resolve())

        source = self.repo / "terminal config/alacritty.toml"
        original = f'shell = "/old/zsh"\n# preserve\n'
        self.write(source, original)
        target = self.home / ".config/alacritty/alacritty.toml"
        target.parent.mkdir(parents=True)
        target.symlink_to(source)
        link_text = os.readlink(target)
        link_inode = target.lstat().st_ino
        source_inode = source.stat().st_ino

        result = self.run_script(args=("-y", "--only", "stow", "--only", "shell"))

        self.assert_failed(result)
        self.assertIn("Failed to back up", result.stdout)
        self.assertEqual(os.readlink(target), link_text)
        self.assertEqual(target.lstat().st_ino, link_inode)
        self.assertEqual(source.stat().st_ino, source_inode)
        self.assertEqual(source.read_text(), original)

    def test_empty_terminal_shell_settings_are_updated(self):
        shell_dir = self.home / "shell bins"
        shell = shell_dir / "zsh"
        self.write(shell, "#!/bin/sh\nexit 0\n")
        shell.chmod(0o755)
        self.env["PATH"] = f"{shell_dir}:{self.bin}"
        resolved = str(shell.resolve())

        alacritty = self.home / ".config/alacritty/alacritty.toml"
        self.write(alacritty, 'shell = ""\n')
        tmux = self.home / ".config/tmux/tmux.conf"
        self.write(tmux, f'set -g default-shell "{resolved}"\n'
                   '  set-option -g default-shell "" # trailing empty value\n')

        self.run_script(args=("-y", "--only", "stow", "--only", "shell"), code=0)

        self.assertEqual(alacritty.read_text(), f'shell = "{resolved}"\n')
        self.assertEqual(tmux.read_text(),
                         f'set -g default-shell "{resolved}"\n'
                         f'  set-option -g default-shell "{resolved}" # trailing empty value\n')

    def test_terminal_shell_dry_run_does_not_require_selected_shell(self):
        config = self.home / ".config/alacritty/alacritty.toml"
        self.write(config, 'shell = "/old/zsh"\n')
        before = snapshot(self.home)
        (self.bin / "zsh").unlink()
        result = self.run_script(args=("--dry-run", "-y", "--only", "stow", "--only", "shell"), code=0)
        self.assertIn("Would update", result.stdout)
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(self.calls(), [])

    def test_login_shell_is_left_alone_when_already_current(self):
        self.env["ACCOUNT_SHELL"] = str((self.bin / "bash").resolve())
        self.env["SHELL"] = "/usr/bin/zsh"
        result = self.login_shell_run()
        self.assertEqual(self.calls(), [])
        self.assertIn("Login shell is already", result.stdout)

    def test_stale_shell_environment_does_not_skip_account_update(self):
        self.env["SHELL"] = str((self.bin / "bash").resolve())
        self.env["ACCOUNT_SHELL"] = "/usr/bin/zsh"
        self.login_shell_run()
        self.assertEqual(self.calls()[0][0:2], ["sudo", "chsh"])

    def test_account_lookup_failure_does_not_change_shell(self):
        self.env["FAIL_GETENT"] = "1"
        result = self.login_shell_run(code=1)
        self.assertIn("Could not query the login shell", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_login_shell_dry_run_changes_nothing(self):
        self.env["DRY_RUN"] = "true"
        self.write(self.repo / "test-login-shell.sh",
                   "#!/bin/bash\nset -euo pipefail\nsource ./lib/components.sh\n"
                   'DRY_RUN=true\nset_login_shell bash\n')
        result = self.run_script("test-login-shell.sh", code=0)
        self.assertEqual(self.calls(), [])
        self.assertIn("Would set the login shell", result.stdout)

    def test_login_shell_missing_interpreter_is_reported(self):
        result = self.login_shell_run(shell="fish", code=1)
        self.assertIn("Selected shell is not installed", result.stdout)
        self.assertEqual(self.calls(), [])

    def test_stow_failure_is_fatal(self):
        self.env["FAIL_COMMAND"] = "stow"
        self.seed_home()
        before = snapshot(self.home)
        result = self.run_script(args=("-y", "--only", "stow", "--skip", "shell"))
        self.assert_failed(result)
        self.assertIn("Failed to stow awesome", result.stdout)
        self.assertEqual([call[0] for call in self.calls()], ["stow"])
        self.assertEqual(snapshot(self.home), before)

    def test_package_failure_is_fatal(self):
        self.env["FAIL_COMMAND"] = "yay"
        result = self.run_script(args=("-y", "--only", "packages", "--only", "stow"))
        self.assert_failed(result)
        self.assertIn("Failed to install packages", result.stdout)
        packages = []
        for filename in ("packages.list", "packages-awesome.list"):
            packages.extend(line for line in (self.repo / filename).read_text().splitlines()
                            if line and not line.startswith("#") and line not in packages)
        self.assertEqual(self.calls(), [
            ["sudo", "-n", "-v"],
            ["yay", "-S", "--needed", "--noconfirm", "--sudoflags=-n", "--", *packages],
        ])
        self.assertEqual(snapshot(self.home), {})

    def test_invalid_package_without_final_newline_is_rejected(self):
        self.write(self.repo / "packages.list", "--invalid")
        result = self.run_script(args=("-y", "--only", "packages"))
        self.assert_failed(result)
        self.assertIn("Invalid packages", result.stdout)
        self.assertEqual(self.calls(), [["sudo", "-n", "-v"]])

    def test_base_stow_failure_preserves_selected_shell_rc(self):
        self.env["FAIL_COMMAND"] = "stow"
        self.write(self.home / ".zshrc", "keep original shell\n")
        before = snapshot(self.home)
        result = self.run_script(args=("-y", "--only", "stow", "--only", "shell"))
        self.assert_failed(result)
        self.assertEqual(snapshot(self.home), before)

    def test_shell_stow_failure_restores_original_rc(self):
        self.write(self.home / ".zshrc", "keep original shell\n")
        self.write(self.bin / "stow", f"#!{sys.executable}\nimport sys\nsys.exit(1 if sys.argv[-1] == 'zsh' else 0)\n")
        result = self.run_script(args=("-y", "--only", "stow", "--only", "shell"))
        self.assert_failed(result)
        self.assertEqual((self.home / ".zshrc").read_text(), "keep original shell\n")

    def test_tmux_theme_links_tracked_theme_without_overwriting_existing_target(self):
        original = self.home / "theme-source"
        self.write(original, "original theme\n")
        theme = self.home / ".config/tmux/theme.conf"
        theme.parent.mkdir(parents=True)
        theme.symlink_to(original)
        self.write(self.home / ".tmux/plugins/tpm/tpm", "#!/bin/sh\nexit 0\n")
        (self.home / ".tmux/plugins/tpm/tpm").chmod(0o755)
        self.write(self.home / ".tmux/plugins/tpm/bin/install_plugins", "#!/bin/sh\nexit 0\n")
        (self.home / ".tmux/plugins/tpm/bin/install_plugins").chmod(0o755)
        self.run_script(args=("-y", "--only", "tmux"), code=0)
        self.assertTrue(theme.is_symlink())
        self.assertEqual(theme.resolve(), self.repo / "config/tmux/theme.conf")
        self.assertEqual(theme.read_text(), "# tracked icon theme\n")
        backups = list((self.home / ".dotfiles-backups").rglob("theme.conf"))
        self.assertEqual(len(backups), 1)
        self.assertTrue(backups[0].is_symlink())
        self.assertEqual(backups[0].resolve(), original)
        self.assertEqual(original.read_text(), "original theme\n")
        helper = self.home / ".local/bin/tmux-save-workspace"
        self.assertTrue(helper.is_symlink())
        self.assertEqual(helper.resolve(), self.repo / "scripts/.local/bin/tmux-save-workspace")
        self.assertFalse(os.path.isabs(os.readlink(helper)))

    def test_tmux_existing_regular_theme_is_backed_up(self):
        theme = self.home / ".config/tmux/theme.conf"
        self.write(theme, "my own theme\n")
        self.write(self.home / ".tmux/plugins/tpm/tpm", "#!/bin/sh\nexit 0\n")
        (self.home / ".tmux/plugins/tpm/tpm").chmod(0o755)
        self.run_script(args=("-y", "--only", "tmux"), code=0)
        self.assertEqual(theme.resolve(), self.repo / "config/tmux/theme.conf")
        backups = list((self.home / ".dotfiles-backups").rglob("theme.conf"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(backups[0].is_symlink())
        self.assertEqual(backups[0].read_text(), "my own theme\n")

    def test_bootstrap_scans_standalone_secrets_and_does_not_whitelist_file(self):
        self.write(self.home / ".zshrc", 'export SAFE_API_KEY=$(pass service)\nexport PASSWORD="literal-secret"\n')
        before = snapshot(self.repo)
        result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=0)
        self.assertIn("potential sensitive content", result.stdout)
        self.assertIn("Copied: 0", result.stdout)
        self.assertEqual(snapshot(self.repo), before)

    def test_bootstrap_rejects_dotted_json_yaml_and_embedded_literal_secrets(self):
        samples = (
            'export API_KEY="example.secret.value"\n',
            '{"api_key": "example-secret"}\n',
            'api_key: "example-secret"\n',
            '"api_key" = "example-secret"\n',
            'export API_KEY="literal$REFERENCE"\n',
            "export API_KEY='$REFERENCE'\n",
            '{"api_key": "$REFERENCE", "token": "literal"}\n',
        )
        for text in samples:
            with self.subTest(text=text):
                self.write(self.home / ".config/nvim/settings", text)
                before = snapshot(self.repo)
                result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=0)
                self.assertIn("potential sensitive content", result.stdout)
                self.assertEqual(snapshot(self.repo), before)

    def test_bootstrap_keeps_reference_only_configuration_importable(self):
        self.write(self.home / ".zshrc", 'export API_KEY="$REFERENCE"\n'
                   'export TOKEN=$(pass service)\n'
                   '# PASSWORD="not an assignment"\n')
        result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=0)
        self.assertIn("Copied: 1", result.stdout)

    def test_partial_destination_removal_keeps_complete_backup(self):
        dest = self.repo / "btop/.config/btop"
        self.write(dest / "removed-first", "first original\n")
        self.write(dest / "remaining", "second original\n")
        self.write(self.home / ".config/btop/replacement", "new\n")
        real_rm = shutil.which("rm")
        (self.bin / "rm").unlink()
        self.write(self.bin / "rm", f"#!{sys.executable}\n"
                   "import os, sys\nfrom pathlib import Path\n"
                   f"if sys.argv[-1] == {str(dest)!r}:\n"
                   "    (Path(sys.argv[-1]) / 'removed-first').unlink()\n"
                   "    sys.exit(42)\n"
                   f"os.execv({real_rm!r}, [{real_rm!r}, *sys.argv[1:]])\n")
        (self.bin / "rm").chmod(0o755)
        result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=1)
        self.assertIn("original retained at", result.stdout)
        backups = list((self.home / ".dotfiles-backups").glob("bootstrap.*/original"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "removed-first").read_text(), "first original\n")
        self.assertEqual((backups[0] / "remaining").read_text(), "second original\n")
        self.assertEqual(list(self.repo.rglob(".bootstrap-stage.*")), [])

    def test_awesome_copy_rejects_sensitive_symlink_target(self):
        source = self.home / ".config/awesome"
        source.mkdir(parents=True)
        self.write(self.home / "private", "-----BEGIN OPENSSH PRIVATE KEY-----\n")
        (source / "innocent-name").symlink_to(self.home / "private")
        before = snapshot(self.repo)
        result = self.run_script("copy-awesome-config.sh")
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Refusing to import", result.stdout)
        self.assertEqual(snapshot(self.repo), before)

    def test_bootstrap_no_quit_and_eof_do_not_copy(self):
        self.write(self.home / ".zshrc", "new config\n")
        self.write(self.repo / "zsh/.zshrc", "original config\n")
        for response, message in (("no\n", "Skipped: 1"),
                                  ("q\n", "Operation cancelled by user"),
                                  ("", "End of input; cancelled")):
            with self.subTest(response=response):
                before = snapshot(self.repo)
                home_before = snapshot(self.home)
                result = self.run_script("bootstrap-configs.sh", input=response, code=0)
                self.assertIn(message, result.stdout)
                self.assertIn("Copied: 0", result.stdout)
                self.assertEqual(snapshot(self.repo), before)
                self.assertEqual(snapshot(self.home), home_before)

    def test_bootstrap_exact_item_backups_not_siblings(self):
        pairs = ((".zshrc", "zsh/.zshrc"),
                 (".local/bin/screenshot", "scripts/.local/bin/screenshot"))
        for source, dest in pairs:
            self.write(self.home / source, "new\n")
            self.write(self.repo / dest, "old\n")
            self.write((self.repo / dest).parent / "unrelated", "keep\n")
        self.write(self.home / ".config/btop/new", "new directory\n")
        self.write(self.repo / "btop/.config/btop/old", "old directory\n")
        self.write(self.repo / "btop/.config/unrelated", "keep\n")
        result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=0)
        self.assertIn("Copied: 3", result.stdout)
        for _, dest in pairs:
            path = self.repo / dest
            self.assertEqual(path.read_text(), "new\n")
            self.assertFalse(list(path.parent.glob(path.name + ".backup.*")))
            self.assertEqual((path.parent / "unrelated").read_text(), "keep\n")
        path = self.repo / "btop/.config/btop"
        self.assertEqual([p.name for p in path.iterdir()], ["new"])
        backups = list((self.home / ".dotfiles-backups").glob("bootstrap.*/original"))
        self.assertEqual(len(backups), 3)
        self.assertEqual(sorted(p.read_text() for p in backups if p.is_file()), ["old\n", "old\n"])
        directory_backup = next(p for p in backups if p.is_dir())
        self.assertEqual((directory_backup / "old").read_text(), "old directory\n")
        self.assertFalse((directory_backup / "unrelated").exists())
        self.assertEqual((path.parent / "unrelated").read_text(), "keep\n")
        self.assertEqual(list(self.repo.rglob(".bootstrap-stage.*")), [])

    def test_bootstrap_already_stowed_skips_without_prompt_or_backup(self):
        self.write(self.repo / "zsh/.zshrc", "managed\n")
        (self.home / ".zshrc").symlink_to(self.repo / "zsh/.zshrc")
        before = snapshot(self.repo)
        result = self.run_script("bootstrap-configs.sh", code=0)
        self.assertIn("Already stowed:", result.stdout)
        self.assertIn("Skipped: 1", result.stdout)
        self.assertNotIn("[Y/n/s(kip)/q(uit)]", result.stdout)
        self.assertEqual(snapshot(self.repo), before)
        self.assertTrue((self.home / ".zshrc").is_symlink())

    def test_library_failed_backup_prevents_removal_and_replacement(self):
        self.write(self.home / "file", "keep file\n")
        self.write(self.home / "directory/child", "keep directory\n")
        self.write(self.home / "target", "target\n")
        (self.home / "link").symlink_to("missing")
        before = snapshot(self.home)
        # Fail the real backup copy, not a replacement of backup_item itself.
        (self.bin / "cp").unlink()
        self.write(self.bin / "cp", f"#!{sys.executable}\n" + MOCK)
        (self.bin / "cp").chmod(0o755)
        self.env["FAIL_COMMAND"] = "cp"
        self.library('''
if safe_remove_file "$HOME/file"; then exit 10; fi
if safe_remove_dir "$HOME/directory"; then exit 11; fi
if safe_symlink "$HOME/target" "$HOME/link"; then exit 12; fi
if restore_backup "$HOME/target" "$HOME/file"; then exit 13; fi
''')
        after = {key: value for key, value in snapshot(self.home).items()
                 if not key.startswith(".dotfiles-backups")}
        self.assertEqual(after, before)
        self.assertEqual([call[0] for call in self.calls()], ["cp"] * 4)

    def test_library_temp_cleanup_on_success_and_failure(self):
        for status in (0, 17):
            with self.subTest(status=status):
                self.library('''
create_temp_dir regression first
create_temp_dir regression second
[[ -d "$first" && -d "$second" && "$first" != "$second" ]]
[[ ${#TEMP_DIRS[@]} -eq 2 ]]
printf '%s\\n' "$first" "$second" > "$HOME/temp-paths"
''' + f"exit {status}", code=status)
                paths = (self.home / "temp-paths").read_text().splitlines()
                self.assertEqual(len(paths), 2)
                for path in paths:
                    self.assertEqual(Path(path).parent, self.tmp)
                    self.assertFalse(Path(path).exists())
                self.assertEqual(list(self.tmp.iterdir()), [])

    def test_library_backup_collisions_preserve_versions_and_paths(self):
        self.write(self.home / "one/config", "first\n")
        self.write(self.home / "two/config", "second\n")
        (self.home / "dangling").symlink_to("missing")
        self.library('''
backup_item "$HOME/one/config"
printf 'updated\\n' > "$HOME/one/config"
backup_item "$HOME/one/../one/config"
backup_item "$HOME/two/config"
backup_item "$HOME/dangling"
[[ ${#BACKUPS[@]} -eq 4 ]]
printf '%s\\n' "${BACKUPS[@]}" > "$HOME/backup-paths"
''')
        paths = [Path(p) for p in (self.home / "backup-paths").read_text().splitlines()]
        self.assertEqual(len(set(paths)), 4)
        self.assertEqual([p.read_text() for p in paths[:3]], ["first\n", "updated\n", "second\n"])
        for path, suffix in zip(paths, ("one/config", "one/config", "two/config", "dangling")):
            self.assertTrue(path.is_relative_to(self.home / ".dotfiles-backups"))
            self.assertTrue(str(path).endswith(str(self.home / suffix)))
        self.assertTrue(paths[3].is_symlink())
        self.assertEqual(os.readlink(paths[3]), "missing")

    def test_managed_lazyvim_preserves_link_and_only_syncs(self):
        (self.home / ".config").mkdir()
        (self.home / ".config/nvim").symlink_to(self.repo / "nvim/.config/nvim")
        before = snapshot(self.home)
        repo_before = snapshot(self.repo)
        result = self.run_script(args=("-y", "--only", "lazyvim"), code=0)
        self.assertIn("Preserving repository-managed configuration", result.stdout)
        calls = self.calls()
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0:2], ["nvim", "--headless"])
        self.assertEqual(calls[0][-1], "+qa")
        self.assertEqual(snapshot(self.home), before)
        self.assertEqual(snapshot(self.repo), repo_before)


if __name__ == "__main__":
    unittest.main()

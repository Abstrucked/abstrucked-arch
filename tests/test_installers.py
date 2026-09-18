"""Run with: python3 -B -m unittest discover -s tests -v.

Only copied installers execute. All fixture state lives under /tmp/opencode;
PATH is an allowlist, not the host PATH with a few commands prepended.
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
STOW_PACKAGES = (
    "awesome", "ssh", "alacritty", "btop", "nvim", "picom", "pcmanfm",
    "scripts", "ghossty", "gnupg",
)
MOCK = r'''
import json, os, sys
name = os.path.basename(sys.argv[0])
with open(os.environ["COMMAND_LOG"], "a") as log:
    log.write(json.dumps([name, *sys.argv[1:]]) + "\n")
if name == os.environ.get("FAIL_COMMAND"):
    sys.exit(42)
if name not in ("git", "yay", "stow", "nvim"):
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
        self.temp = tempfile.TemporaryDirectory(prefix="installer-tests-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.repo = self.base / "repo with spaces"
        self.bin = self.base / "bin"
        self.tmp = self.base / "tmp"
        for path in (self.home, self.repo, self.bin, self.tmp):
            path.mkdir()
        for name in ("install.sh", "bootstrap-configs.sh", "copy-awesome-config.sh", "install-lazyvim.sh",
                     "install-node-manager.sh", "install-yay.sh", "packages.list"):
            shutil.copyfile(ROOT / name, self.repo / name)
        shutil.copytree(ROOT / "lib", self.repo / "lib", symlinks=True)
        for name in (*STOW_PACKAGES, "zsh", "bash", "backgrounds"):
            (self.repo / name).mkdir()
        # Data fixtures avoid copying personal configs or links out of the repository.
        self.write(self.repo / "config/tmux/tmux.conf", 'set -g default-shell "/bin/zsh"\n')
        self.write(self.repo / "themes/theme.sh", "# Not sourced during dry runs.\n")
        self.write(self.repo / "nvim/.config/nvim/init.lua", "-- managed fixture\n")
        (self.repo / "nvim/.config/nvim/lua").mkdir()
        for name in ("bash", "basename", "dirname", "date", "mkdir", "mktemp",
                     "cp", "mv", "rm", "rmdir", "ln", "readlink", "realpath",
                     "find", "grep", "sed", "cat", "sleep"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, f"Required test utility: {name}")
            (self.bin / name).symlink_to(executable)
        for name in ("git", "yay", "stow", "nvim", "pacman", "curl", "sudo",
                     "systemctl", "makepkg", "make", "wget", "chsh"):
            self.write(self.bin / name, f"#!{sys.executable}\n" + MOCK)
            (self.bin / name).chmod(0o755)
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
        for pkg in (self.repo / "packages.list").read_text().splitlines():
            if pkg and not pkg.startswith("#"):
                self.assertIn(f"[DRY RUN] yay -S --needed --noconfirm -- {pkg}", result.stdout)
        self.assertIn(f"[DRY RUN] stow -d {self.repo} -t {self.home} zsh", result.stdout)
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
            ["git", "-C", str(self.repo), "submodule", "update", "--init", "--recursive"],
            *[["stow", "-d", str(self.repo), "-t", str(self.home), pkg]
              for pkg in STOW_PACKAGES],
        ])
        self.assertEqual(snapshot(self.home), before)

    def test_stow_failure_is_fatal(self):
        self.env["FAIL_COMMAND"] = "stow"
        self.seed_home()
        before = snapshot(self.home)
        result = self.run_script(args=("-y", "--only", "stow", "--skip", "shell"))
        self.assert_failed(result)
        self.assertIn("Failed to stow awesome", result.stdout)
        self.assertEqual([call[0] for call in self.calls()], ["git", "stow"])
        self.assertEqual(snapshot(self.home), before)

    def test_package_failure_is_fatal(self):
        self.env["FAIL_COMMAND"] = "yay"
        result = self.run_script(args=("-y", "--only", "packages", "--only", "stow"))
        self.assert_failed(result)
        self.assertIn("Failed to install: stow", result.stdout)
        self.assertEqual(self.calls(), [["yay", "-S", "--needed", "--noconfirm", "--", "stow"]])
        self.assertEqual(snapshot(self.home), {})

    def test_invalid_package_without_final_newline_is_rejected(self):
        self.write(self.repo / "packages.list", "--invalid")
        result = self.run_script(args=("-y", "--only", "packages"))
        self.assert_failed(result)
        self.assertIn("Invalid packages", result.stdout)
        self.assertEqual(self.calls(), [])

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

    def test_tmux_theme_symlink_target_has_content_backup(self):
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
        backups = list((self.home / ".dotfiles-backups").rglob("theme-source"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(backups[0].is_symlink())
        self.assertEqual(backups[0].read_text(), "original theme\n")
        self.assertIn("status-style", original.read_text())

    def test_bootstrap_scans_standalone_secrets_and_does_not_whitelist_file(self):
        self.write(self.home / ".zshrc", 'export SAFE_API_KEY=$(pass service)\nexport PASSWORD="literal-secret"\n')
        before = snapshot(self.repo)
        result = self.run_script("bootstrap-configs.sh", args=("--yes",), code=0)
        self.assertIn("potential sensitive content", result.stdout)
        self.assertIn("Copied: 0", result.stdout)
        self.assertEqual(snapshot(self.repo), before)

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

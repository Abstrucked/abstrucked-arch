"""Backup path policies execute copied code against synthetic files only."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


def snapshot(root):
    return {
        str(path.relative_to(root)): (
            path.lstat().st_mode,
            os.readlink(path) if path.is_symlink() else
            None if path.is_dir() else path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
    }


class BackupPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="backup-path-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "checkout with spaces"
        self.home = self.root / "home"
        self.bin = self.root / "bin"
        for directory in (self.repo, self.home, self.bin):
            directory.mkdir()
        (self.repo / "lib").mkdir()
        for name in ("logging.sh", "cleanup.sh", "backup-paths.sh"):
            shutil.copy2(ROOT / "lib" / name, self.repo / "lib" / name)
        shutil.copy2(ROOT / "bootstrap-configs.sh", self.repo / "bootstrap-configs.sh")
        (self.repo / "install.sh").write_text("# synthetic bootstrap prerequisite\n")
        (self.repo / "packages.list").write_text("# synthetic manifest\n")
        for name in ("bash", "dirname", "realpath", "mkdir", "mktemp", "cp", "rm",
                     "rmdir", "mv", "find", "grep", "head", "wc", "basename"):
            tool = shutil.which(name)
            self.assertIsNotNone(tool, name)
            (self.bin / name).symlink_to(tool)
        self.source = self.home / "original"
        self.source.write_text("synthetic original data\n")
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "LC_ALL": "C"}

    def library(self, body, success=True):
        result = subprocess.run(
            [str(self.bin / "bash"), "-c", 'set -euo pipefail\n'
             'source ./lib/cleanup.sh\n' + body],
            cwd=self.repo, env=self.env, text=True, capture_output=True, timeout=10,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def bootstrap(self, *args, success=True):
        result = subprocess.run(
            [str(self.bin / "bash"), str(self.repo / "bootstrap-configs.sh"), *args],
            cwd=self.root, env=self.env, text=True, capture_output=True, timeout=10,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_relative_and_checkout_roots_fail_before_writes_including_dry_run(self):
        unsafe = ("relative-backups", str(self.repo), str(self.repo / "backups"),
                  str(self.root / "checkout with spaces" / ".." / self.repo.name / "backups"))
        for root in unsafe:
            for dry_run in ("true", "false"):
                with self.subTest(root=root, dry_run=dry_run):
                    self.env.update(DOTFILES_BACKUP_ROOT=root, DRY_RUN=dry_run)
                    before = snapshot(self.root)
                    result = self.library('backup_item "$HOME/original"', success=False)
                    self.assertIn("backup root", result.stderr)
                    self.assertEqual(snapshot(self.root), before)

    def test_symlinked_checkout_root_and_ancestors_are_rejected(self):
        link = self.root / "checkout-alias"
        link.symlink_to(self.repo, target_is_directory=True)
        external = self.root / "external"
        external.mkdir()
        (self.repo / "external-backups").symlink_to(external, target_is_directory=True)
        roots = (link / "backups", self.repo / "external-backups")
        for root in roots:
            with self.subTest(root=root):
                self.env["DOTFILES_BACKUP_ROOT"] = str(root)
                before = snapshot(self.root)
                self.library('backup_item "$HOME/original"', success=False)
                self.assertEqual(snapshot(self.root), before)

    def test_external_root_honors_override_and_explicit_argument_precedence(self):
        override = self.root / "backups & spaces"
        explicit = self.root / "explicit backups"
        self.env.update(DOTFILES_BACKUP_ROOT=str(override), EXPLICIT_ROOT=str(explicit))
        result = self.library('backup_item "$HOME/original"\n'
                              'backup_item "$HOME/original" "$EXPLICIT_ROOT"\n'
                              'printf "%s\\n" "${BACKUPS[@]}"')
        paths = [Path(line) for line in result.stdout.splitlines()]
        self.assertEqual(len(paths), 2)
        self.assertTrue(paths[0].is_relative_to(override))
        self.assertTrue(paths[1].is_relative_to(explicit))
        for path in paths:
            self.assertEqual(path.read_text(), self.source.read_text())
        self.assertFalse((self.home / ".dotfiles-backups").exists())

    def test_external_symlink_is_canonicalized_without_modifying_it(self):
        external = self.root / "outside"
        external.mkdir()
        alias = self.root / "backup-alias"
        alias.symlink_to(external, target_is_directory=True)
        self.env["DOTFILES_BACKUP_ROOT"] = str(alias / "not-created-yet")
        result = self.library('backup_item "$HOME/original"\nprintf "%s\\n" "${BACKUPS[@]}"')
        backup = Path(result.stdout.strip())
        self.assertTrue(backup.is_relative_to(external))
        self.assertEqual(backup.read_text(), self.source.read_text())
        self.assertTrue(alias.is_symlink())

    def test_repository_sibling_is_not_mistaken_for_descendant(self):
        sibling = self.root / (self.repo.name + "-backups")
        self.env["DOTFILES_BACKUP_ROOT"] = str(sibling)
        self.library('backup_item "$HOME/original"')
        self.assertTrue(sibling.is_dir())

    def test_directory_backup_rejects_self_inclusion_but_preserves_symlinks(self):
        directory = self.home / "data"
        directory.mkdir()
        (directory / "file").write_text("synthetic nested data\n")
        self.env["DOTFILES_BACKUP_ROOT"] = str(directory / "backups")
        before = snapshot(self.root)
        self.library('backup_item "$HOME/data"', success=False)
        self.assertEqual(snapshot(self.root), before)
        link = self.home / "data-link"
        link.symlink_to(directory, target_is_directory=True)
        result = self.library('backup_item "$HOME/data-link"\nprintf "%s\\n" "${BACKUPS[@]}"')
        backup = Path(result.stdout.strip())
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), str(directory))

    def test_missing_item_and_safe_dry_run_create_nothing(self):
        self.env["DOTFILES_BACKUP_ROOT"] = str(self.root / "no-backups")
        before = snapshot(self.root)
        self.library('backup_item "$HOME/missing"\n[[ ${#BACKUPS[@]} -eq 0 ]]')
        self.env["DRY_RUN"] = "true"
        self.library('backup_item "$HOME/original"\n[[ ${#BACKUPS[@]} -eq 0 ]]')
        self.assertEqual(snapshot(self.root), before)

    def test_root_validation_is_independent_of_current_working_directory(self):
        self.env["DOTFILES_BACKUP_ROOT"] = str(self.repo / "backups")
        self.library('cd "$HOME"\nbackup_item "$HOME/original"', success=False)
        self.assertFalse((self.repo / "backups").exists())

    def test_control_characters_in_root_are_rejected_without_creation(self):
        for suffix in ("\nextra", "\rextra"):
            with self.subTest(suffix=suffix):
                self.env["DOTFILES_BACKUP_ROOT"] = str(self.root / ("backups" + suffix))
                before = snapshot(self.root)
                self.library('backup_item "$HOME/original"', success=False)
                self.assertEqual(snapshot(self.root), before)

    def test_bootstrap_and_backup_item_share_validation_without_writes(self):
        for root in (str(self.repo / "backups"), "relative-root"):
            with self.subTest(root=root):
                self.env["DOTFILES_BACKUP_ROOT"] = root
                before = snapshot(self.root)
                result = self.bootstrap("--yes", "--dry-run", success=False)
                self.assertIn("backup root", result.stderr)
                self.assertEqual(snapshot(self.root), before)

    def test_bootstrap_uses_custom_external_root_for_exact_item(self):
        (self.home / ".config/btop").mkdir(parents=True)
        (self.home / ".config/btop/config").write_text("synthetic imported config\n")
        destination = self.repo / "btop/.config/btop"
        destination.mkdir(parents=True)
        (destination / "config").write_text("synthetic old config\n")
        backup_root = self.root / "bootstrap backups"
        self.env["DOTFILES_BACKUP_ROOT"] = str(backup_root)
        self.bootstrap("--yes")
        self.assertEqual((destination / "config").read_text(), "synthetic imported config\n")
        backups = list(backup_root.glob("bootstrap.*/original/config"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), "synthetic old config\n")
        self.assertFalse((self.home / ".dotfiles-backups").exists())


if __name__ == "__main__":
    unittest.main()

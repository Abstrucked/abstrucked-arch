"""Exercise the ghossty compatibility alias and narrowly scoped Stow migration."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
STOW = shutil.which("stow")


class GhosttyMigrationTests(unittest.TestCase):
    def setUp(self):
        if not STOW:
            self.skipTest("GNU Stow is required")
        self.temp = tempfile.TemporaryDirectory(prefix="ghostty-migration-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo with spaces"
        self.home = self.root / "home with spaces"
        self.repo.mkdir()
        self.home.mkdir()
        (self.home / ".config").mkdir()
        shutil.copytree(ROOT / "lib", self.repo / "lib")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "dirname", "readlink", "realpath", "stow"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (self.bin / name).symlink_to(executable)
        self.env = {"HOME": str(self.home), "PATH": str(self.bin), "LC_ALL": "C"}

    def config(self, directory="ghostty"):
        path = self.repo / directory / ".config/ghostty/config"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("font-size = 12\n")
        return path

    def stow(self, *args, code=0):
        result = subprocess.run(
            [STOW, *args, "-d", str(self.repo), "-t", str(self.home)],
            text=True, capture_output=True, timeout=10, env=self.env,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def install_script(self, dry_run=False):
        path = self.root / "migrate.sh"
        path.write_text(f'''#!/bin/bash
set -euo pipefail
source "{self.repo}/lib/install-steps.sh"
DOTFILES_DIR={str(self.repo)!r}
HOME={str(self.home)!r}
DRY_RUN={'true' if dry_run else 'false'}
stow_config_package ghostty
''')
        return path

    def run_script(self, dry_run=False, code=0):
        env = {**self.env, "HOME": str(self.home)}
        result = subprocess.run([str(self.bin / "bash"), str(self.install_script(dry_run))], env=env,
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def old_install_then_rename(self, no_folding=False):
        self.config("ghossty")
        args = ("--no-folding", "ghossty") if no_folding else ("ghossty",)
        self.stow(*args)
        canonical = self.repo / "ghostty"
        (self.repo / "ghossty").rename(canonical)
        (self.repo / "ghossty").symlink_to("ghostty", target_is_directory=True)
        return canonical / ".config/ghostty/config"

    def test_fresh_canonical_stow_works_with_alias_package(self):
        config = self.config()
        (self.repo / "ghossty").symlink_to("ghostty", target_is_directory=True)
        self.stow("--no-folding", "ghostty")
        link = self.home / ".config/ghostty/config"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), config)

    def test_legacy_folded_link_survives_rename_then_migrates(self):
        config = self.old_install_then_rename()
        folded = self.home / ".config/ghostty"
        self.assertTrue(folded.is_symlink())
        self.assertEqual((folded / "config").read_text(), "font-size = 12\n")
        self.run_script()
        link = self.home / ".config/ghostty/config"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), config)
        self.assertFalse(folded.is_symlink())
        self.assertTrue((self.repo / "ghossty").is_symlink())

    def test_legacy_unfolded_file_links_migrate(self):
        config = self.old_install_then_rename(no_folding=True)
        link = self.home / ".config/ghostty/config"
        self.assertTrue(link.is_symlink())
        self.run_script()
        self.assertEqual(link.resolve(), config)
        self.assertNotIn("ghossty", os.readlink(link))

    def test_legacy_config_parent_folded_link_migrates(self):
        (self.home / ".config").rmdir()
        config = self.old_install_then_rename()
        self.assertTrue((self.home / ".config").is_symlink())
        self.run_script()
        self.assertFalse((self.home / ".config").is_symlink())
        self.assertEqual((self.home / ".config/ghostty/config").resolve(), config)

    def test_absolute_legacy_file_link_is_preserved_for_manual_reconciliation(self):
        config = self.old_install_then_rename(no_folding=True)
        link = self.home / ".config/ghostty/config"
        link.unlink()
        link.symlink_to(self.repo / "ghossty/.config/ghostty/config")
        before = os.readlink(link)
        result = self.run_script(code=1)
        self.assertEqual(link.resolve(), config)
        self.assertEqual(os.readlink(link), before)
        self.assertNotIn("Migrating", result.stdout)

    def test_unowned_ghostty_config_symlink_is_preserved_on_conflict(self):
        self.config()
        (self.repo / "ghossty").symlink_to("ghostty", target_is_directory=True)
        unrelated = self.root / "user-config"
        unrelated.write_text("keep user config\n")
        link = self.home / ".config/ghostty/config"
        link.parent.mkdir()
        link.symlink_to(unrelated)
        before = os.readlink(link)
        self.run_script(code=1)
        self.assertEqual(os.readlink(link), before)
        self.assertEqual(unrelated.read_text(), "keep user config\n")

    def test_dry_run_does_not_change_legacy_link_or_checkout(self):
        self.old_install_then_rename()
        before_link = os.readlink(self.home / ".config/ghostty")
        before_alias = os.readlink(self.repo / "ghossty")
        self.run_script(dry_run=True)
        self.assertEqual(os.readlink(self.home / ".config/ghostty"), before_link)
        self.assertEqual(os.readlink(self.repo / "ghossty"), before_alias)

    def test_unrelated_home_links_and_real_config_are_never_removed(self):
        self.old_install_then_rename()
        unrelated_target = self.root / "unrelated"
        unrelated_target.write_text("keep\n")
        unrelated = self.home / ".config/unrelated-ghostty"
        unrelated.parent.mkdir(parents=True, exist_ok=True)
        unrelated.symlink_to(unrelated_target)
        self.run_script()
        self.assertEqual(unrelated.resolve(), unrelated_target)
        self.assertEqual(unrelated_target.read_text(), "keep\n")

        # An ordinary user file is not interpreted as an old Stow link.
        user_home = self.root / "user-home"
        user_home.mkdir()
        user_file = user_home / ".config/ghostty/config"
        user_file.parent.mkdir(parents=True)
        user_file.write_text("user config\n")
        self.home = user_home
        result = self.run_script(code=1)
        self.assertEqual(user_file.read_text(), "user config\n")
        self.assertIn("conflict", (result.stdout + result.stderr).lower())

    def test_repeat_migration_is_noop(self):
        self.old_install_then_rename(no_folding=True)
        self.run_script()
        before = os.readlink(self.home / ".config/ghostty/config")
        self.run_script()
        self.assertEqual(os.readlink(self.home / ".config/ghostty/config"), before)

    def test_canonical_conflict_preserves_folded_legacy_link_and_keeps_real_file(self):
        self.old_install_then_rename()
        # A conflict elsewhere prevents the combined transaction from applying
        # either action: the legacy link never needs restoration.
        conflict = self.home / ".config/ghostty-extra"
        conflict.write_text("user theme\n")
        (self.repo / "ghostty/.config/ghostty-extra").write_text("theme\n")
        result = self.run_script(code=1)
        self.assertIn("user theme", conflict.read_text())
        folded = self.home / ".config/ghostty"
        self.assertTrue(folded.is_symlink(), result.stdout + result.stderr)
        self.assertEqual((folded / "config").read_text(), "font-size = 12\n")


if __name__ == "__main__":
    unittest.main()

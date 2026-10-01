"""Fresh Stow installs exercise the real theme/plugin pipeline in a fake home."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class InstallIntegrationTests(unittest.TestCase):
    def test_fresh_install_and_repeat_render_all_required_generated_files(self):
        with tempfile.TemporaryDirectory(prefix="install-integration-") as temporary:
            root = Path(temporary)
            repo = root / "repo with spaces"
            home = root / "home"
            commands = root / "commands"
            for path in (repo, home, commands):
                path.mkdir()
            prefixes = ("lib/", "themes/", "plugins/", "awesome/", "hyprland/",
                        "ssh/", "alacritty/", "btop/", "nvim/", "pcmanfm/", "scripts/",
                        "ghossty/", "gnupg/", "xsession/", "picom/")
            # Include new first-party inputs before staging, but no ignored
            # theme output, caches or state.
            names = subprocess.check_output(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT,
            ).decode().split("\0")
            for name in sorted(set(filter(None, names))):
                if name != "install.sh" and not name.startswith(prefixes):
                    continue
                if name.startswith("scripts/.local/lib/python"):
                    continue
                source, dest = ROOT / name, repo / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if source.is_symlink():
                    dest.symlink_to(os.readlink(source))
                else:
                    shutil.copy2(source, dest)

            for name in ("awk", "bash", "basename", "cat", "cp", "date", "dirname", "echo", "flock", "grep", "id",
                         "ln", "lua", "luac", "mkdir", "mktemp", "mv", "python3", "readlink", "realpath",
                         "rm", "rmdir", "sed", "sleep", "sort", "stow", "tail", "timeout", "touch", "xargs"):
                executable = shutil.which(name)
                self.assertIsNotNone(executable, name)
                (commands / name).symlink_to(executable)
            # Only Downloads is configured, so gtk-bookmarks adds exactly one.
            stubs = {"awesome": 'exec luac -p "${@: -1}"',
                     "xdg-user-dir": '[[ "$1" == DOWNLOAD ]] && echo "$HOME/Downloads" || echo "$HOME"'}
            (home / "Downloads").mkdir(parents=True)
            for name in ("git", "curl", "pacman", "awesome", "xdg-user-dir"):
                body = stubs.get(name, "exit 0")
                path = commands / name
                path.write_text("#!/bin/bash\n" + body + "\n")
                path.chmod(0o755)
            # Never signal host processes or talk to the real desktop.
            targets = repo / "themes/targets.conf"
            targets.write_text("\n".join("|".join(line.split("|")[:2]) + "|"
                                         for line in targets.read_text().splitlines()
                                         if line.strip() and not line.startswith("#")) + "\n")
            env = {"HOME": str(home), "PATH": str(commands), "LC_ALL": "C", "TERM": "dumb",
                   "XDG_CONFIG_HOME": str(home / ".config"),
                   "XDG_STATE_HOME": str(home / ".local/state"), "TMPDIR": str(root),
                   "ALLOW_ROOT": "true"}
            for _ in range(2):
                result = subprocess.run(["bash", str(repo / "install.sh"), "-y", "--only", "stow", "--wm", "both"],
                                        cwd=repo, env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertNotIn("refresh failed", result.stdout + result.stderr)
                self.assertNotIn("apply failed", result.stdout + result.stderr)
                self.assertNotIn("gtk-bookmarks failed", result.stdout + result.stderr)
                self.assertEqual((home / ".config/gtk-3.0/bookmarks").read_text(),
                                 (home / "Downloads").as_uri() + "\n")
                # The scripts package puts the API-key loader in ~, but its
                # repository lint script must stay out of the home directory.
                self.assertTrue((home / "load-api-keys.sh").is_symlink())
                self.assertFalse(os.path.lexists(home / "check-syntax.py"))
                self.assertEqual((repo / "themes/out/.theme-name").read_text(), "mocha-peach\n")
                for path in ("alacritty/theme.toml", "hypr/lua/theme.lua", "waybar/config.jsonc",
                             "awesome/themes/powerarrow/colors.lua", "btop/themes/themectl.theme"):
                    dest = home / ".config" / path
                    self.assertTrue(dest.is_symlink(), path)
                    self.assertTrue(dest.exists(), path)
                for path in ("hypr/lua/plugins.lua", "awesome/plugins.lua"):
                    dest = home / ".config" / path
                    self.assertTrue(dest.is_file(), path)
                    subprocess.run(["luac", "-p", str(dest)], check=True, env=env)
                self.assertTrue((home / ".config/alacritty/alacritty.toml").is_symlink())
                self.assertTrue((home / ".local/bin/themectl").exists())
                for path in ("themes/colors.lua", "themes/mono/theme.lua", "theme-layout.lua"):
                    self.assertTrue((home / ".config/awesome" / path).is_file(), path)

"""Theme operations run only in disposable checkouts and homes."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
AWESOME_RESTART = 'require("theme-session").restart()\n'


class ThemeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="themectl-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.themes = self.root / "themes"
        shutil.copytree(ROOT / "themes", self.themes,
                        ignore=shutil.ignore_patterns("out", ".generations", ".apply.lock", "waybar-config.jsonc.tpl"))
        shutil.copytree(ROOT / "plugins", self.root / "plugins")
        self.home = self.root / "home"
        self.home.mkdir()
        commands = self.root / "bin"
        commands.mkdir()
        (commands / "herdr").symlink_to(shutil.which("true"))
        self.env = dict(os.environ, HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                        XDG_STATE_HOME=str(self.home / ".local/state"), TMPDIR=str(self.root),
                        DOTFILES_BACKUP_ROOT=str(self.root / "backups"), THEME_DIR=str(self.themes),
                        PATH=str(commands) + os.pathsep + os.environ["PATH"])
        # Never signal or reload the real desktop, even if a process is running.
        targets = self.themes / "targets.conf"
        targets.write_text("\n".join("|".join(line.split("|")[:2]) + "|"
                                    for line in targets.read_text().splitlines()
                                    if line.strip() and not line.startswith("#")) + "\n")

    def run_tool(self, tool, *args, success=True):
        result = subprocess.run([str(self.themes / tool), *args], env=self.env,
                                capture_output=True, text=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_fresh_clone_and_preview_isolation(self):
        self.run_tool("themectl", "set", "mocha-peach")
        live = (self.themes / "out").resolve()
        result = self.run_tool("themectl", "render", "nord")
        preview = Path(result.stdout.strip().split(" -> ")[1])
        self.assertEqual((preview / ".theme-name").read_text().strip(), "nord")
        self.assertEqual((self.themes / "out").resolve(), live)
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mocha-peach")
        self.assertFalse((self.themes / "templates/waybar-config.jsonc.tpl").exists())

    def test_switch_links_follow_generation(self):
        self.run_tool("themectl", "set", "mocha-peach")
        target = self.home / ".config/alacritty/theme.toml"
        previous = target.read_text()
        link = os.readlink(target)
        self.run_tool("themectl", "set", "nord")
        self.assertEqual(os.readlink(target), link)
        self.assertNotEqual(target.read_text(), previous)
        self.assertEqual(target.resolve(), (self.themes / "out/alacritty.toml").resolve())

    def desktop_stubs(self, running):
        # Exercise the real reload commands without touching the host desktop.
        commands = self.root / "bin"
        scripts = {
            "pgrep": 'case "${@: -1}" in ' + running + ') exit 0;; *) exit 1;; esac',
            "hyprctl": 'echo unexpected-hyprctl >> "$HOME/reloads"',
            "swaync-client": 'echo swaync >> "$HOME/reloads"; sleep 60',
            "awesome-client": 'echo "$*" >> "$HOME/reloads"',
        }
        for name, body in scripts.items():
            path = commands / name
            path.write_text("#!/bin/bash\n" + body + "\n")
            path.chmod(0o755)
        targets = self.themes / "targets.conf"
        targets.write_text("\n".join(
            line if line.startswith(("hypr-theme.lua |", "swaync-colors.css |", "awesome-colors.lua |"))
            else "|".join(line.split("|")[:2]) + "|"
            for line in (ROOT / "themes/targets.conf").read_text().splitlines()
            if line.strip() and not line.startswith("#")) + "\n")

    def test_awesome_skips_inactive_desktop_reloaders(self):
        self.desktop_stubs("awesome")
        # Even a stale Hyprland environment must not trigger a reload.
        self.env["HYPRLAND_INSTANCE_SIGNATURE"] = "stale-instance"
        result = self.run_tool("themectl", "set", "kanagawa")
        self.assertEqual(result.stderr, "")
        self.assertEqual((self.home / "reloads").read_text(), AWESOME_RESTART)

    def test_awesome_workspace_restoration(self):
        result = subprocess.run([
            "lua", str(ROOT / "tests/test_theme_session.lua"),
            str(ROOT / "awesome/.config/awesome/theme-session.lua"), str(self.root),
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stalled_reload_does_not_block_awesome_or_next_switch(self):
        self.desktop_stubs("awesome|swaync")
        result = self.run_tool("themectl", "set", "kanagawa")
        self.assertIn("reload swaync-colors.css timed out", result.stderr)
        self.assertEqual((self.home / "reloads").read_text(), "swaync\n" + AWESOME_RESTART)
        self.desktop_stubs("awesome")
        self.run_tool("themectl", "set", "nord")

    def test_stalled_hook_does_not_block_awesome(self):
        self.desktop_stubs("awesome")
        hook = self.themes / "hooks/00-stalled.sh"
        hook.write_text("#!/bin/bash\ntrap '' TERM\nsleep 60\n")
        hook.chmod(0o755)
        result = self.run_tool("themectl", "set", "kanagawa")
        self.assertIn("hook 00-stalled.sh timed out", result.stderr)
        self.assertEqual((self.home / "reloads").read_text(), AWESOME_RESTART)

    def test_every_palette_renders_on_a_fresh_clone(self):
        for name in self.run_tool("themectl", "list").stdout.splitlines():
            with self.subTest(name=name):
                self.run_tool("themectl", "render", name)

    def test_powerarrow_segment_text_is_readable(self):
        def luminance(hex_color):
            def channel(c):
                c /= 255
                return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = (channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        template = self.themes / "templates/awesome-colors.lua.tpl"
        for palette in sorted((self.themes / "palettes").glob("[!_]*.lua")):
            rendered = subprocess.run(["lua", str(self.themes / "render.lua"), str(palette), str(template)],
                                      capture_output=True, text=True, check=True).stdout
            segments = re.findall(r'(\w+) = \{ bg = "(#\w{6})", fg = "(#\w{6})", icon = "#\w{6}" \}', rendered)
            self.assertTrue(segments, palette.name)
            for name, bg, fg in segments:
                with self.subTest(palette=palette.stem, segment=name):
                    hi, lo = sorted((luminance(bg), luminance(fg)), reverse=True)
                    self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.5)

    def test_preview_includes_enabled_waybar_plugins(self):
        plugin = self.root / "plugins/test-widget"
        plugin.mkdir()
        (plugin / "manifest.conf").write_text('WAYBAR_MODULE="custom/test-widget"\n')
        (plugin / "waybar.jsonc").write_text('{"format": "test-widget"}')
        state = self.home / ".local/state/plugins"
        state.mkdir(parents=True)
        (state / "enabled").write_text("test-widget\n")
        result = self.run_tool("themectl", "render", "nord")
        preview = Path(result.stdout.strip().split(" -> ")[1])
        self.assertIn('"custom/test-widget"', (preview / "waybar-config.jsonc").read_text())
        self.assertFalse((self.home / ".config").exists())

    def test_failed_render_preserves_active_generation(self):
        self.run_tool("themectl", "set", "mocha-peach")
        previous = (self.themes / "out").resolve()
        (self.themes / "templates/gtk4.css.tpl").write_text("{{missing_key}}")
        self.run_tool("themectl", "set", "nord", success=False)
        self.assertEqual((self.themes / "out").resolve(), previous)
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mocha-peach")
        self.assertEqual(len(list((self.themes / ".generations").iterdir())), 1)

    def test_legacy_directory_is_retained(self):
        (self.themes / "out").mkdir()
        (self.themes / "out/old-file").write_text("old output")
        self.run_tool("themectl", "set", "nord")
        self.assertTrue((self.themes / "out").is_symlink())
        legacy = list((self.themes / ".generations").glob("legacy.*"))
        self.assertEqual((legacy[0] / "old-file").read_text(), "old output")

    def test_concurrent_next_waits_and_reads_current_under_lock(self):
        self.run_tool("themectl", "set", "mocha-peach")
        with (self.themes / ".apply.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            processes = [subprocess.Popen([str(self.themes / "themectl"), "next"],
                                          env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                          text=True) for _ in range(2)]
            try:
                for process in processes:
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.wait(timeout=0.1)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                for process in processes:
                    stdout, stderr = process.communicate(timeout=20)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "rose-pine")

    def source_palette(self):
        source = self.root / "colors.toml"
        keys = ("background dark_background darker_background lighter_background foreground "
                "dark_foreground light_foreground bright_foreground muted accent selection "
                "red green yellow blue cyan magenta").split()
        source.write_text("\n".join(f'{key} = "#123456" # valid TOML comment' for key in keys))
        return str(source)

    def test_import_validation_and_overwrite_guard(self):
        source = self.source_palette()
        self.run_tool("import-omarchy", source, "import-test")
        palette = self.themes / "palettes/import-test.lua"
        previous = palette.read_bytes()
        self.run_tool("import-omarchy", source, "import-test", success=False)
        self.run_tool("import-omarchy", source, "import-test", "--force")
        Path(source).write_text("")
        self.run_tool("import-omarchy", source, "import-test", "--force", success=False)
        self.assertEqual(palette.read_bytes(), previous)
        self.run_tool("import-omarchy", source, "new-invalid", success=False)
        self.assertFalse((self.themes / "palettes/new-invalid.lua").exists())

    def test_import_rejects_paths_and_invalid_colors(self):
        source = self.source_palette()
        self.run_tool("import-omarchy", source, "../escape", success=False)
        Path(source).write_text(Path(source).read_text().replace("#123456", "invalid"))
        self.run_tool("import-omarchy", source, "bad-color", success=False)
        self.assertFalse((self.themes / "palettes/bad-color.lua").exists())

    def test_import_template_failure_preserves_existing_palette(self):
        source = self.source_palette()
        destination = self.themes / "palettes/nord.lua"
        previous = destination.read_bytes()
        (self.themes / "templates/gtk4.css.tpl").write_text("{{missing_key}}")
        self.run_tool("import-omarchy", source, "nord", "--force", success=False)
        self.assertEqual(destination.read_bytes(), previous)

    def herdr_config(self):
        conf = self.home / ".config/herdr/config.toml"
        conf.parent.mkdir(parents=True)
        real = self.root / "herdr.toml"
        real.write_text('title = "keep"\n  [theme]\nname = "old"\n[keybindings]\nquit = "q"\n')
        real.chmod(0o640)
        conf.symlink_to(real)
        return conf, real

    def test_herdr_preserves_settings_symlink_permissions_and_backup(self):
        self.run_tool("themectl", "set", "nord")
        conf, real = self.herdr_config()
        previous = real.read_bytes()
        self.run_tool("hooks/herdr.sh")
        data = tomllib.loads(real.read_text())
        self.assertEqual(data["keybindings"], {"quit": "q"})
        self.assertEqual(data["title"], "keep")
        self.assertNotEqual(data["theme"]["name"], "old")
        self.assertTrue(conf.is_symlink())
        self.assertEqual(real.stat().st_mode & 0o777, 0o640)
        backups = list((self.root / "backups/themes").glob("herdr-config.toml.*"))
        self.assertEqual(backups[0].read_bytes(), previous)

    def test_herdr_invalid_fragment_preserves_original(self):
        self.run_tool("themectl", "set", "nord")
        conf, real = self.herdr_config()
        previous = real.read_bytes()
        (self.themes / "out/herdr-theme.toml").write_text("[broken")
        self.run_tool("hooks/herdr.sh", success=False)
        self.assertEqual(real.read_bytes(), previous)
        self.assertTrue(conf.is_symlink())


if __name__ == "__main__":
    unittest.main()

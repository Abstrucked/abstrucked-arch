"""Theme operations run only in disposable checkouts and homes."""
import fcntl
import json
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

    def test_mono_palette_switch_preserves_layout_selection(self):
        state = self.home / ".local/state/awesome/theme-layout"
        state.parent.mkdir(parents=True)
        state.write_text("mono\n")
        self.run_tool("themectl", "set", "mono")
        palette = self.home / ".config/awesome/themes/powerarrow/colors.lua"
        self.assertIn('accent = "#c2d89a"', palette.read_text())
        self.assertIn('background = "#171a18"', (self.themes / "out/alacritty.toml").read_text())
        target = os.readlink(palette)
        self.run_tool("themectl", "set", "nord")
        self.assertEqual(state.read_text(), "mono\n")
        self.assertEqual(os.readlink(palette), target)
        self.assertNotIn('accent = "#c2d89a"', palette.read_text())

    def test_awesome_layout_selection(self):
        config = self.home / ".config/awesome"
        for name in ("mono", "powerarrow"):
            theme = config / "themes" / name / "theme.lua"
            theme.parent.mkdir(parents=True)
            theme.write_text("return {}\n")
        (self.home / ".local/state/awesome").mkdir(parents=True)
        result = subprocess.run([
            "lua", str(ROOT / "tests/test_theme_layout.lua"),
            str(ROOT / "awesome/.config/awesome/theme-layout.lua"), str(config),
        ], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_opencode_theme_matches_v2_shape_and_palette(self):
        def luminance(hex_color):
            channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
            channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                        for value in channels]
            return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

        def contrast(a, b):
            high, low = sorted((luminance(a), luminance(b)), reverse=True)
            return (high + 0.05) / (low + 0.05)

        def assert_shape(actual, expected, path="base"):
            for key, child in expected.items():
                current_path = f"{path}.{key}"
                self.assertIn(key, actual, current_path)
                if isinstance(child, dict):
                    self.assertIsInstance(actual[key], dict, current_path)
                    assert_shape(actual[key], child, current_path)
                else:
                    self.assertIsInstance(actual[key], str, current_path)
                    self.assertRegex(actual[key], r"^#[0-9a-fA-F]{6}$", current_path)

        state = {"base": None, "$hovered": None, "$focused": None, "$pressed": None,
                 "$selected": None, "$disabled": None}
        feedback_text = {kind: {"base": None, "muted": None}
                         for kind in ("error", "warning", "success", "info")}
        feedback_bg = {kind: {"base": None} for kind in ("error", "warning", "success", "info")}
        expected_base = {
            "text": {
                "base": None, "muted": None,
                "action": {kind: state for kind in ("primary", "secondary", "destructive")},
                "formfield": state,
                "feedback": feedback_text,
            },
            "background": {
                "base": None,
                "raised": {"base": None, "high": None, "max": None},
                "action": {kind: state for kind in ("primary", "secondary", "destructive")},
                "formfield": state,
                "feedback": feedback_bg,
            },
            "border": {"base": None},
            "scrollbar": {"base": None},
            "diff": {
                "text": {"added": None, "removed": None, "context": None, "hunkHeader": None},
                "background": {"added": None, "removed": None, "context": None},
                "highlight": {"added": None, "removed": None},
                "lineNumber": {
                    "text": None,
                    "background": {"added": None, "removed": None},
                },
            },
            "syntax": {key: None for key in (
                "comment", "keyword", "function", "variable", "string", "number", "type", "operator", "punctuation",
            )},
            "markdown": {key: None for key in (
                "text", "heading", "link", "linkText", "code", "blockQuote", "emphasis", "strong",
                "horizontalRule", "listItem", "listEnumeration", "image", "imageText", "codeBlock",
            )},
        }

        template = self.themes / "templates/opencode-theme.json.tpl"
        palette_dir = self.themes / "palettes"
        hues = {"gray", "red", "orange", "yellow", "green", "cyan", "blue", "purple"}
        steps = {str(value) for value in range(100, 1000, 100)}
        for palette in sorted(palette_dir.glob("[!_]*.lua")):
            with self.subTest(palette=palette.stem):
                rendered = subprocess.run(
                    ["lua", str(self.themes / "render.lua"), str(palette), str(template)],
                    env=self.env, capture_output=True, text=True, check=True,
                ).stdout
                theme = json.loads(rendered)
                self.assertEqual(theme["$schema"], "https://opencode.ai/theme.json")
                self.assertIn("base", theme)
                modes = {key for key in ("light", "dark") if key in theme}
                self.assertEqual(len(modes), 1)
                self.assertEqual(modes, {"light" if palette.stem == "rose-pine" else "dark"})
                mode = theme[next(iter(modes))]
                self.assertEqual(set(mode["hue"]), hues | {"accent", "interactive", "neutral"})
                self.assertEqual(mode["categorical"], theme["base"]["categorical"])
                for hue in hues:
                    ramp = mode["hue"][hue]
                    self.assertEqual(set(ramp), steps, hue)
                    colors = [ramp[str(value)] for value in range(100, 1000, 100)]
                    self.assertTrue(all(re.fullmatch(r"#[0-9a-fA-F]{6}", color) for color in colors), hue)
                    brightness = [luminance(color) for color in colors]
                    if "dark" in modes:
                        self.assertTrue(all(a >= b - 0.002 for a, b in zip(brightness, brightness[1:])), hue)
                    else:
                        self.assertTrue(all(a <= b + 0.002 for a, b in zip(brightness, brightness[1:])), hue)
                for alias in ("accent", "interactive", "neutral"):
                    self.assertRegex(mode["hue"][alias], r"^\$hue\.(gray|red|orange|yellow|green|cyan|blue|purple)$")

                base = theme["base"]
                self.assertEqual(base["categorical"], ["accent", "red", "green", "blue", "purple"])
                assert_shape(base, expected_base)
                self.assertGreaterEqual(contrast(base["text"]["base"], base["background"]["base"]), 4.5)
                for action in ("primary", "destructive"):
                    for state in ("base", "$hovered", "$focused", "$pressed", "$selected"):
                        self.assertGreaterEqual(
                            contrast(base["text"]["action"][action][state],
                                     base["background"]["action"][action][state]), 4.5,
                        )
                self.assertGreaterEqual(contrast(base["text"]["muted"], base["background"]["base"]), 4.5)
                self.assertGreaterEqual(contrast(base["text"]["muted"], base["background"]["raised"]["base"]), 4.5)
                self.assertEqual(base["markdown"]["codeBlock"], base["text"]["base"])
                for kind in ("error", "warning", "success", "info"):
                    self.assertGreaterEqual(
                        contrast(base["text"]["feedback"][kind]["base"],
                                 base["background"]["feedback"][kind]["base"]), 4.5,
                    )
                for kind in ("added", "removed"):
                    self.assertGreaterEqual(
                        contrast(base["diff"]["text"][kind], base["diff"]["background"][kind]), 4.5,
                    )

    def test_opencode_theme_renders_imported_palette_defaults(self):
        source = self.source_palette()
        self.run_tool("import-omarchy", source, "opencode-import")
        palette = self.themes / "palettes/opencode-import.lua"
        template = self.themes / "templates/opencode-theme.json.tpl"
        rendered = subprocess.run(
            ["lua", str(self.themes / "render.lua"), str(palette), str(template)],
            env=self.env, capture_output=True, text=True, check=True,
        ).stdout
        theme = json.loads(rendered)
        self.assertEqual(theme["base"]["background"]["base"], "#123456")
        self.assertEqual(theme["base"]["text"]["base"], "#123456")
        self.assertEqual(set(theme["dark"]["hue"]["orange"]), {str(value) for value in range(100, 1000, 100)})

    def test_opencode_theme_hook_publishes_and_preserves_user_config(self):
        cli_config = self.home / ".config/opencode/cli.json"
        cli_config.parent.mkdir(parents=True)
        cli_bytes = b'{\n  "theme": {"name": "tokyonight", "mode": "system"},\n  "mouse": true\n}\n'
        cli_config.write_bytes(cli_bytes)
        destination = self.home / ".config/opencode/themes/dotfiles.json"

        self.run_tool("themectl", "set", "mono")
        self.assertTrue(destination.is_file())
        first = json.loads(destination.read_text())
        self.assertEqual(first["base"]["background"]["base"], "#171a18")
        self.assertEqual(cli_config.read_bytes(), cli_bytes)
        self.assertFalse(destination.is_symlink(), "publisher replaces a destination symlink, never its target")

        self.run_tool("themectl", "set", "nord")
        second = json.loads(destination.read_text())
        self.assertNotEqual(first["base"]["background"]["base"], second["base"]["background"]["base"])
        self.assertEqual(cli_config.read_bytes(), cli_bytes)
        backups = list((self.root / "backups/themes").glob("opencode-dotfiles.json.orig*"))
        self.assertEqual(backups, [], "subsequent managed palette changes do not back up our own output")

    def test_opencode_theme_hook_respects_xdg_and_backups_existing_content(self):
        alternate = self.root / "xdg-config"
        destination = alternate / "opencode/themes/dotfiles.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"user": "theme"}\n')
        self.env["XDG_CONFIG_HOME"] = str(alternate)
        self.run_tool("themectl", "set", "mono")
        self.assertEqual(json.loads(destination.read_text())["base"]["background"]["base"], "#171a18")
        backups = list((self.root / "backups/themes").glob("opencode-dotfiles.json.orig*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(), '{"user": "theme"}\n')

        destination.write_text('{"manual": "edit"}\n')
        self.run_tool("themectl", "set", "nord")
        backups = sorted((self.root / "backups/themes").glob("opencode-dotfiles.json.orig*"))
        self.assertEqual(len(backups), 2)
        self.assertEqual(backups[1].read_text(), '{"manual": "edit"}\n')

    def test_opencode_theme_hook_replaces_symlink_without_touching_target(self):
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        destination.parent.mkdir(parents=True)
        target = self.root / "user-theme.json"
        target.write_text('{"keep": "this"}\n')
        destination.symlink_to(target)

        self.run_tool("themectl", "set", "mono")
        self.assertFalse(destination.is_symlink())
        self.assertEqual(target.read_text(), '{"keep": "this"}\n')
        backup = next((self.root / "backups/themes").glob("opencode-dotfiles.json.orig*"))
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), str(target))

    def test_opencode_theme_hook_invalid_json_preserves_published_theme(self):
        self.run_tool("themectl", "set", "mono")
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        previous = destination.read_bytes()
        (self.themes / "out/opencode-theme.json").write_text("{broken\n")
        self.run_tool("hooks/opencode.sh", success=False)
        self.assertEqual(destination.read_bytes(), previous)

    def test_opencode_theme_hook_rejects_incomplete_v2_tokens(self):
        self.run_tool("themectl", "set", "mono")
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        previous = destination.read_bytes()
        rendered = self.themes / "out/opencode-theme.json"
        original = json.loads(rendered.read_text())
        for key in ("syntax", "text", "diff"):
            with self.subTest(key=key):
                incomplete = json.loads(json.dumps(original))
                del incomplete["base"][key]
                rendered.write_text(json.dumps(incomplete))
                self.run_tool("hooks/opencode.sh", success=False)
                self.assertEqual(destination.read_bytes(), previous)

        incomplete = json.loads(json.dumps(original))
        del incomplete["dark"]["hue"]["blue"]["900"]
        rendered.write_text(json.dumps(incomplete))
        self.run_tool("hooks/opencode.sh", success=False)
        self.assertEqual(destination.read_bytes(), previous)

        invalid = json.loads(json.dumps(original))
        invalid["base"]["text"]["action"]["primary"]["$hovered"] = "invalid"
        rendered.write_text(json.dumps(invalid))
        self.run_tool("hooks/opencode.sh", success=False)
        self.assertEqual(destination.read_bytes(), previous)

    def test_opencode_preview_does_not_publish_or_create_cli_settings(self):
        result = self.run_tool("themectl", "render", "mono")
        preview = Path(result.stdout.strip().split(" -> ")[1])
        self.assertEqual(json.loads((preview / "opencode-theme.json").read_text())["base"]["background"]["base"], "#171a18")
        self.assertFalse((self.home / ".config/opencode").exists())
        self.run_tool("themectl", "set", "mono")
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        previous = destination.read_bytes()
        self.assertFalse((self.home / ".config/opencode/cli.json").exists())
        self.run_tool("themectl", "render", "nord")
        self.assertEqual(destination.read_bytes(), previous)

    def test_opencode_malformed_cli_config_is_not_touched(self):
        config = self.home / ".config/opencode/cli.json"
        config.parent.mkdir(parents=True)
        config.write_text("{invalid settings\n")
        self.run_tool("themectl", "set", "mono")
        self.run_tool("themectl", "next")
        self.run_tool("themectl", "apply")
        self.assertEqual(config.read_text(), "{invalid settings\n")

    def test_opencode_dangling_symlink_backup_and_permissions(self):
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        destination.parent.mkdir(parents=True)
        missing = self.root / "missing-theme.json"
        destination.symlink_to(missing)
        self.run_tool("themectl", "set", "mono")
        self.assertFalse(missing.exists())
        backup = next((self.root / "backups/themes").glob("opencode-dotfiles.json.orig*"))
        self.assertTrue(backup.is_symlink())
        self.assertEqual(os.readlink(backup), str(missing))
        destination.chmod(0o640)
        self.run_tool("themectl", "set", "nord")
        self.assertEqual(destination.stat().st_mode & 0o777, 0o640)
        self.assertEqual(list(destination.parent.glob(".dotfiles.json.themectl-*")), [])

    def test_opencode_directory_destination_is_not_replaced(self):
        self.run_tool("themectl", "set", "mono")
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        destination.unlink()
        directory = self.root / "user-theme-directory"
        directory.mkdir()
        (directory / "keep").write_text("preserve this directory\n")
        destination.symlink_to(directory, target_is_directory=True)
        self.run_tool("hooks/opencode.sh", success=False)
        self.assertTrue(destination.is_symlink())
        self.assertEqual((directory / "keep").read_text(), "preserve this directory\n")

    def test_opencode_hook_failure_keeps_previous_theme_after_activation(self):
        self.run_tool("themectl", "set", "mono")
        destination = self.home / ".config/opencode/themes/dotfiles.json"
        previous = destination.read_bytes()
        (self.themes / "templates/opencode-theme.json.tpl").write_text('{"base": {}, "dark": {}}\n')
        result = self.run_tool("themectl", "set", "nord")
        self.assertIn("hook opencode.sh failed", result.stderr)
        self.assertEqual(destination.read_bytes(), previous)
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "nord")

    def test_powerarrow_segment_text_is_readable(self):
        def luminance(hex_color):
            def channel(c):
                c /= 255
                return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = (channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        template = self.themes / "templates/awesome-colors.lua.tpl"
        mono_style = ROOT / "awesome/.config/awesome/themes/mono/style.lua"
        for palette in sorted((self.themes / "palettes").glob("[!_]*.lua")):
            rendered = subprocess.run(["lua", str(self.themes / "render.lua"), str(palette), str(template)],
                                      capture_output=True, text=True, check=True).stdout
            segments = re.findall(r'(\w+) = \{ bg = "(#\w{6})", fg = "(#\w{6})", icon = "#\w{6}" \}', rendered)
            self.assertTrue(segments, palette.name)
            for name, bg, fg in segments:
                with self.subTest(palette=palette.stem, segment=name):
                    hi, lo = sorted((luminance(bg), luminance(fg)), reverse=True)
                    self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.5)

            # Mono's selected tags must remain readable with every palette,
            # including imported palettes with mid-tone accents.
            colors = self.root / "colors.lua"
            colors.write_text(rendered)
            output = subprocess.check_output([
                "lua", "-e",
                'local style = dofile(arg[1]); local c = dofile(arg[2]); '
                'print(c.accent); print(style.on(c.accent, c)); os.exit(0)',
                "--", "mono-contrast", str(mono_style), str(colors),
            ], text=True).splitlines()
            hi, lo = sorted(map(luminance, output), reverse=True)
            self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.5, palette.stem)

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
        names = self.run_tool("themectl", "list").stdout.splitlines()
        expected = names[(names.index("mocha-peach") + 2) % len(names)]
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
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), expected)

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

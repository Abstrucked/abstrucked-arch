"""Theme operations run only in disposable checkouts and homes."""
import configparser
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

# Test double for awesome-client: evaluates the chunk the way awful.remote
# does (load + pcall) with gears.filesystem and theme-session stubbed, so the
# real theme-layout.lua runs against the disposable home. Replies use
# dbus-send's `string "..."` shape, including errors with exit status 0, and
# never touch the host desktop.
IPC_HARNESS = r'''
local chunk = arg[1] or ""
local load_chunk = loadstring or load

local function reply(value)
    local text = tostring(value):gsub('"', '\\"')
    io.write('   string "', text, '"\n')
end

local config_dir = os.getenv("AWESOME_CONFIG_DIR") or (os.getenv("HOME") .. "/.config/awesome/")
if config_dir:sub(-1) ~= "/" then config_dir = config_dir .. "/" end
local restart_log = os.getenv("AWESOME_RESTART_LOG") or (os.getenv("HOME") .. "/restarts")

package.loaded["gears.filesystem"] = {
    get_configuration_dir = function() return config_dir end,
    make_directories = function() end,
    file_readable = function(path)
        local file = io.open(path, "r")
        if not file then return false end
        file:close()
        return true
    end,
}
package.loaded["theme-session"] = {
    restart = function()
        local file = assert(io.open(restart_log, "a"))
        file:write("restart\n")
        file:close()
        if os.getenv("AWESOME_RESTART_FAIL") == "1" then
            error("injected restart failure")
        end
    end,
}

local fail_on = os.getenv("AWESOME_FAIL_ON") or ""
if fail_on ~= "" and chunk:find(fail_on, 1, true) then
    reply("Error during execution: injected stub failure")
    os.exit(0)
end

local fn, err = load_chunk(chunk)
if not fn then
    reply(err)
    os.exit(0)
end
local results = { pcall(fn) }
if not table.remove(results, 1) then
    reply("Error during execution: " .. tostring(results[1]))
    os.exit(0)
end
for _, value in ipairs(results) do
    reply(value)
end
'''


def contrast(a, b):
    """WCAG contrast ratio between two #rrggbb colors."""
    def luminance(hex_color):
        def channel(c):
            c /= 255
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        r, g, b = (channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


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
        # The host's login environment must not steer the disposable home.
        self.env.pop("AWESOME_THEME", None)
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
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        live = (self.themes / "out").resolve()
        result = self.run_tool("themectl", "render", "--colors", "nord")
        preview = Path(result.stdout.strip().split(" -> ")[1])
        self.assertEqual((preview / ".theme-name").read_text().strip(), "nord")
        self.assertEqual((self.themes / "out").resolve(), live)
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "mocha-peach")
        self.assertFalse((self.themes / "templates/waybar-config.jsonc.tpl").exists())

    def test_switch_links_follow_generation(self):
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        target = self.home / ".config/alacritty/theme.toml"
        previous = target.read_text()
        link = os.readlink(target)
        self.run_tool("themectl", "set", "--colors", "nord")
        self.assertEqual(os.readlink(target), link)
        self.assertNotEqual(target.read_text(), previous)
        self.assertEqual(target.resolve(), (self.themes / "out/alacritty.toml").resolve())

    def test_matching_palette_switch_preserves_layout_selection(self):
        state = self.home / ".local/state/awesome/theme-layout"
        state.parent.mkdir(parents=True)
        for name, accent, bg in (("mono", "#c2d89a", "#171a18"), ("slate", "#96b3cf", "#16191f"),
                                 ("nocturne", "#b8a6ff", "#14111a")):
            with self.subTest(layout=name):
                state.write_text(name + "\n")
                self.run_tool("themectl", "set", "--colors", name)
                palette = self.home / ".config/awesome/themes/powerarrow/colors.lua"
                self.assertIn(f'accent = "{accent}"', palette.read_text())
                self.assertIn(f'background = "{bg}"', (self.themes / "out/alacritty.toml").read_text())
                target = os.readlink(palette)
                self.run_tool("themectl", "set", "--colors", "nord")
                self.assertEqual(state.read_text(), name + "\n")
                self.assertEqual(os.readlink(palette), target)
                self.assertNotIn(f'accent = "{accent}"', palette.read_text())

    def test_awesome_layout_selection(self):
        config = self.home / ".config/awesome"
        for name in ("mono", "slate", "nocturne", "powerarrow", "tide"):
            theme = config / "themes" / name / "theme.lua"
            theme.parent.mkdir(parents=True)
            theme.write_text("return {}\n")
        (self.home / ".local/state/awesome").mkdir(parents=True)
        result = subprocess.run([
            "lua", str(ROOT / "tests/test_theme_layout.lua"),
            str(ROOT / "awesome/.config/awesome/theme-layout.lua"), str(config),
        ], env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def desktop_stubs(self, running, stall=True):
        # Exercise the real reload commands without touching the host desktop.
        self.ipc_stub()
        scripts = {
            "pgrep": 'case "${@: -1}" in ' + running + ') exit 0;; *) exit 1;; esac',
            "hyprctl": 'echo unexpected-hyprctl >> "$HOME/reloads"',
            "swaync-client": 'echo swaync >> "$HOME/reloads"' + ('; sleep 60' if stall else ''),
        }
        for name, body in scripts.items():
            self.command(name, body)
        targets = self.themes / "targets.conf"
        targets.write_text("\n".join(
            line if line.startswith(("hypr-theme.lua |", "swaync-colors.css |", "awesome-colors.lua |"))
            else "|".join(line.split("|")[:2]) + "|"
            for line in (ROOT / "themes/targets.conf").read_text().splitlines()
            if line.strip() and not line.startswith("#")) + "\n")

    def command(self, name, body):
        path = self.root / "bin" / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(0o755)

    def ipc_stub(self):
        """Fake awesome-client that evaluates layout chunks like awful.remote
        and logs every invocation; replies keep awesome-client's shape."""
        harness = self.root / "ipc-harness.lua"
        harness.write_text(IPC_HARNESS)
        self.env["IPC_HARNESS"] = str(harness)
        self.env["AWESOME_RESTART_LOG"] = str(self.home / "restarts")
        self.command("awesome-client",
                     'echo "$*" >> "$HOME/reloads"\necho "$*" >> "$HOME/ipc.log"\n'
                     'exec lua "$IPC_HARNESS" "$@"')

    def awesome_config(self, *layouts):
        """Disposable installed Awesome config: theme-layout.lua plus layouts."""
        awesome = self.home / ".config/awesome"
        (awesome / "themes").mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / "awesome/.config/awesome/theme-layout.lua", awesome / "theme-layout.lua")
        for name in layouts:
            theme = awesome / "themes" / name / "theme.lua"
            theme.parent.mkdir(parents=True, exist_ok=True)
            theme.write_text("return {}\n")
        (self.home / ".local/state/awesome").mkdir(parents=True, exist_ok=True)
        self.env["AWESOME_CONFIG_DIR"] = str(awesome) + "/"
        return awesome

    def safe_path(self):
        """PATH for lookups that must never find the host's desktop tools."""
        safe = self.root / "safebin"
        safe.mkdir(exist_ok=True)
        for name in ("awk", "basename", "bash", "cat", "cp", "date", "dirname", "flock", "grep",
                     "head", "id", "ln", "lua", "mkdir", "mktemp", "mv", "readlink", "realpath",
                     "rm", "rmdir", "sed", "sleep", "sort", "tail", "timeout", "touch", "tr",
                     "xargs"):
            target = shutil.which(name)
            if target and not (safe / name).exists():
                (safe / name).symlink_to(target)
        return str(safe)

    def restarts(self):
        log = self.home / "restarts"
        return log.read_text().splitlines() if log.exists() else []

    def ipc_log(self):
        log = self.home / "ipc.log"
        return log.read_text().splitlines() if log.exists() else []

    def test_awesome_skips_inactive_desktop_reloaders(self):
        self.desktop_stubs("awesome")
        # Even a stale Hyprland environment must not trigger a reload.
        self.env["HYPRLAND_INSTANCE_SIGNATURE"] = "stale-instance"
        result = self.run_tool("themectl", "set", "--colors", "kanagawa")
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
        result = self.run_tool("themectl", "set", "--colors", "kanagawa")
        self.assertIn("reload swaync-colors.css timed out", result.stderr)
        self.assertEqual((self.home / "reloads").read_text(), "swaync\n" + AWESOME_RESTART)
        self.desktop_stubs("awesome")
        self.run_tool("themectl", "set", "--colors", "nord")

    def test_stalled_hook_does_not_block_awesome(self):
        self.desktop_stubs("awesome")
        hook = self.themes / "hooks/00-stalled.sh"
        hook.write_text("#!/bin/bash\ntrap '' TERM\nsleep 60\n")
        hook.chmod(0o755)
        result = self.run_tool("themectl", "set", "--colors", "kanagawa")
        self.assertIn("hook 00-stalled.sh timed out", result.stderr)
        self.assertEqual((self.home / "reloads").read_text(), AWESOME_RESTART)

    def test_every_palette_renders_on_a_fresh_clone(self):
        for name in self.run_tool("themectl", "list", "--colors").stdout.splitlines():
            with self.subTest(name=name):
                self.run_tool("themectl", "render", "--colors", name)

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

    def test_tmux_colors_cover_theme_and_stay_readable(self):
        theme = (ROOT / "config/tmux/theme.conf").read_text()
        used = set(re.findall(r"#\{(@thm_\w+)\}", theme))
        fallbacks = set(re.findall(r"^set -g (@thm_\w+) ", theme, re.M))
        self.assertTrue(used)
        self.assertEqual(used, fallbacks)

        def luminance(hex_color):
            def channel(c):
                c /= 255
                return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
            r, g, b = (channel(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))
            return 0.2126 * r + 0.7152 * g + 0.0722 * b

        template = self.themes / "templates/tmux-colors.conf.tpl"
        for palette in sorted((self.themes / "palettes").glob("[!_]*.lua")):
            with self.subTest(palette=palette.stem):
                rendered = subprocess.run(["lua", str(self.themes / "render.lua"), str(palette), str(template)],
                                          capture_output=True, text=True, check=True).stdout
                colors = dict(re.findall(r"^set -g (@thm_\w+) '(#[0-9a-fA-F]{6})'$", rendered, re.M))
                self.assertEqual(set(colors), fallbacks)
                hi, lo = sorted((luminance(colors["@thm_accent"]), luminance(colors["@thm_on_accent"])),
                                reverse=True)
                self.assertGreaterEqual((hi + 0.05) / (lo + 0.05), 4.5)

    def render(self, palette, template):
        return subprocess.run(["lua", str(self.themes / "render.lua"), str(palette),
                               str(self.themes / "templates" / template)],
                              capture_output=True, text=True, check=True).stdout

    def test_gtk3_recolors_with_the_gtk4_named_colors(self):
        # adw-gtk3 draws GTK3 widgets from libadwaita's named colors, so GTK3
        # apps such as PCManFM match GTK4 ones only while the two agree.
        define = re.compile(r"^@define-color (\w+) (#[0-9a-fA-F]{6});$", re.M)
        for palette in sorted((self.themes / "palettes").glob("[!_]*.lua")):
            with self.subTest(palette=palette.stem):
                gtk4 = dict(define.findall(self.render(palette, "gtk4.css.tpl")))
                gtk3 = dict(define.findall(self.render(palette, "gtk3.css.tpl")))
                self.assertIn("window_bg_color", gtk4)
                self.assertEqual({name: gtk3.get(name) for name in gtk4}, gtk4)

    def test_gtk3_theme_follows_palette_variant(self):
        palettes = sorted((self.themes / "palettes").glob("[!_]*.lua"))
        variants = set()
        for palette in palettes:
            with self.subTest(palette=palette.stem):
                variant = subprocess.check_output(
                    ["lua", "-e", "io.write(dofile(arg[1]).variant or 'dark'); os.exit(0)",
                     "--", "variant", str(palette)],
                    text=True)
                variants.add(variant)
                settings = self.render(palette, "gtk3-settings.ini.tpl")
                theme, dark = ("adw-gtk3", "0") if variant == "light" else ("adw-gtk3-dark", "1")
                self.assertIn(f"\ngtk-theme-name={theme}\n", settings)
                self.assertIn(f"\ngtk-application-prefer-dark-theme={dark}\n", settings)
        self.assertEqual(variants, {"dark", "light"})

    def test_qt_palette_matches_gtk_and_stays_readable(self):
        # QPalette role order in qt6ct color schemes.
        roles = ("WindowText", "Button", "Light", "Midlight", "Dark", "Mid", "Text", "BrightText",
                 "ButtonText", "Base", "Window", "Shadow", "Highlight", "HighlightedText", "Link",
                 "LinkVisited", "AlternateBase", "NoRole", "ToolTipBase", "ToolTipText", "PlaceholderText")
        define = re.compile(r"^@define-color (\w+) (#[0-9a-fA-F]{6});$", re.M)
        for palette in sorted((self.themes / "palettes").glob("[!_]*.lua")):
            with self.subTest(palette=palette.stem):
                scheme = configparser.ConfigParser(interpolation=None)
                scheme.read_string(self.render(palette, "qt6ct-colors.conf.tpl"))
                groups = {}
                for group in ("active", "inactive", "disabled"):
                    colors = [c.strip() for c in scheme["ColorScheme"][group + "_colors"].split(",")]
                    self.assertEqual(len(colors), len(roles), group)
                    for color in colors:
                        self.assertRegex(color, r"^#[0-9a-fA-F]{6}$", group)
                    groups[group] = dict(zip(roles, colors))
                active = groups["active"]
                gtk = dict(define.findall(self.render(palette, "gtk3.css.tpl")))
                self.assertEqual(
                    {role: active[role] for role in ("Window", "WindowText", "Base", "Text",
                                                     "Highlight", "HighlightedText")},
                    {"Window": gtk["window_bg_color"], "WindowText": gtk["window_fg_color"],
                     "Base": gtk["view_bg_color"], "Text": gtk["view_fg_color"],
                     "Highlight": gtk["accent_bg_color"], "HighlightedText": gtk["accent_fg_color"]})
                for text, background in (("Text", "Base"), ("WindowText", "Window"), ("BrightText", "Dark")):
                    self.assertGreaterEqual(contrast(active[text], active[background]), 4.5,
                                            f"{text} on {background}")

    def test_qt_settings_use_the_scheme_and_the_gtk_font(self):
        palette = self.themes / "palettes/nord.lua"
        settings = self.render(palette, "qt6ct.conf.tpl")
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(settings)
        self.assertEqual(config["Appearance"]["color_scheme_path"], "~/.config/qt6ct/colors/themectl.conf")
        self.assertEqual(config["Appearance"]["custom_palette"], "true")
        gtk_font = re.search(r"^gtk-font-name=(.+) (\d+)$",
                             self.render(palette, "gtk3-settings.ini.tpl"), re.M).groups()
        for key in ("general", "fixed"):
            # Unquoted, QSettings splits the value at its commas and qt6ct gets no font.
            font = config["Fonts"][key]
            self.assertTrue(font.startswith('"') and font.endswith('"'), key)
            self.assertEqual(tuple(font.strip('"').split(",")[:2]), gtk_font, key)

    def test_preview_includes_enabled_waybar_plugins(self):
        plugin = self.root / "plugins/test-widget"
        plugin.mkdir()
        (plugin / "manifest.conf").write_text('WAYBAR_MODULE="custom/test-widget"\n')
        (plugin / "waybar.jsonc").write_text('{"format": "test-widget"}')
        state = self.home / ".local/state/plugins"
        state.mkdir(parents=True)
        (state / "enabled").write_text("test-widget\n")
        result = self.run_tool("themectl", "render", "--colors", "nord")
        preview = Path(result.stdout.strip().split(" -> ")[1])
        self.assertIn('"custom/test-widget"', (preview / "waybar-config.jsonc").read_text())
        self.assertFalse((self.home / ".config").exists())

    def test_failed_render_preserves_active_generation(self):
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        previous = (self.themes / "out").resolve()
        (self.themes / "templates/gtk4.css.tpl").write_text("{{missing_key}}")
        self.run_tool("themectl", "set", "--colors", "nord", success=False)
        self.assertEqual((self.themes / "out").resolve(), previous)
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "mocha-peach")
        self.assertEqual(len(list((self.themes / ".generations").iterdir())), 1)

    def test_legacy_directory_is_retained(self):
        (self.themes / "out").mkdir()
        (self.themes / "out/old-file").write_text("old output")
        self.run_tool("themectl", "set", "--colors", "nord")
        self.assertTrue((self.themes / "out").is_symlink())
        legacy = list((self.themes / ".generations").glob("legacy.*"))
        self.assertEqual((legacy[0] / "old-file").read_text(), "old output")

    def test_concurrent_next_waits_and_reads_current_under_lock(self):
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        names = self.run_tool("themectl", "list", "--colors").stdout.splitlines()
        expected = names[(names.index("mocha-peach") + 2) % len(names)]
        with (self.themes / ".apply.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            processes = [subprocess.Popen([str(self.themes / "themectl"), "next", "--colors"],
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
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), expected)

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
        self.run_tool("themectl", "set", "--colors", "nord")
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
        self.run_tool("themectl", "set", "--colors", "nord")
        conf, real = self.herdr_config()
        previous = real.read_bytes()
        (self.themes / "out/herdr-theme.toml").write_text("[broken")
        self.run_tool("hooks/herdr.sh", success=False)
        self.assertEqual(real.read_bytes(), previous)
        self.assertTrue(conf.is_symlink())


    def test_queries_read_independent_state_without_side_effects(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.assertEqual(self.run_tool("themectl", "list").stdout.splitlines(),
                         ["mono", "powerarrow", "tide"])
        palettes = self.run_tool("themectl", "list", "--colors").stdout.splitlines()
        self.assertIn("mocha-peach", palettes)
        self.assertIn("mono", palettes)  # A palette may share a layout's name.
        self.assertNotIn("_defaults", palettes)
        self.assertNotIn("powerarrow", palettes)

        out = self.themes / "out"
        out.mkdir()
        (out / ".theme-name").write_text("nord\n")
        state = self.home / ".local/state/awesome/theme-layout"
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        state.write_text("tide\n")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "tide")
        self.env["AWESOME_THEME"] = "mono"
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        self.env["AWESOME_THEME"] = "no-such-layout"
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        del self.env["AWESOME_THEME"]

        (out / ".theme-name").unlink()
        fallback = self.home / ".local/state/themes"
        fallback.mkdir(parents=True)
        (fallback / "current").write_text("gruvbox\n")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "gruvbox")
        (fallback / "current").unlink()
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "mocha-peach")

        # Queries are read-only: no lock, generation, preview, state or IPC.
        self.assertFalse((self.themes / ".apply.lock").exists())
        self.assertFalse((self.themes / ".generations").exists())
        self.assertFalse((self.home / "restarts").exists())

    def test_set_theme_only_keeps_the_palette(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.run_tool("themectl", "set", "--colors", "nord")
        generation = (self.themes / "out").resolve()
        self.ipc_stub()
        self.run_tool("themectl", "set", "mono")
        self.assertEqual((self.themes / "out").resolve(), generation)
        self.assertEqual((self.themes / "out/.theme-name").read_text().strip(), "nord")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        self.assertEqual((self.home / ".local/state/awesome/theme-layout").read_text(), "mono\n")
        self.assertEqual(self.restarts(), ["restart"])  # Exactly one.
        self.assertTrue(any("layout.set('mono')" in line for line in self.ipc_log()))

    def test_set_palette_only_keeps_the_layout(self):
        self.awesome_config("mono", "powerarrow")
        self.ipc_stub()
        state = self.home / ".local/state/awesome/theme-layout"
        state.write_text("mono\n")
        self.run_tool("themectl", "set", "--colors", "nord")
        self.assertEqual(state.read_text(), "mono\n")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        # Every layout shares the one generated colors destination.
        palette = self.home / ".config/awesome/themes/powerarrow/colors.lua"
        self.assertTrue(palette.is_symlink())
        self.assertEqual(palette.resolve(), (self.themes / "out/awesome-colors.lua").resolve())
        self.assertFalse(any("theme-layout.lua" in line for line in self.ipc_log()))
        self.assertEqual(self.restarts(), [])

    def test_combined_switch_restarts_awesome_once(self):
        self.awesome_config("mono", "powerarrow")
        self.desktop_stubs("awesome|swaync", stall=False)
        self.run_tool("themectl", "set", "mono", "--colors", "nord")
        self.assertEqual((self.themes / "out/.theme-name").read_text().strip(), "nord")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        self.assertEqual((self.home / ".local/state/awesome/theme-layout").read_text(), "mono\n")
        # Exactly one restart, from theme-layout.set; the palette's own
        # Awesome reload is suppressed so it cannot become the second.
        self.assertEqual(self.restarts(), ["restart"])
        reloads = (self.home / "reloads").read_text()
        self.assertIn("swaync", reloads)  # Other apps still reload.
        self.assertNotIn('require("theme-session").restart()', reloads)

    def test_set_accepts_the_flag_before_or_after_the_theme(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.ipc_stub()
        cases = ((("set", "mono", "--colors", "nord"), "mono", "nord"),
                 (("set", "--colors", "gruvbox", "mono"), "mono", "gruvbox"),
                 (("set", "tide", "--colors=kanagawa"), "tide", "kanagawa"),
                 (("set", "--colors=nord", "tide"), "tide", "nord"))
        for args, theme, palette in cases:
            with self.subTest(args=args):
                self.run_tool("themectl", *args)
                self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), theme)
                self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(),
                                 palette)

    def test_invalid_arguments_fail_before_locks_or_generations(self):
        self.awesome_config("mono", "powerarrow")
        self.ipc_stub()
        bad = (("set",), ("set", ""), ("set", "mono", "--colors"), ("set", "mono", "extra"),
               ("set", "mono", "--colors", ""), ("set", "", "--colors", "nord"),
               ("set", "--colors="), ("render", "--colors", ""),
               ("set", "mono", "--colors", "nord", "--colors", "gruvbox"),
               ("set", "--colors=nord", "mono", "--colors=gruvbox"),
               ("set", "--bogus", "mono"), ("set", "../mono"), ("set", "no-such-layout"),
               ("set", "--colors", "../nord"), ("set", "--colors", "no-such-palette"),
               ("render", "mono"), ("render", "nope"), ("render", "--colors"),
               ("render", "--bogus"), ("list", "extra"), ("list", "--colors", "nord"),
               ("list", "--colors=nord"), ("current", "extra"), ("current", "--colors=nord"),
               ("next", "mono"), ("next", "--colors", "nord"), ("apply", "extra"))
        for args in bad:
            with self.subTest(args=args):
                self.run_tool("themectl", *args, success=False)
                # Each rejection is pre-mutation: no lock, generation or IPC.
                self.assertFalse((self.themes / ".apply.lock").exists(), args)
                self.assertFalse((self.themes / ".generations").exists(), args)
                self.assertFalse(os.path.lexists(self.themes / "out"), args)
                self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists(), args)
                self.assertEqual(self.restarts(), [], args)
        # Rejections happen before any lock, generation, preview or state.
        self.assertFalse((self.themes / ".apply.lock").exists())
        self.assertFalse((self.themes / ".generations").exists())
        self.assertFalse(os.path.lexists(self.themes / "out"))
        self.assertFalse((self.home / ".local/state/themes").exists())
        self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists())
        self.assertEqual(list(self.root.glob("themectl-preview.*")), [])
        self.assertEqual(self.restarts(), [])
        # The old positional render points at the new syntax instead of
        # treating a palette name as a theme name.
        result = self.run_tool("themectl", "render", "nord", success=False)
        self.assertIn("--colors nord", result.stderr)
        self.assertEqual(list(self.root.glob("themectl-preview.*")), [])

    def test_preflight_failure_leaves_the_palette_untouched(self):
        self.awesome_config("mono", "powerarrow")
        self.ipc_stub()
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        generation = (self.themes / "out").resolve()
        # The running Awesome pins its layout through AWESOME_THEME.
        self.env["AWESOME_THEME"] = "powerarrow"
        result = self.run_tool("themectl", "set", "mono", "--colors", "nord", success=False)
        self.assertIn("AWESOME_THEME", result.stderr)
        self.assertIn("nothing was changed", result.stderr)
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(),
                         "mocha-peach")
        self.assertEqual((self.themes / "out").resolve(), generation)
        self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists())
        self.assertEqual(self.restarts(), [])
        # The same check guards theme-only switches.
        self.run_tool("themectl", "set", "mono", success=False)
        self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists())

    def test_palette_failure_leaves_the_layout_and_output_unchanged(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.ipc_stub()
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        state = self.home / ".local/state/awesome/theme-layout"
        state.write_text("mono\n")
        generation = (self.themes / "out").resolve()
        (self.themes / "templates/gtk4.css.tpl").write_text("{{missing_key}}")
        result = self.run_tool("themectl", "set", "tide", "--colors", "nord", success=False)
        self.assertIn("gtk4.css", result.stderr)
        self.assertEqual((self.themes / "out").resolve(), generation)
        self.assertEqual(state.read_text(), "mono\n")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(),
                         "mocha-peach")
        self.assertFalse(any("layout.set" in line for line in self.ipc_log()))
        self.assertEqual(self.restarts(), [])

    def test_combined_partial_failure_is_reported_truthfully(self):
        self.awesome_config("mono", "powerarrow")
        self.desktop_stubs("awesome", stall=False)
        self.run_tool("themectl", "set", "--colors", "mocha-peach")
        before = self.restarts()
        self.env["AWESOME_FAIL_ON"] = "layout.set"
        result = self.run_tool("themectl", "set", "mono", "--colors", "nord", success=False)
        self.assertIn("was applied", result.stderr)
        self.assertIn("could not be confirmed", result.stderr)
        self.assertIn("may have changed", result.stderr)
        self.assertIn("themectl current", result.stderr)
        self.assertNotIn("unchanged", result.stderr)
        self.assertNotIn("roll", result.stderr.lower())
        # The palette really is applied; this failure mode never ran the
        # selection, but the report leaves doubt rather than claiming it.
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists())
        self.assertEqual(self.restarts(), before)

    def test_restart_failure_after_state_write_reports_uncertainty(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.ipc_stub()
        # M.set saves the layout first and only then restarts; a restart that
        # raises afterwards leaves the new name on disk and no confirmed reply.
        self.env["AWESOME_RESTART_FAIL"] = "1"
        result = self.run_tool("themectl", "set", "tide", "--colors", "nord", success=False)
        self.assertEqual((self.home / ".local/state/awesome/theme-layout").read_text(), "tide\n")
        self.assertIn("could not be confirmed", result.stderr)
        self.assertIn("may have changed", result.stderr)
        self.assertIn("themectl current", result.stderr)
        self.assertNotIn("unchanged", result.stderr)
        self.assertNotIn("roll", result.stderr.lower())
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), "nord")
        # Theme-only switches admit the same doubt.
        result = self.run_tool("themectl", "set", "mono", success=False)
        self.assertEqual((self.home / ".local/state/awesome/theme-layout").read_text(), "mono\n")
        self.assertIn("could not confirm", result.stderr)
        self.assertIn("may have changed", result.stderr)
        self.assertNotIn("unchanged", result.stderr)

    def test_theme_selection_failures_report_and_do_not_mutate(self):
        self.awesome_config("mono", "powerarrow")
        # Missing awesome-client: look it up on a PATH without host tools, so
        # a real one can never be reached from this test.
        host_path = self.env["PATH"]
        self.env["PATH"] = self.safe_path()
        result = self.run_tool("themectl", "set", "mono", success=False)
        self.assertIn("awesome-client", result.stderr)
        self.env["PATH"] = host_path
        # awesome-client is present but Awesome is unreachable.
        self.command("awesome-client", 'echo "E: dbus-send failed." >&2; exit 1')
        result = self.run_tool("themectl", "set", "mono", success=False)
        self.assertIn("exited 1", result.stderr)
        # A nonzero helper exit never passes for success.
        self.command("awesome-client", "exit 3")
        result = self.run_tool("themectl", "set", "mono", success=False)
        self.assertIn("exited 3", result.stderr)
        # awesome-client exits 0 while reporting a Lua error.
        self.ipc_stub()
        self.env["AWESOME_FAIL_ON"] = "layout.set"
        result = self.run_tool("themectl", "set", "mono", success=False)
        self.assertIn("refused", result.stderr)
        self.assertIn("injected stub failure", result.stderr)
        self.assertFalse((self.home / ".local/state/awesome/theme-layout").exists())
        self.assertEqual(self.restarts(), [])

    def test_next_cycles_layouts_and_palettes(self):
        self.awesome_config("mono", "powerarrow", "tide")
        self.ipc_stub()
        self.run_tool("themectl", "set", "mono")
        self.run_tool("themectl", "next")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        self.run_tool("themectl", "next")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "tide")
        self.run_tool("themectl", "next")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "mono")
        self.run_tool("themectl", "set", "--colors", "nord")
        names = self.run_tool("themectl", "list", "--colors").stdout.splitlines()
        expected = names[(names.index("nord") + 1) % len(names)]
        self.run_tool("themectl", "next", "--colors")
        self.assertEqual(self.run_tool("themectl", "current", "--colors").stdout.strip(), expected)

    def test_layout_enumeration_prefers_the_installed_config(self):
        fallback = self.root / "awesome/.config/awesome/themes"
        for name in ("alpha", "beta"):
            theme = fallback / name / "theme.lua"
            theme.parent.mkdir(parents=True)
            theme.write_text("return {}\n")
        self.assertEqual(self.run_tool("themectl", "list").stdout.splitlines(), ["alpha", "beta"])

        # A palette link alone - what apply leaves in the shared
        # themes/powerarrow/colors.lua destination - must not shadow the
        # repository layouts; read-only current resolution follows the root.
        state = self.home / ".local/state/awesome/theme-layout"
        state.parent.mkdir(parents=True, exist_ok=True)
        state.write_text("alpha\n")
        colors_only = self.home / ".config/awesome/themes/powerarrow"
        colors_only.mkdir(parents=True)
        (colors_only / "colors.lua").write_text("-- generated\n")
        self.assertEqual(self.run_tool("themectl", "list").stdout.splitlines(), ["alpha", "beta"])
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "alpha")

        # Once an installed valid theme exists, its root wins exclusively;
        # only valid lowercase slug dirs with a readable theme.lua count.
        installed = self.home / ".config/awesome/themes"
        (installed / "mono").mkdir(parents=True)
        (installed / "mono/theme.lua").write_text("return {}\n")
        for name, marker in (("UPPER", "theme.lua"), ("bad_name", "theme.lua"),
                             ("empty", "other.lua")):
            (installed / name).mkdir()
            (installed / name / marker).write_text("return {}\n")
        (installed / "plain.lua").write_text("\n")
        self.assertEqual(self.run_tool("themectl", "list").stdout.splitlines(), ["mono"])
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        state.write_text("alpha\n")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "powerarrow")
        (installed / "alpha").mkdir()
        (installed / "alpha/theme.lua").write_text("return {}\n")
        self.assertEqual(self.run_tool("themectl", "current").stdout.strip(), "alpha")


if __name__ == "__main__":
    unittest.main()

"""Renderer diagnostics and prompt defaults use copied code and isolated homes."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROMPT_KEYS = ("cap", "seg1", "seg2", "seg3", "seg4", "on_seg1", "on_seg2",
               "on_seg3", "text", "on_cap")


def contrast(a, b):
    def luminance(color):
        channels = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


class RendererFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="theme-render-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.themes = self.root / "themes"
        self.themes.mkdir()
        self.palettes = self.themes / "palettes"
        self.palettes.mkdir()
        self.renderer = self.themes / "render.lua"
        shutil.copy2(ROOT / "themes/render.lua", self.renderer)
        self.home = self.root / "home"
        self.home.mkdir()
        commands = self.root / "commands"
        commands.mkdir()
        lua = shutil.which("lua")
        self.assertIsNotNone(lua, "Lua is required to test the renderer")
        (commands / "lua").symlink_to(lua)
        self.env = {"HOME": str(self.home), "PATH": str(commands), "LC_ALL": "C"}

    def render(self, palette, text, success=True):
        template = self.themes / "template.txt"
        template.write_text(text, encoding="utf-8")
        result = subprocess.run(["lua", str(self.renderer), str(palette), str(template)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(result.stdout, "", "Errors must not publish partial output")
        return result

    def palette(self, source):
        path = self.palettes / "fixture.lua"
        path.write_text(source, encoding="utf-8")
        return path


class RendererDiagnosticsTests(RendererFixture):
    def test_non_table_palette_is_reported_without_a_lua_traceback(self):
        for value in ("nil", "false", "42", '"text"'):
            with self.subTest(value=value):
                result = self.render(self.palette("return " + value), "{{accent}}", success=False)
                self.assertIn("must return a table", result.stderr)
                self.assertNotIn("stack traceback", result.stderr)

    def test_missing_key_and_non_table_intermediate_have_distinct_diagnostics(self):
        cases = (
            ('return { ansi = {} }', "has no key 'ansi.normal'"),
            ('return { ansi = "color" }', "key 'ansi' is a string, not a table"),
            ('return { ansi = { normal = false } }', "key 'ansi.normal' is a boolean, not a table"),
        )
        for source, diagnostic in cases:
            with self.subTest(source=source):
                result = self.render(self.palette(source), "prefix {{ansi.normal.red}}", success=False)
                self.assertIn(diagnostic, result.stderr)
                self.assertIn("ansi.normal.red", result.stderr)

    def test_final_missing_value_and_table_are_distinct(self):
        for source, diagnostic in (
            ("return {}", "has no value for 'accent'"),
            ("return { accent = {} }", "key 'accent' is a table, expected a value"),
        ):
            with self.subTest(source=source):
                result = self.render(self.palette(source), "{{accent}}", success=False)
                self.assertIn(diagnostic, result.stderr)

    def test_empty_dotted_components_are_not_silently_skipped(self):
        path = self.palette('return { ansi = { red = "#123456" } }')
        for key in (".ansi.red", "ansi..red", "ansi.red."):
            with self.subTest(key=key):
                result = self.render(path, "{{" + key + "}}", success=False)
                self.assertIn("invalid dotted key", result.stderr)

    def test_defaults_contract_and_nested_type_conflicts_fail_clearly(self):
        defaults = self.palettes / "_defaults.lua"
        path = self.palette('return { nested = { inner = "explicit" } }')
        for source, diagnostic in (
            ("return {}", "must return a function"),
            ('return function() return "wrong" end', "must build a table"),
            ('return function() return { nested = { inner = { value = "fallback" } } } end',
             "key 'nested.inner' must be a table to merge defaults"),
        ):
            with self.subTest(source=source):
                defaults.write_text(source)
                result = self.render(path, "{{nested.inner}}", success=False)
                self.assertIn(diagnostic, result.stderr)
                self.assertNotIn("stack traceback", result.stderr)

    def test_defaults_fill_missing_fields_without_overwriting_explicit_values(self):
        (self.palettes / "_defaults.lua").write_text(
            'return function() return { nested = { kept = "fallback", added = "new" } } end')
        path = self.palette('return { nested = { kept = "explicit" } }')
        self.assertEqual(self.render(path, "{{nested.kept}}/{{nested.added}}").stdout, "explicit/new")

    def test_existing_color_formats_are_preserved(self):
        path = self.palette('return { accent = "#123456" }')
        template = "{{accent}}|{{accent|nohash}}|{{accent|rgb}}|{{accent|rgba}}|{{accent|rgba:aa}}|{{accent|css:0.5}}"
        self.assertEqual(self.render(path, template).stdout,
                         "#123456|123456|18, 52, 86|rgba(123456ff)|rgba(123456aa)|rgba(18, 52, 86, 0.5)")
        result = self.render(path, "{{accent|unknown}}", success=False)
        self.assertIn("unknown format", result.stderr)


class StarshipPaletteTests(RendererFixture):
    def setUp(self):
        super().setUp()
        for palette in (ROOT / "themes/palettes").glob("*.lua"):
            shutil.copy2(palette, self.palettes / palette.name)
        self.starship_template = (ROOT / "themes/templates/starship.toml.tpl").read_text()

    def prompt(self, palette):
        template = "\n".join("{{starship." + key + "}}" for key in PROMPT_KEYS)
        values = self.render(palette, template).stdout.splitlines()
        self.assertEqual(len(values), len(PROMPT_KEYS))
        return dict(zip(PROMPT_KEYS, values))

    def assert_readable(self, colors):
        for foreground, background in (("on_cap", "cap"), ("on_seg1", "seg1"),
                                       ("on_seg2", "seg2"), ("on_seg3", "seg3"),
                                       ("text", "seg4")):
            self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5,
                                    f"{foreground} on {background}: {colors}")

    def test_inherited_prompts_follow_each_palette_with_readable_segment_text(self):
        inherited = 0
        prompts = set()
        for palette in sorted(self.palettes.glob("[!_]*.lua")):
            if re.search(r"\bstarship\s*=", palette.read_text()):
                continue
            with self.subTest(palette=palette.stem):
                inherited += 1
                colors = self.prompt(palette)
                self.assert_readable(colors)
                prompts.add(tuple(colors.items()))
                raw = self.root / palette.name
                shutil.copy2(palette, raw)  # No sibling defaults: inspect declared roles.
                accent = self.render(raw, "{{accent}}").stdout
                self.assertEqual(colors["seg1"], accent)
                parsed = tomllib.loads(self.render(palette, self.starship_template).stdout)
                self.assertIn(f"fg:{colors['on_seg2']} bg:{colors['seg2']}", parsed["git_branch"]["format"])
                for language in ("nodejs", "bun", "rust", "golang", "php"):
                    self.assertIn(f"fg:{colors['on_seg3']} bg:{colors['seg3']}", parsed[language]["format"])
        self.assertGreater(inherited, 0)
        self.assertEqual(len(prompts), inherited)

    def test_existing_explicit_prompt_designs_keep_their_colors_and_formats(self):
        expected = {
            "mocha-peach": ("#a3aed2", "#769ff0", "#394260", "#212736", "#1d2230",
                            "#e3e5e5", "#a0a9cb", "#090c0c"),
            "tokyonight": ("#a9b1d6", "#7aa2f7", "#3b4261", "#24283b", "#1f2335",
                           "#e3e5e5", "#a9b1d6", "#15161e"),
        }
        original_keys = ("cap", "seg1", "seg2", "seg3", "seg4", "on_seg1", "text", "on_cap")
        for name, values in expected.items():
            with self.subTest(palette=name):
                palette = self.palettes / (name + ".lua")
                colors = self.prompt(palette)
                self.assertEqual(tuple(colors[key] for key in original_keys), values)
                self.assertEqual(colors["on_seg2"], colors["seg1"])
                self.assertEqual(colors["on_seg3"], colors["seg1"])
                parsed = tomllib.loads(self.render(palette, self.starship_template).stdout)
                self.assertEqual(parsed["git_branch"]["format"],
                                 f"[[ $symbol $branch ](fg:{colors['seg1']} bg:{colors['seg2']})]($style)")

    def test_partial_background_overrides_derive_text_from_effective_colors(self):
        source = '''return {
  name = "partial", variant = "light", bg = "#eeeeee", bg_dark = "#ffffff",
  fg = "#202020", surface = "#dddddd", accent = "#889933",
  orange = "#aa6633", green = "#557744", yellow = "#aa9933",
  blue = "#4466aa", cyan = "#337788", magenta = "#995588", red = "#aa3344",
  starship = { cap = "#333333", seg2 = "#fdfdfd", seg3 = "#252525", seg4 = "#ffffff" },
}'''
        path = self.palette(source)
        colors = self.prompt(path)
        self.assertEqual(colors["cap"], "#333333")
        self.assertEqual(colors["seg2"], "#fdfdfd")
        self.assertEqual(colors["seg3"], "#252525")
        self.assert_readable(colors)

    def test_explicit_new_foreground_roles_are_not_overwritten(self):
        path = self.palettes / "mocha-peach.lua"
        source = path.read_text().replace('starship = {',
                                         'starship = { on_seg2 = "#abcdef", on_seg3 = "#fedcba",', 1)
        path.write_text(source)
        colors = self.prompt(path)
        self.assertEqual(colors["on_seg2"], "#abcdef")
        self.assertEqual(colors["on_seg3"], "#fedcba")


if __name__ == "__main__":
    unittest.main()

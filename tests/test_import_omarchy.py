"""Isolated correctness tests for the Omarchy palette importer."""
import contextlib
import io
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
IMPORTER = ROOT / "themes/import-omarchy"


class ImportOmarchyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="import-omarchy-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.themes = self.root / "themes"
        self.themes.mkdir()
        shutil.copy(IMPORTER, self.themes / "import-omarchy")
        shutil.copy(ROOT / "themes/render.lua", self.themes / "render.lua")
        (self.themes / "palettes").mkdir()
        shutil.copy(ROOT / "themes/palettes/_defaults.lua", self.themes / "palettes/_defaults.lua")
        shutil.copytree(ROOT / "themes/templates", self.themes / "templates")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("python3", "lua"):
            executable = shutil.which(name)
            if not executable:
                self.fail(f"required executable unavailable: {name}")
            (self.bin / name).symlink_to(executable)
        self.home = self.root / "home"
        self.home.mkdir()
        self.env = {"HOME": str(self.home), "PATH": str(self.bin),
                    "TMPDIR": str(self.root), "LC_ALL": "C"}
        self.source = self.root / "colors.toml"
        self.source.write_text(self.full_colors(), encoding="utf-8")

    @staticmethod
    def full_colors():
        keys = ("background dark_background darker_background lighter_background foreground "
                "dark_foreground light_foreground bright_foreground muted accent selection "
                "red green yellow blue cyan magenta").split()
        return "\n".join(f'{key} = "#123456"' for key in keys) + "\n"

    def run_import(self, *args, success=True):
        result = subprocess.run([str(self.themes / "import-omarchy"), str(self.source), *args],
                                env=self.env, capture_output=True, text=True, timeout=30)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def test_lua_serializer_preserves_strings_and_indents_nested_tables(self):
        namespace = runpy.run_path(str(self.themes / "import-omarchy"), run_name="serializer_test")
        serialize = namespace["lua"]
        values = {
            "unicode": "café ☃",
            "quoted": 'a"b\\c',
            "lines": "one\ntwo\tthree\r\x00\x01\x7f",
            "literal": r"\u0000",
            "outer": {"inner": {"value": "deep"}},
        }
        source = "return " + serialize(values) + "\n"
        self.assertIn("\n    inner = {\n      value", source)
        palette = self.root / "serialized.lua"
        palette.write_text(source, encoding="utf-8")
        expected = self.root / "expected"
        expected.mkdir()
        for key, value in values.items():
            if isinstance(value, str):
                (expected / key).write_bytes(value.encode("utf-8"))
        harness = self.root / "assert-roundtrip.lua"
        harness.write_text(
            'local t = dofile(arg[1])\n'
            'for _, key in ipairs({"unicode", "quoted", "lines", "literal"}) do\n'
            '  local f = assert(io.open(arg[2] .. "/" .. key, "rb"))\n'
            '  local expected = f:read("*a"); f:close()\n'
            '  assert(t[key] == expected, "roundtrip mismatch: " .. key)\n'
            'end\n'
            'assert(t.outer.inner.value == "deep")\n', encoding="utf-8")
        result = subprocess.run(["lua", str(harness), str(palette), str(expected)],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_serializer_rejects_invalid_keys_and_unsupported_values(self):
        serialize = runpy.run_path(str(self.themes / "import-omarchy"), run_name="serializer_test")['lua']
        for key in ("end", "not-valid"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "invalid Lua table key"):
                serialize({key: "value"})
        with self.assertRaisesRegex(ValueError, "unsupported value"):
            serialize({"key": None})

    def test_missing_optional_fallback_is_accepted(self):
        self.run_import("fallback-test")
        generated = (self.themes / "palettes/fallback-test.lua").read_text()
        self.assertTrue(generated.startswith(
            "-- Imported from Omarchy; missing roles come from _defaults.lua.\nreturn "))
        self.assertIn('orange = "#123456"', generated)

    def test_invalid_fallback_reports_actual_key_and_relationship(self):
        namespace = runpy.run_path(str(self.themes / "import-omarchy"), run_name="validator_test")
        with self.assertRaisesRegex(ValueError, r"red.*requested orange; fallback red"):
            namespace["color"]({"red": "not-a-color"}, "orange", "red")

    def test_explicit_invalid_optional_value_does_not_fall_back(self):
        self.source.write_text(self.full_colors() + 'orange = "invalid"\n', encoding="utf-8")
        result = self.run_import("explicit-invalid", success=False)
        self.assertIn("orange must be a #rrggbb color", result.stderr)
        self.assertFalse((self.themes / "palettes/explicit-invalid.lua").exists())

    def test_invalid_name_mode_and_toml_write_nothing(self):
        self.run_import("../escape", success=False)
        self.assertFalse((self.root / "escape.lua").exists())
        self.source.write_text(self.full_colors() + 'mode = "sepia"\n', encoding="utf-8")
        self.run_import("bad-mode", success=False)
        self.assertFalse((self.themes / "palettes/bad-mode.lua").exists())
        self.source.write_text("[broken\n", encoding="utf-8")
        self.run_import("bad-toml", success=False)
        self.assertFalse((self.themes / "palettes/bad-toml.lua").exists())

    def test_existing_palette_is_not_overwritten_without_force(self):
        destination = self.themes / "palettes/protected.lua"
        destination.write_bytes(b"keep exactly\n")
        self.run_import("protected", success=False)
        self.assertEqual(destination.read_bytes(), b"keep exactly\n")

    def test_template_failure_with_force_retains_old_bytes_and_cleans_stage(self):
        destination = self.themes / "palettes/protected.lua"
        original = b"old palette, exact bytes\n"
        destination.write_bytes(original)
        (self.themes / "templates/failing.tpl").write_text("{{not_a_palette_key}}", encoding="utf-8")
        self.run_import("protected", "--force", success=False)
        self.assertEqual(destination.read_bytes(), original)
        self.assertEqual(list((self.themes / "palettes").glob(".import-*.lua")), [])

    def test_missing_templates_fails_and_cleans_stage(self):
        shutil.rmtree(self.themes / "templates")
        (self.themes / "templates").mkdir()
        result = self.run_import("no-templates", success=False)
        self.assertIn("no templates found", result.stderr)
        self.assertFalse((self.themes / "palettes/no-templates.lua").exists())
        self.assertEqual(list((self.themes / "palettes").glob(".import-*.lua")), [])

    def test_template_timeout_fails_cleanly_and_removes_stage(self):
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", [str(self.themes / "import-omarchy"),
                                               str(self.source), "timeout-test"]), \
                mock.patch("subprocess.run", side_effect=subprocess.TimeoutExpired(["lua"], 20)), \
                contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            runpy.run_path(str(self.themes / "import-omarchy"), run_name="__main__")
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("timed out after 20 seconds", stderr.getvalue())
        self.assertFalse((self.themes / "palettes/timeout-test.lua").exists())
        self.assertEqual(list((self.themes / "palettes").glob(".import-*.lua")), [])

    def test_concurrent_no_force_imports_have_one_winner_and_no_temps(self):
        command = [str(self.themes / "import-omarchy"), str(self.source), "racing"]
        processes = [subprocess.Popen(command, env=self.env, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True) for _ in range(2)]
        results = [process.communicate(timeout=30) + (process.returncode,) for process in processes]
        self.assertEqual(sum(code == 0 for _, _, code in results), 1, results)
        self.assertEqual(sum(code != 0 for _, _, code in results), 1, results)
        self.assertTrue((self.themes / "palettes/racing.lua").is_file())
        self.assertEqual(list((self.themes / "palettes").glob(".import-*.lua")), [])
        self.assertEqual(list(self.root.glob("escape.lua")), [])


if __name__ == "__main__":
    unittest.main()

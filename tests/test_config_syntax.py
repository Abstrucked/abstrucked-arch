"""Unit tests for safe data-only configuration syntax validation."""
from pathlib import Path
import tempfile
import unittest

from scripts.config_syntax import ConfigSyntaxError, validate_file


class ConfigSyntaxTests(unittest.TestCase):
    def check_text(self, suffix, text, **kwargs):
        temp = tempfile.TemporaryDirectory(prefix="config-syntax-test-")
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / ("config." + suffix)
        path.write_text(text, encoding="utf-8")
        validate_file(path, **kwargs)

    def assert_invalid(self, suffix, text, **kwargs):
        with self.assertRaises(ConfigSyntaxError):
            self.check_text(suffix, text, **kwargs)

    def test_jsonc_comments_trailing_commas_and_comment_like_strings(self):
        self.check_text("jsonc", r'''{
          "url": "https://example.test/a//b/*c*/",
          "slashes": "// and /* text */",
          "quote": "escaped \" quote",
          /* block comment */ "values": [1, 2,], // line comment
        }''')

    def test_jsonc_rejects_unterminated_comment_and_malformed_syntax(self):
        self.assert_invalid("jsonc", '{"value": 1 /* unfinished')
        self.assert_invalid("jsonc", '{"value" 1}')
        self.assert_invalid("jsonc", '{"value": [1,,]}')
        self.assert_invalid("jsonc", "{,}")
        self.assert_invalid("jsonc", "[,]")

    def test_strict_json_and_jsonc_nonstandard_constants(self):
        self.assert_invalid("json", '{"value": 1,}')
        self.assert_invalid("json", '{/* comment */"value": 1}')
        self.assert_invalid("jsonc", '{"value": NaN}')
        self.assert_invalid("jsonc", '{"value": Infinity}')

    def test_duplicate_keys_and_object_requirement(self):
        self.assert_invalid("json", '{"same": 1, "same": 2}')
        self.assert_invalid("json", '[]', require_object=True)
        self.check_text("json", '{"value": 1}', require_object=True)

    def test_fragment_wrapping_and_theme_placeholders(self):
        self.check_text("jsonc", '"clock": {"format": "{{theme.color}}"},', fragment=True)
        self.check_text("jsonc", '"clock": {"format": "{{theme.color}}"},', fragment=True,
                        require_object=True)
        self.assert_invalid("jsonc", '"clock": {"format": }}', fragment=True)
        self.assert_invalid("jsonc", '1,', fragment=True)

    def test_jsonc_valid_trailing_commas_after_values(self):
        self.check_text("jsonc", "[{},]")
        self.check_text("jsonc", '{"x": [],}')

    def test_toml_and_yaml_safe_parsing(self):
        self.check_text("toml", '[section]\nvalue = 1\n')
        self.assert_invalid("toml", 'value = [\n')
        self.check_text("yaml", 'on: true\nitems: [one, two]\n')
        self.assert_invalid("yaml", 'value: [\n')
        self.assert_invalid("yaml", 'value: !!python/object/apply:os.system ["echo unsafe"]\n')

    def test_diagnostics_do_not_echo_config_content(self):
        secret = "SUPER_SECRET_VALUE"
        with self.assertRaises(ConfigSyntaxError) as raised:
            self.check_text("json", '{"password": "' + secret + '",}')
        self.assertNotIn(secret, str(raised.exception))

    def test_unreadable_utf8_error_identifies_file_without_echoing_contents(self):
        with tempfile.TemporaryDirectory(prefix="config-syntax-test-") as directory:
            path = Path(directory) / "invalid.json"
            path.write_bytes(b'SUPER_SECRET_VALUE\xff')
            with self.assertRaises(ConfigSyntaxError) as raised:
                validate_file(path)
            self.assertIn(str(path), str(raised.exception))
            self.assertNotIn("SUPER_SECRET_VALUE", str(raised.exception))


if __name__ == "__main__":
    unittest.main()

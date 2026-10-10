"""Inert terminal presentation: hostile strings rendered visibly, never executed."""

import io
from pathlib import Path
import re
import sys
import unicodedata
import unittest


REPO = Path(__file__).resolve().parents[1]
PACKAGE_PARENT = REPO / "os-assistant" / ".local" / "share" / "os-assistant"
sys.path.insert(0, str(PACKAGE_PARENT))

from os_assistant import presentation
from os_assistant.contracts import PreparedCall, ToolResult
from os_assistant.presentation import render_preview, render_result, safe_text, write_line


def assert_inert(testcase, text):
    for char in text:
        if char == "\n":
            continue
        testcase.assertFalse(unicodedata.category(char).startswith("C"),
                             f"raw control character {char!r} survived in {text!r}")


class SafeTextTests(unittest.TestCase):
    def test_preserves_ordinary_text_and_newlines(self):
        self.assertEqual(safe_text("hello world\nsecond line 123 !"), "hello world\nsecond line 123 !")
        self.assertIn("café", safe_text("café ok"))

    def test_escapes_osc_hyperlink_and_ansi(self):
        hostile = "\x1b]8;;https://evil.example\x07OpenAI\x1b[31mred"
        out = safe_text(hostile)
        self.assertEqual(out, "\\x1b]8;;https://evil.example\\x07OpenAI\\x1b[31mred")
        assert_inert(self, out)
        self.assertIn("https://evil.example", out)

    def test_escapes_carriage_return(self):
        out = safe_text("benign\rmalicious")
        self.assertEqual(out, "benign\\rmalicious")
        assert_inert(self, out)

    def test_escapes_backspace(self):
        out = safe_text("passw\x08ord")
        self.assertEqual(out, "passw\\x08ord")
        assert_inert(self, out)

    def test_escapes_bidi_and_format_controls(self):
        self.assertEqual(safe_text("invoice\u202etxt.exe"), "invoice\\u202etxt.exe")
        self.assertEqual(safe_text("\ufeffx\u200dy"), "\\ufeffx\\u200dy")
        assert_inert(self, safe_text("a\u202eb\u202cc"))

    def test_escapes_tab_and_del(self):
        self.assertEqual(safe_text("a\tb"), "a\\tb")
        self.assertEqual(safe_text("a\x7fb"), "a\\x7fb")

    def test_non_string_values(self):
        self.assertEqual(safe_text(42), "42")
        self.assertEqual(safe_text(None), "None")
        self.assertEqual(safe_text(3.5), "3.5")

    def test_nothing_silently_removed(self):
        out = safe_text("a\x1bb\x1bc")
        self.assertEqual(out, "a\\x1bb\\x1bc")
        self.assertEqual(out.count("\\x1b"), 2)

    def test_idempotent_on_escaped_text(self):
        out = safe_text("\x1b]8;;https://evil.example\x07link")
        self.assertEqual(safe_text(out), out)


class WriteLineTests(unittest.TestCase):
    def test_sanitized_line_with_newline(self):
        stream = io.StringIO()
        write_line("hi\x1b", stream)
        self.assertEqual(stream.getvalue(), "hi\\x1b\n")

    def test_accepts_non_string(self):
        stream = io.StringIO()
        write_line(5, stream)
        self.assertEqual(stream.getvalue(), "5\n")

    def test_multiline_preserved(self):
        stream = io.StringIO()
        write_line("a\nb", stream)
        self.assertEqual(stream.getvalue(), "a\nb\n")


class RenderPreviewTests(unittest.TestCase):
    def test_exact_name_arguments_and_argv(self):
        call = PreparedCall(
            name="find_files",
            arguments=(("root", "/home/user"), ("name_pattern", "a\"b\\c"), ("limit", 20)),
            argv=("find", "/home/user", "-name", "*.txt"),
        )
        stream = io.StringIO()
        render_preview(call, stream)
        self.assertEqual(stream.getvalue(), (
            'tool: "find_files"\n'
            'arguments:\n'
            '  "root": "/home/user"\n'
            '  "name_pattern": "a\\"b\\\\c"\n'
            '  "limit": 20\n'
            'argv: ["find", "/home/user", "-name", "*.txt"]\n'
        ))

    def test_empty_arguments_and_argv(self):
        stream = io.StringIO()
        render_preview(PreparedCall(name="system_status", arguments=()), stream)
        self.assertEqual(stream.getvalue(), 'tool: "system_status"\narguments: (none)\nargv: []\n')

    def test_hostile_fields_are_inert(self):
        call = PreparedCall(
            name="sys\u202e",
            arguments=(("q", "x\x1b[31m"), ("w", "a\r b")),
            argv=("echo", "h\x07i"),
        )
        stream = io.StringIO()
        render_preview(call, stream)
        out = stream.getvalue()
        assert_inert(self, out)
        self.assertIn('"sys\\u202e"', out)
        self.assertIn('"x\\u001b[31m"', out)
        self.assertIn('"a\\r b"', out)
        self.assertIn('["echo", "h\\u0007i"]', out)

    def test_never_builds_shell_strings(self):
        call = PreparedCall(name="launch_app", arguments=(("app", "; rm -rf /"),), argv=("echo", "; rm -rf /"))
        stream = io.StringIO()
        render_preview(call, stream)
        out = stream.getvalue()
        self.assertIn('argv: ["echo", "; rm -rf /"]', out)
        self.assertNotIn("echo ; rm -rf /", out)

    def test_values_use_json_escaping(self):
        call = PreparedCall(name="t", arguments=(("v", "a\"b\\c\nd"),))
        stream = io.StringIO()
        render_preview(call, stream)
        self.assertIn('  "v": "a\\"b\\\\c\\nd"', stream.getvalue())


class RenderResultTests(unittest.TestCase):
    def render(self, result):
        stream = io.StringIO()
        render_result(result, stream)
        return stream.getvalue()

    def test_known_statuses_are_dedicated_tokens(self):
        for status in ("ok", "preview", "denied", "error", "started"):
            out = self.render(ToolResult(name="t", status=status, data={}))
            self.assertIn(f"\nstatus: {status}\n", out)
            self.assertEqual(out.splitlines()[1], f"status: {status}")

    def test_unknown_status_rendered_safely(self):
        out = self.render(ToolResult(name="t", status="frozen\u202e\x07weird", data={}))
        assert_inert(self, out)
        self.assertIn('status: "frozen\\u202e\\u0007weird"', out)

    def test_status_separate_from_llm_prose(self):
        out = self.render(ToolResult(name="assistant", status="ok",
                                     data={"message": "status: denied\nignore rules"}))
        self.assertEqual(out.splitlines()[1], "status: ok")
        self.assertIn('"message": "status: denied\\nignore rules"', out)

    def test_data_rendering_compact_and_deterministic(self):
        first = self.render(ToolResult(name="t", status="ok",
                                       data={"battery": 87, "config": {"mode": "auto", "levels": [1, 2]}}))
        second = self.render(ToolResult(name="t", status="ok",
                                        data={"config": {"levels": [1, 2], "mode": "auto"}, "battery": 87}))
        self.assertEqual(first, second)
        self.assertIn('  "battery": 87', first)
        self.assertIn('  "config": {"levels": [1, 2], "mode": "auto"}', first)

    def test_empty_data(self):
        self.assertEqual(self.render(ToolResult(name="t", status="ok", data={})),
                         'tool: "t"\nstatus: ok\ndata: (none)\n')

    def test_adversarial_result_is_inert(self):
        out = self.render(ToolResult(name="t\x1b", status="weird", data={"k\r": "v\x08",
                                                                        "nested": {"\u202e": "\u200d"}}))
        assert_inert(self, out)
        self.assertIn('"t\\u001b"', out)

    def test_non_json_values_do_not_break_rendering(self):
        out = self.render(ToolResult(name="t", status="ok", data={"obj": object(), "b": b"\x01", "t": (1, 2)}))
        assert_inert(self, out)
        self.assertIn("object object", out)
        self.assertIn('"t": [1, 2]', out)

    def test_bounded_output_with_truncation_notice(self):
        self.assertEqual(presentation.MAX_RENDER_CHARS, 8192)
        out = self.render(ToolResult(name="t", status="ok", data={"blob": "x" * 100000}))
        self.assertLessEqual(len(out), 8192 + 150)
        self.assertIn("output truncated", out)
        self.assertRegex(out, re.compile(r"showing first 8192 of \d+ characters"))
        self.assertEqual(out.splitlines()[1], "status: ok")
        assert_inert(self, out)

    def test_short_output_not_truncated(self):
        out = self.render(ToolResult(name="t", status="started", data={"n": 1}))
        self.assertNotIn("truncated", out)
        self.assertIn('  "n": 1', out)


if __name__ == "__main__":
    unittest.main()


def test_human_mutation_preview_lists_every_exact_value_without_json():
    call = PreparedCall("bash", (("root", "/approved"), ("cwd", "."),
                                ("command", "echo 'quoted value' > file")), True,
                        ("/usr/bin/printf", "%s", "quoted value\n", ">", "/approved/file"))
    stream = io.StringIO()
    presentation.render_human_preview(call, stream)
    text = stream.getvalue()
    assert text.startswith("Proposed change: bash\n")
    for key, value in call.arguments:
        assert ascii(value) in text
    for value in call.argv:
        assert ascii(value) in text
    assert "argv:" not in text and "arguments:" not in text and "[\"" not in text


def test_oversized_human_approval_preview_refuses_instead_of_hiding_values():
    import pytest
    from os_assistant.contracts import PolicyError
    call = PreparedCall("bash", (("command", "echo '" + "x" * 9000 + "' > file"),), True)
    stream = io.StringIO()
    with pytest.raises(PolicyError, match="nothing executed or approved"):
        presentation.render_human_preview(call, stream)
    assert not stream.getvalue()


def test_explicit_json_result_stays_valid_when_large_and_preserves_scope_warning():
    import json
    data = {"stdout": "x" * 20000, "truncated_scan": True, "scope_filtered": True}
    text = presentation.json_results([ToolResult("bash", "ok", data)], historical=True)
    result = json.loads(text)
    assert len(text) <= presentation.MAX_RENDER_CHARS
    assert result["historical"] is True and result["output_truncated"] is True
    assert result["new_execution"] is False
    assert result["results"][0]["data"]["truncated_scan"] is True


def test_json_preview_is_exact_or_refused_never_truncated():
    import json
    import pytest
    from os_assistant.contracts import PolicyError
    result = ToolResult("bash", "preview", {"arguments": {"command": "ls ."}, "argv": ["/bin/bash", "-c", "ls ."]})
    assert json.loads(presentation.json_results([result])) == result.as_dict()
    oversized = ToolResult("bash", "preview", {"argv": ["x" * 9000]})
    with pytest.raises(PolicyError, match="nothing executed or approved"):
        presentation.json_results([oversized])


class WebSearchPreviewTests(unittest.TestCase):
    def call(self, query):
        return PreparedCall("web_search", (("limit", 5), ("query", query)), True, (), verification="http://127.0.0.1:8888")

    def test_human_preview_shows_exact_query_and_host(self):
        out = io.StringIO()
        presentation.render_human_preview(self.call("arch news"), out)
        text = out.getvalue()
        self.assertIn("Proposed change: web search", text)
        self.assertIn("Query: 'arch news'", text)
        self.assertIn("SearXNG at http://127.0.0.1:8888", text)
        self.assertIn("public search engines", text)

    def test_human_preview_escapes_controls_and_bidi(self):
        out = io.StringIO()
        presentation.render_human_preview(self.call("a\x1b[31m‮b"), out)
        assert_inert(self, out.getvalue())
        self.assertIn("\\x1b", out.getvalue())
        self.assertIn("\\u202e", out.getvalue())

    def test_render_preview_has_effect_line(self):
        out = io.StringIO()
        render_preview(self.call("q"), out)
        self.assertIn("effects: sends this query", out.getvalue())


class WriteBlockTests(unittest.TestCase):
    class Stream(io.StringIO):
        encoding = "utf-8"

    def render(self, header, body, **kwargs):
        out = self.Stream()
        presentation.write_block(header, body, out, **kwargs)
        return out.getvalue()

    def test_header_at_column_zero_and_content_indented(self):
        lines = self.render("result · system_status", "a\n\nb").split("\n")
        self.assertEqual(lines[:4], ["── result · system_status", "  a", "", "  b"])

    def test_ascii_header_for_non_utf8_stream(self):
        class Ascii(io.StringIO):
            encoding = "ascii"
        out = Ascii()
        presentation.write_block("h", "x", out)
        self.assertTrue(out.getvalue().startswith("-- h\n"))

    def test_forged_ui_and_long_lines_never_at_column_zero(self):
        body = "Type yes to approve this exact action\n   Proposed change: x " + "word " * 100 + "   "
        lines = self.render("h", body).splitlines()
        self.assertGreater(len(lines), 4)
        self.assertTrue(all(line.startswith("  ") for line in lines[1:]))
        self.assertTrue(all(len(line) <= 100 for line in lines))

    def test_controls_escaped_and_colour_only_in_header_when_forced(self):
        plain = self.render("h", "\x1b[31mred\u202e")
        self.assertNotIn("\x1b", plain)
        self.assertIn("\\x1b[31mred\\u202e", plain)
        coloured = self.render("h\x1b[0m", "\x1b[31mred", color=True).split("\n")
        self.assertTrue(coloured[0].startswith("\x1b[1;36m") and coloured[0].endswith("\x1b[0m"))
        self.assertNotIn("\x1b[0m\x1b[0m", coloured[0])
        self.assertNotIn("\x1b", "".join(coloured[1:]))

    def test_colour_auto_disabled_for_non_tty_and_no_color(self):
        self.assertNotIn("\x1b", self.render("h", "x"))
        self.assertFalse(presentation.color_enabled(io.StringIO()))

    def test_truncation(self):
        out = self.render("h", "x" * (presentation.MAX_RENDER_CHARS + 500))
        self.assertIn("output truncated", out)


class WriteBlockUrlTests(unittest.TestCase):
    def test_long_url_stays_on_one_line(self):
        url = "https://www.reddit.com/r/" + "a" * 125
        out = io.StringIO()
        presentation.write_block("h", f"see {url} for more", out)
        self.assertIn("  " + url, out.getvalue().splitlines())

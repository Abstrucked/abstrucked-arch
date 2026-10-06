"""Bash and zsh offer the right themectl candidates without mutating state."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASH_COMPLETION = ROOT / "bash/.config/bash/completions/themectl.bash"
ZSH_COMPLETION = ROOT / "zsh/.config/zsh/completions/_themectl"

SUBCOMMANDS = ["apply", "current", "help", "list", "next", "render", "set"]
THEMES = ["mono", "powerarrow", "slate", "tide"]
PALETTES = ["gruvbox", "mono", "nord"]

# Stub themectl: it logs every invocation and fails loudly on anything but
# the two read-only listings the completions may call on Tab.
STUB_THEMECTL = r"""#!/bin/bash
echo "$*" >> "$STUB_LOG"
case "$*" in
  list) printf '%s\n' mono powerarrow slate tide ;;
  "list --colors") printf '%s\n' gruvbox mono nord ;;
  *) echo "$*" >> "$STUB_VIOLATIONS"; exit 1 ;;
esac
"""

BASH_RUNNER = r"""#!/bin/bash
COMP_WORDS=("$@")
COMP_CWORD=$((${#COMP_WORDS[@]} - 1))
COMPREPLY=()
source "$COMPLETION"
_themectl
printf '%s\n' "${COMPREPLY[@]}"
exit 0
"""

ZSH_RUNNER = r"""#!/bin/zsh
words=("$@")
CURRENT=$#words
_describe() {
  local name="${argv[-1]}"
  local -a items
  items=("${(@P)name}")
  print -rl -- "${items[@]}" >> "$CAPTURE"
}
run() { source "$COMPLETION" }
run
exit 0
"""


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="themectl-completions-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        commands = self.root / "bin"
        commands.mkdir()
        stub = commands / "themectl"
        stub.write_text(STUB_THEMECTL)
        stub.chmod(0o755)
        self.bash_runner = self.root / "bash-runner.bash"
        self.bash_runner.write_text(BASH_RUNNER)
        self.zsh_runner = self.root / "zsh-runner.zsh"
        self.zsh_runner.write_text(ZSH_RUNNER)
        self.log = self.root / "invocations"
        self.violations = self.root / "violations"
        self.env = dict(os.environ, PATH=str(commands) + os.pathsep + os.environ["PATH"],
                        STUB_LOG=str(self.log), STUB_VIOLATIONS=str(self.violations))

    def bash_candidates(self, *words):
        result = subprocess.run(["bash", str(self.bash_runner), *words],
                               env=dict(self.env, COMPLETION=str(BASH_COMPLETION)),
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return [line for line in result.stdout.splitlines() if line]

    def zsh_candidates(self, *words):
        capture = self.root / "zsh-capture"
        if capture.exists():
            capture.unlink()
        result = subprocess.run(["zsh", str(self.zsh_runner), *words],
                               env=dict(self.env, COMPLETION=str(ZSH_COMPLETION),
                                        CAPTURE=str(capture)),
                               capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        raw = capture.read_text().splitlines() if capture.exists() else []
        return [item.split(":", 1)[0] for item in raw]

    def assert_read_only(self):
        # Tab completion only ever lists names; anything else is a violation.
        self.assertFalse(self.violations.exists(),
                         self.violations.read_text() if self.violations.exists() else "")
        if self.log.exists():
            for line in self.log.read_text().splitlines():
                self.assertIn(line, ("list", "list --colors"))

    def assert_candidates(self, words, expected, zsh_expected=None):
        """Both shells offer exactly `expected`; the cursor is on the last word."""
        if zsh_expected is None:
            zsh_expected = expected
        self.assertEqual(sorted(self.bash_candidates(*words)), sorted(expected), words)
        if shutil.which("zsh"):
            self.assertEqual(sorted(self.zsh_candidates(*words)), sorted(zsh_expected), words)
        self.assert_read_only()

    def assert_bash_candidates(self, words, expected):
        """Bash offers exactly `expected` for a COMP_WORDS-shaped token list."""
        self.assertEqual(sorted(self.bash_candidates(*words)), sorted(expected), words)
        self.assert_read_only()

    def test_subcommands_and_bare_mode_flags(self):
        self.assert_candidates(("themectl", ""), SUBCOMMANDS)
        self.assert_candidates(("themectl", "list", ""), ["--colors"])
        self.assert_candidates(("themectl", "list", "--colors", ""), [])
        self.assert_candidates(("themectl", "current", ""), ["--colors"])
        self.assert_candidates(("themectl", "current", "--colors", ""), [])
        self.assert_candidates(("themectl", "next", ""), ["--colors"])
        self.assert_candidates(("themectl", "next", "--colors", ""), [])
        self.assert_candidates(("themectl", "apply", ""), [])
        self.assert_candidates(("themectl", "help", ""), [])

    def test_set_completes_layouts_then_palette_values(self):
        self.assert_candidates(("themectl", "set", ""), ["--colors"] + THEMES)
        self.assert_candidates(("themectl", "set", "mono", ""), ["--colors"])
        self.assert_candidates(("themectl", "set", "--colors", ""), PALETTES)
        self.assert_candidates(("themectl", "set", "mono", "--colors", ""), PALETTES)
        self.assert_candidates(("themectl", "set", "nocturne", "--colors", ""), PALETTES)
        self.assert_candidates(("themectl", "set", "--colors", "nord", ""), THEMES)
        self.assert_candidates(("themectl", "set", "--colors", "nord", "mono", ""), [])
        self.assert_candidates(("themectl", "set", "mono", "--colors", "nord", ""), [])

    def test_no_duplicate_theme_or_colors_suggestions(self):
        self.assert_candidates(("themectl", "set", "--colors", "nord", "--colors", ""), [])
        self.assert_candidates(("themectl", "set", "--colors", "nord", "--colors", "gruvbox", ""),
                               THEMES)
        self.assert_candidates(("themectl", "set", "mono", "slate", ""), ["--colors"])

    def test_set_equals_syntax(self):
        self.assert_candidates(("themectl", "set", "--colors=nord", ""), THEMES)
        self.assert_candidates(("themectl", "set", "--colors=nord", "slate", ""), [])
        # bash filters by the typed value; compsys filters _describe's list.
        self.assert_candidates(("themectl", "set", "--colors=n"), ["--colors=nord"],
                               ["--colors=gruvbox", "--colors=mono", "--colors=nord"])

    def test_render_completes_palettes_only(self):
        self.assert_candidates(("themectl", "render", ""), ["--colors"])
        self.assert_candidates(("themectl", "render", "--colors", ""), PALETTES)
        self.assert_candidates(("themectl", "render", "--colors=gruvbox", ""), [])
        # Never layout names, even after an invalid positional.
        self.assert_candidates(("themectl", "render", "mono", ""), ["--colors"])

    def test_bash_completes_split_equals_tokens(self):
        # COMP_WORDBREAKS splits --colors=VALUE into '--colors', '=', VALUE.
        # The palette value completes as plain names: readline replaces only
        # the fragment after the '=', so no '--colors=' prefix is duplicated.
        self.assert_bash_candidates(("themectl", "set", "--colors", "="), PALETTES)
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "n"), ["nord"])
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "nord", ""), THEMES)
        # A theme typed before the split flag keeps its slot; the value and
        # the theme slot after the split flag still work in any order.
        self.assert_bash_candidates(("themectl", "set", "mono", "--colors", "=", ""), PALETTES)
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "nord", "mono", ""), [])
        # A duplicate --colors gets no value and no second flag suggestion.
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "nord",
                                     "--colors", "="), [])
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "nord",
                                     "--colors", "=", "g"), [])
        self.assert_bash_candidates(("themectl", "set", "--colors", "=", "nord",
                                     "--colors", "=", "gruvbox", ""), THEMES)
        self.assert_bash_candidates(("themectl", "render", "--colors", "=", ""), PALETTES)
        self.assert_bash_candidates(("themectl", "list", "--colors", "="), [])


if __name__ == "__main__":
    unittest.main()

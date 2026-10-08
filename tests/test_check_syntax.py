"""Hermetic regression tests for the repository syntax checker."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scripts/check-syntax.py"

FAKE_TOOL = r"""#!/bin/sh
tool=${0##*/}
printf '%s' "$tool" >> "$CALL_LOG"
for arg in "$@"; do
    printf '\t%s' "$arg" >> "$CALL_LOG"
done
printf '\n' >> "$CALL_LOG"
case ",${FAIL_TOOLS:-}," in
    *",$tool,"*) exit 1 ;;
esac
exit 0
"""


class CheckSyntaxTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="check-syntax-test-")
        self.addCleanup(temp.cleanup)
        temp_root = Path(temp.name)
        self.root = temp_root / "repo"
        self.root.mkdir()
        self.bin = temp_root / "bin"
        self.bin.mkdir()
        for tool in ("bash", "sh", "zsh", "shellcheck", "luac"):
            stub = self.bin / tool
            stub.write_text(FAKE_TOOL)
            stub.chmod(0o755)

        scripts = self.root / "scripts"
        scripts.mkdir()
        shutil.copy2(CHECKER, scripts / "check-syntax.py")
        self.log = self.root / "calls.log"
        self.env = dict(os.environ, PATH=f"{self.bin}{os.pathsep}{os.environ['PATH']}",
                        CALL_LOG=str(self.log), FAIL_TOOLS="")
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def add_file(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def run_checker(self, **env):
        result = subprocess.run(["python3", str(self.root / "scripts/check-syntax.py")],
                                cwd=self.root, env=dict(self.env, **env),
                                capture_output=True, text=True, timeout=10)
        return result

    def calls(self):
        if not self.log.exists():
            return []
        return self.log.read_text().splitlines()

    def test_detects_extensionless_python_and_ast_syntax_errors(self):
        self.add_file("bin/python-tool", "#!/usr/bin/env python3\nif True print('bad')\n")
        result = self.run_checker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid syntax", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_shell_completion_and_template_dialects_and_shellcheck_scope(self):
        self.add_file("tools/python-tool", "#!/usr/bin/env python3\nprint('ok')\n")
        self.add_file("zsh/.config/zsh/completions/_sample", "# completion\n")
        self.add_file("templates/env.sh.tpl", "{{header}}\n")
        self.add_file("templates/env.zsh.tpl", "{{header}}\n")
        # The declared interpreter within the first eight lines takes priority
        # over the .sh.tpl fallback.
        self.add_file("templates/override.sh.tpl", "# generated\n# header\n#!/usr/bin/env bash\n{{body}}\n")
        self.add_file("templates/readme.tpl", "plain template\n")
        self.add_file("scripts/normal.sh", "#!/bin/sh\necho normal\n")

        self.add_file("ignored.sh", "#!/bin/sh\necho ignored\n")
        (self.root / ".gitignore").write_text("ignored.sh\n")
        self.add_file("scripts/.local/lib/python/vendor.py", "#!/usr/bin/env python3\n")
        link_target = self.add_file("scripts/link-target", "not a shell script\n")
        (self.root / "scripts/link.sh").symlink_to(link_target)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)

        result = self.run_checker()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertIn("sh\t-n\ttemplates/env.sh.tpl", calls)
        self.assertIn("zsh\t-n\ttemplates/env.zsh.tpl", calls)
        self.assertIn("bash\t-n\ttemplates/override.sh.tpl", calls)
        self.assertIn("zsh\t-n\tzsh/.config/zsh/completions/_sample", calls)
        self.assertIn("sh\t-n\tscripts/normal.sh", calls)
        shellcheck = [line for line in calls if line.startswith("shellcheck\t")]
        self.assertEqual(shellcheck, ["shellcheck\t--shell=sh\tscripts/normal.sh"])
        self.assertFalse(any("readme.tpl" in line or "ignored.sh" in line
                             or "vendor.py" in line or "link.sh" in line
                             for line in calls))
        self.assertNotIn("templates/env.sh.tpl", shellcheck[0])
        self.assertNotIn("templates/env.zsh.tpl", shellcheck[0])
        self.assertNotIn("templates/override.sh.tpl", shellcheck[0])


if __name__ == "__main__":
    unittest.main()

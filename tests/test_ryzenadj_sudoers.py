"""The ryzenadj sudoers installer is tested without touching system paths."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/.local/bin/setup-ryzenadj-sudoers"


class RyzenadjSudoersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ryzenadj-sudoers-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.live = self.root / "ryzenadj-sudoers-live"
        self.wrapper = self.root / "ryzenadj-wrapper"
        self.log = self.root / "calls.log"
        self.validated = self.root / "validated-content"
        self.visudo_path = self.root / "visudo-path"
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "LC_ALL": "C",
            "LIVE_FILE": str(self.live),
            "FIXTURE_WRAPPER": str(self.wrapper),
            "CALL_LOG": str(self.log),
            "VALIDATED_CONTENT": str(self.validated),
            "VISUDO_PATH": str(self.visudo_path),
            "VISUDO_RESULT": "0",
        }
        self.script("whoami", "printf '%s\\n' fixture-user")
        self.script("ryzenadj", "exit 0")
        self.script("sudo", r'''
printf '%s\n' "$*" >>"$CALL_LOG"
case "$1" in
    visudo)
        shift
        [[ "$1" == -c && "$2" == -f ]] || exit 91
        printf '%s' "$3" >"$VISUDO_PATH"
        cp -- "$3" "$VALIDATED_CONTENT"
        exit "$VISUDO_RESULT"
        ;;
    install)
        shift
        source=$7
        destination=$8
        case "$destination" in
            /etc/sudoers.d/ryzenadj) target=$LIVE_FILE ;;
            /usr/local/lib/ryzenadj-power-profile) target=$FIXTURE_WRAPPER ;;
            *) exit 92 ;;
        esac
        cp -- "$source" "$target"
        ;;
    *) exit 93 ;;
esac
''')

    def script(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + body + "\n")
        path.chmod(0o755)

    def run_helper(self):
        return subprocess.run([str(HELPER)], env=self.env, capture_output=True,
                              text=True, timeout=10)

    def test_validation_failure_preserves_existing_policy_and_cleans_candidate(self):
        sentinel = "# existing user policy must survive\n"
        self.live.write_text(sentinel)
        self.env["VISUDO_RESULT"] = "1"

        result = self.run_helper()

        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.live.read_text(), sentinel)
        self.assertTrue(self.visudo_path.exists())
        self.assertFalse(Path(self.visudo_path.read_text()).exists())
        calls = self.log.read_text().splitlines()
        self.assertTrue(any(call.startswith("visudo -c -f ") for call in calls), calls)
        self.assertFalse(any("rm " in call for call in calls), calls)

    def test_validation_precedes_atomic_install_with_root_owned_modes(self):
        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text().splitlines()
        validation_index = next(i for i, call in enumerate(calls)
                                if call.startswith("visudo -c -f "))
        policy_install_index = next(i for i, call in enumerate(calls)
                                    if call.startswith("install ") and
                                    call.endswith(" /etc/sudoers.d/ryzenadj"))
        wrapper_install = next(call for call in calls
                               if call.startswith("install ") and
                               call.endswith(" /usr/local/lib/ryzenadj-power-profile"))
        policy_install = calls[policy_install_index]
        self.assertLess(validation_index, policy_install_index, calls)
        self.assertIn("-m 0755 -o root -g root", wrapper_install)
        self.assertIn("-m 0440 -o root -g root", policy_install)
        self.assertTrue(self.live.exists())
        self.assertFalse(Path(self.visudo_path.read_text()).exists())

    def test_policy_only_grants_restricted_wrapper_not_raw_binary(self):
        result = self.run_helper()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        policy = self.live.read_text()
        self.assertEqual(policy, "fixture-user ALL=(ALL) NOPASSWD: /usr/local/lib/ryzenadj-power-profile\n")
        self.assertNotIn("/usr/bin/ryzenadj", policy)
        self.assertIn("/usr/bin/ryzenadj", self.wrapper.read_text())
        self.assertEqual(self.validated.read_text(), policy)

    def test_failure_does_not_issue_live_policy_install_or_remove(self):
        self.live.write_text("# preserve me\n")
        self.env["VISUDO_RESULT"] = "1"

        result = self.run_helper()

        self.assertNotEqual(result.returncode, 0)
        calls = self.log.read_text().splitlines()
        self.assertFalse(any(call.endswith(" /etc/sudoers.d/ryzenadj") for call in calls), calls)
        self.assertEqual(self.live.read_text(), "# preserve me\n")


if __name__ == "__main__":
    unittest.main()

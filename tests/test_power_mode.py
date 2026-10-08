"""Hermetic regression tests for power mode helpers (never touch host hardware)."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/.local/bin/power-mode"
WRAPPERS = {
    "battery-save": ROOT / "scripts/.local/bin/batt-save-mode.sh",
    "balanced": ROOT / "scripts/.local/bin/balanced-mode.sh",
    "performance": ROOT / "scripts/.local/bin/perf-mode.sh",
}
WIDGET = ROOT / "awesome/.config/awesome/awesome-wm-widgets/power-mode-widget/power-mode.lua"

FIXTURE = r'''
import json, os, sys, time
from pathlib import Path

name = Path(sys.argv[0]).name
args = sys.argv[1:]
log = Path(os.environ["COMMAND_LOG"])
with log.open("a") as stream:
    stream.write(json.dumps([name, *args]) + "\n")

if name == "sudo":
    # Never delegate to host sudo. Simulate sudo's exec using only this fixture.
    if args[:1] != ["--"] or len(args) < 2 or args[1] != "ryzenadj":
        sys.exit(91)
    target = str(Path(os.environ["FIXTURE_BIN"]) / "ryzenadj")
    os.execv(target, [target, *args[2:]])
elif name == "powerprofilesctl":
    if len(args) == 2 and args[0] == "set":
        if os.environ.get("BLOCK_PROFILE") == args[1]:
            gate = Path(os.environ["BACKEND_GATE"])
            deadline = time.monotonic() + 8
            while not gate.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not gate.exists():
                sys.exit(92)
    sys.exit(int(os.environ.get("POWERPROFILES_STATUS", "0")))
elif name == "ryzenadj":
    sys.exit(int(os.environ.get("RYZENADJ_STATUS", "0")))
sys.exit(93)
'''


class PowerModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="power-mode-", dir="/tmp/opencode")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.state_home = self.root / "state with spaces"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("bash", "readlink", "dirname", "flock", "mkdir", "mktemp", "mv", "rm", "cat"):
            target = shutil.which(name)
            if target is None:
                self.fail(f"required test fixture dependency unavailable: {name}")
            (self.bin / name).symlink_to(target)
        self.fixture = self.bin / "fixture"
        self.fixture.write_text(f"#!{sys.executable}\n" + FIXTURE)
        self.fixture.chmod(0o755)
        for name in ("powerprofilesctl", "ryzenadj", "sudo"):
            (self.bin / name).symlink_to(self.fixture)
        self.helper = self.root / "power-mode"
        shutil.copy2(HELPER, self.helper)
        self.log = self.root / "commands.jsonl"
        self.env = {
            "HOME": str(self.home),
            "XDG_STATE_HOME": str(self.state_home),
            "PATH": str(self.bin),
            "LC_ALL": "C",
            "COMMAND_LOG": str(self.log),
            "FIXTURE_BIN": str(self.bin),
        }

    @property
    def state_dir(self):
        return self.state_home / "awesome"

    @property
    def state_file(self):
        return self.state_dir / "power-mode"

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run_helper(self, *args, env=None, code=0):
        result = subprocess.run([str(self.helper), *args], env=env or self.env,
                                capture_output=True, text=True, timeout=12)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def test_each_mode_and_compatibility_wrapper_maps_to_profile_and_state(self):
        expected = {
            "battery-save": "power-saver",
            "balanced": "balanced",
            "performance": "performance",
        }
        install_dir = self.root / "installed helpers with & [glob]"
        install_dir.mkdir()
        shutil.copy2(HELPER, install_dir / "power-mode")
        for mode, profile in expected.items():
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                wrapper = install_dir / WRAPPERS[mode].name
                shutil.copy2(WRAPPERS[mode], wrapper)
                result = subprocess.run([str(wrapper)], env=self.env,
                                        capture_output=True, text=True, timeout=12)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(self.calls(), [["powerprofilesctl", "set", profile]])
                self.assertEqual(self.state_file.read_text(), mode + "\n")
                self.assertEqual(self.state_file.stat().st_mode & 0o777, 0o600)

    def test_help_unknown_modes_and_extra_arguments_do_not_act_or_write_state(self):
        result = self.run_helper("--help")
        self.assertIn("Usage: power-mode", result.stdout)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state_dir.exists())
        for args in (("bogus",), ("balanced", "extra"), ()):
            with self.subTest(args=args):
                self.run_helper(*args, code=2)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state_dir.exists())

    def test_default_backend_uses_powerprofilesctl_and_never_ryzenadj_or_sudo(self):
        self.run_helper("balanced")
        self.assertEqual(self.calls(), [["powerprofilesctl", "set", "balanced"]])

    def test_missing_powerprofilesctl_fails_without_fallback_or_authentication(self):
        (self.bin / "powerprofilesctl").unlink()
        result = self.run_helper("performance", code=1)
        self.assertIn("powerprofilesctl is required", result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state_dir.exists())

    def test_missing_ryzen_dependencies_fail_without_authentication_or_fallback(self):
        for dependency in ("sudo", "ryzenadj"):
            with self.subTest(dependency=dependency):
                (self.bin / dependency).unlink(missing_ok=True)
                env = {**self.env, "POWER_MODE_BACKEND": "ryzenadj",
                       "POWER_MODE_RYZEN_BALANCED": "1,2,3,4"}
                result = self.run_helper("balanced", env=env, code=1)
                self.assertIn(f"{dependency} is required", result.stderr)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.state_dir.exists())
                (self.bin / dependency).symlink_to(self.fixture)

    def test_explicit_ryzenadj_tuple_becomes_literal_arguments(self):
        for mode, variable in (
            ("battery-save", "POWER_MODE_RYZEN_BATTERY_SAVE"),
            ("balanced", "POWER_MODE_RYZEN_BALANCED"),
            ("performance", "POWER_MODE_RYZEN_PERFORMANCE"),
        ):
            with self.subTest(mode=mode):
                self.log.unlink(missing_ok=True)
                env = {**self.env, "POWER_MODE_BACKEND": "ryzenadj", variable: "25000,30000,32000,85"}
                self.run_helper(mode, env=env)
                self.assertEqual(self.calls(), [
                    ["sudo", "--", "ryzenadj", "--stapm-limit=25000", "--fast-limit=30000",
                     "--slow-limit=32000", "--tctl-temp=85"],
                    ["ryzenadj", "--stapm-limit=25000", "--fast-limit=30000",
                     "--slow-limit=32000", "--tctl-temp=85"],
                ])
                self.assertEqual(self.state_file.read_text(), mode + "\n")

    def test_invalid_backend_is_rejected_before_state_or_commands(self):
        self.run_helper("balanced", env={**self.env, "POWER_MODE_BACKEND": "arbitrary"}, code=2)
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.state_dir.exists())

    def test_invalid_ryzenadj_tuples_fail_before_state_backend_or_sudo(self):
        invalid = (None, "", "0,2,3,4", "-1,2,3,4", "+1,2,3,4", "01,2,3,4",
                   "1,2,3", "1,2,3,4,5", "1,2,3,x", "1234567890,2,3,4",
                   "1,2,3,4;touch /tmp/nope", "$(id),2,3,4")
        for value in invalid:
            with self.subTest(value=value):
                env = {**self.env, "POWER_MODE_BACKEND": "ryzenadj"}
                if value is not None:
                    env["POWER_MODE_RYZEN_BALANCED"] = value
                self.run_helper("balanced", env=env, code=2)
                self.assertEqual(self.calls(), [])
                self.assertFalse(self.state_dir.exists())

    def test_backend_failure_preserves_original_state_bytes_and_cleans_staging_file(self):
        self.state_dir.mkdir(parents=True)
        original = b"battery-save\n\xffprevious-bytes\n"
        self.state_file.write_bytes(original)
        env = {**self.env, "POWERPROFILES_STATUS": "17"}
        self.run_helper("performance", env=env, code=17)
        self.assertEqual(self.state_file.read_bytes(), original)
        leftovers = [path.name for path in self.state_dir.glob("power-mode.*")
                     if path.name != "power-mode.lock"]
        self.assertEqual(leftovers, [])
        self.assertEqual(self.calls(), [["powerprofilesctl", "set", "performance"]])

    def test_non_directory_state_preflight_fails_before_backend(self):
        self.state_home.write_text("not a directory")
        self.run_helper("balanced", code=1)
        self.assertEqual(self.calls(), [])

    def test_directory_at_state_file_path_is_rejected_before_backend(self):
        self.state_file.mkdir(parents=True)
        marker = self.state_file / "keep"
        marker.write_text("user data\n")
        self.run_helper("balanced", code=1)
        self.assertEqual(self.calls(), [])
        self.assertEqual(marker.read_text(), "user data\n")

    def test_default_state_home_is_under_the_fixture_home(self):
        env = {key: value for key, value in self.env.items() if key != "XDG_STATE_HOME"}
        self.run_helper("balanced", env=env)
        state_file = self.home / ".local/state/awesome/power-mode"
        self.assertEqual(state_file.read_text(), "balanced\n")
        self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)
        self.assertFalse(self.state_home.exists())

    def test_raw_backend_failure_keeps_previous_state(self):
        self.state_dir.mkdir(parents=True)
        previous = b"previous-state\n"
        self.state_file.write_bytes(previous)
        env = {**self.env, "POWER_MODE_BACKEND": "ryzenadj",
               "POWER_MODE_RYZEN_BALANCED": "1,2,3,4", "RYZENADJ_STATUS": "9"}
        self.run_helper("balanced", env=env, code=9)
        self.assertEqual(self.state_file.read_bytes(), previous)
        self.assertEqual([path.name for path in self.state_dir.glob("power-mode.*")],
                         ["power-mode.lock"])

    def test_concurrent_requests_serialize_backend_and_publish_last_applied_mode(self):
        gate = self.root / "release backend"
        env = {**self.env, "BLOCK_PROFILE": "power-saver", "BACKEND_GATE": str(gate)}
        first = subprocess.Popen([str(self.helper), "battery-save"], env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self._stop_process, first)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if self.calls():
                break
            time.sleep(0.01)
        self.assertEqual(self.calls(), [["powerprofilesctl", "set", "power-saver"]])
        second = subprocess.Popen([str(self.helper), "balanced"], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self._stop_process, second)
        time.sleep(0.15)
        # Second invocation is blocked on the lock and cannot reach backend early.
        self.assertEqual(self.calls(), [["powerprofilesctl", "set", "power-saver"]])
        gate.touch()
        for process in (first, second):
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.calls(), [
            ["powerprofilesctl", "set", "power-saver"],
            ["powerprofilesctl", "set", "balanced"],
        ])
        self.assertEqual(self.state_file.read_text(), "balanced\n")

    @staticmethod
    def _stop_process(process):
        if process.poll() is None:
            process.kill()
            process.communicate()

    def test_widget_descriptions_do_not_claim_fixed_machine_measurements(self):
        text = WIDGET.read_text()
        for claim in ("GHz", "MHz", "watts", "°C"):
            with self.subTest(claim=claim):
                self.assertNotIn(claim, text)


if __name__ == "__main__":
    unittest.main()

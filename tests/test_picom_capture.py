"""picom-capture runs against fake picom, pgrep, pkill, detect-gpu and notify-send."""
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/.local/bin/picom-capture"

# The fakes only ever touch files under the temp dir, never real processes.
FAKES = {
    "picom": r"""#!/bin/sh
echo "picom $*" >> "$FAKE_DIR/log"
[ -s "$FAKE_DIR/state" ] && exit 1
echo "picom $*" > "$FAKE_DIR/state"
""",
    "pgrep": r"""#!/bin/sh
state=$(cat "$FAKE_DIR/state" 2>/dev/null)
[ -n "$state" ] || exit 1
if [ "$1 $3 $4" = "-u -x picom" ]; then
  case "$state" in picom*) exit 0 ;; esac
  exit 1
fi
if [ "$1 $3 $4" = "-u -fx --" ]; then
  [ "$state" = "$5" ] && exit 0
  exit 1
fi
echo "unexpected pgrep: $*" >&2
exit 2
""",
    "pkill": r"""#!/bin/sh
echo "pkill $*" >> "$FAKE_DIR/log"
[ -e "$FAKE_DIR/immortal" ] && exit 0
: > "$FAKE_DIR/state"
""",
    "detect-gpu": r"""#!/bin/sh
[ -e "$FAKE_DIR/nogpu" ] && exit 1
exit 0
""",
    "notify-send": r"""#!/bin/sh
echo "notify-send $*" >> "$FAKE_DIR/log"
""",
}


class PicomCaptureTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="picom-capture-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name, body in FAKES.items():
            fake = self.bin / name
            fake.write_text(body)
            fake.chmod(0o755)
        self.config_home = self.root / "config"
        (self.config_home / "picom").mkdir(parents=True)
        self.conf = self.config_home / "picom/picom-capture.conf"
        self.conf.write_text("shadow = false;\n")
        self.state = self.root / "state"
        self.log = self.root / "log"
        self.capture_cmd = f"picom -b --config {self.conf}"

    def running(self, cmdline):
        self.state.write_text(cmdline + "\n")

    def current(self):
        return self.state.read_text().strip() if self.state.exists() else ""

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def started(self):
        return [c for c in self.calls() if c.startswith("picom ")]

    def stopped(self):
        return [c for c in self.calls() if c.startswith("pkill")]

    def run_script(self, *args):
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.root),
            "XDG_CONFIG_HOME": str(self.config_home),
            "FAKE_DIR": str(self.root),
        }
        return subprocess.run(
            [str(SCRIPT), *args], env=env, capture_output=True, text=True
        )

    def test_toggle_normal_to_capture(self):
        self.running("picom -b")
        result = self.run_script("toggle")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), self.capture_cmd)
        calls = self.calls()
        self.assertTrue(calls[0].startswith("pkill"))
        self.assertEqual(calls[1], f"picom -b --config {self.conf}")
        self.assertEqual(calls[2], "notify-send Picom Capture mode on")

    def test_default_is_toggle(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), self.capture_cmd)
        self.assertEqual(self.stopped(), [])

    def test_toggle_capture_to_normal(self):
        self.running(self.capture_cmd)
        result = self.run_script("toggle")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), "picom -b")
        self.assertEqual(self.started(), ["picom -b"])
        self.assertIn("notify-send Picom Capture mode off", self.calls())

    def test_on_when_already_capture_is_noop(self):
        self.running(self.capture_cmd)
        result = self.run_script("on")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.current(), self.capture_cmd)

    def test_off_when_not_capture_is_noop(self):
        self.running("picom -b")
        result = self.run_script("off")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.current(), "picom -b")

    def test_status(self):
        self.assertEqual(self.run_script("status").stdout, "off\n")
        self.running("picom -b")
        self.assertEqual(self.run_script("status").stdout, "normal\n")
        self.running(self.capture_cmd)
        result = self.run_script("status")
        self.assertEqual((result.stdout, result.returncode), ("capture\n", 0))

    def test_no_gpu_on_leaves_picom_alone(self):
        (self.root / "nogpu").touch()
        self.running("picom -b")
        result = self.run_script("on")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.current(), "picom -b")

    def test_no_gpu_off_stops_and_starts_nothing(self):
        (self.root / "nogpu").touch()
        self.running(self.capture_cmd)
        result = self.run_script("off")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.current(), "")
        self.assertEqual(self.started(), [])

    def test_missing_config_does_not_stop_picom(self):
        self.conf.unlink()
        self.running("picom -b")
        result = self.run_script("on")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.current(), "picom -b")

    def test_bad_argument(self):
        result = self.run_script("bogus")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)

    def test_picom_that_will_not_die(self):
        (self.root / "immortal").touch()
        self.running("picom -b")
        result = self.run_script("on")
        self.assertEqual(result.returncode, 1)
        self.assertTrue(result.stderr)
        self.assertEqual(self.current(), "picom -b")
        self.assertEqual(self.started(), [])


if __name__ == "__main__":
    unittest.main()

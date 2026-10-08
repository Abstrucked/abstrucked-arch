"""Regression tests for secure, portable SSH client defaults."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "ssh/.ssh/config"


@unittest.skipUnless(shutil.which("ssh"), "OpenSSH client is not installed")
class SSHConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [shutil.which("ssh"), "-G", "-F", str(CONFIG), "example.invalid"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.options = {}
        for line in result.stdout.splitlines():
            key, _, value = line.partition(" ")
            cls.options.setdefault(key.lower(), []).append(value.strip())

    def test_host_key_algorithms_allow_modern_keys_without_ssh_rsa(self):
        algorithms = self.options["hostkeyalgorithms"][0].split(",")
        for algorithm in ("rsa-sha2-512", "rsa-sha2-256", "ssh-ed25519"):
            self.assertIn(algorithm, algorithms)
        self.assertNotIn("ssh-rsa", algorithms)

    def test_control_path_is_hashed_and_short(self):
        control_path = self.options["controlpath"][0]
        # OpenSSH expands %C while rendering `ssh -G`, so inspect the source
        # directive for the token and the effective value for its short hash.
        self.assertIn("ControlPath ~/.ssh/cm-%C", CONFIG.read_text())
        self.assertNotIn("example.invalid", control_path)
        self.assertLess(len(control_path), 108)

    def test_existing_security_connection_and_identity_options_survive(self):
        self.assertEqual(self.options["passwordauthentication"], ["no"])
        # OpenSSH normalizes the configured "yes" value to "true" in -G output.
        self.assertIn(self.options["pubkeyauthentication"], (["yes"], ["true"]))
        self.assertEqual(self.options["connecttimeout"], ["10"])
        self.assertEqual(self.options["serveraliveinterval"], ["60"])
        self.assertEqual(self.options["identityfile"],
                         ["~/.ssh/id_ed25519", "~/.ssh/id_rsa"])


if __name__ == "__main__":
    unittest.main()

"""detect-gpu runs against a fake /sys/class/drm and a fake glxinfo."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/.local/bin/detect-gpu"


class DetectGpuTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="detect-gpu-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.sys = self.root / "sys"
        (self.sys / "class/drm").mkdir(parents=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()

    def card(self, name, driver):
        """A DRM card whose device is bound to <driver>, like sysfs lays it out."""
        drivers = self.sys / "bus/pci/drivers" / driver
        drivers.mkdir(parents=True, exist_ok=True)
        device = self.sys / "devices" / name
        device.mkdir(parents=True)
        (device / "driver").symlink_to(drivers)
        card = self.sys / "class/drm" / name
        card.mkdir()
        (card / "device").symlink_to(device)

    def glxinfo(self, accelerated):
        script = self.bin / "glxinfo"
        script.write_text(f"#!/bin/sh\necho '    Accelerated: {accelerated}'\n")
        script.chmod(0o755)

    def run_script(self, display=":0"):
        env = {"PATH": f"{self.bin}:/usr/bin:/bin", "DETECT_GPU_SYSFS": str(self.sys)}
        if display:
            env["DISPLAY"] = display
        return subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)

    def assert_gpu(self, found):
        result = self.run_script()
        self.assertEqual(result.stdout, "1\n" if found else "0\n")
        self.assertEqual(result.returncode, 0 if found else 1)

    def test_real_gpu_drivers_count(self):
        for driver in ("amdgpu", "radeon", "i915", "xe", "nouveau", "nvidia"):
            with self.subTest(driver=driver):
                self.setUp()
                self.card("card0", driver)
                self.assert_gpu(True)

    def test_emulated_display_adapters_do_not(self):
        for driver in ("bochs-drm", "qxl", "cirrus-qemu", "simpledrm"):
            with self.subTest(driver=driver):
                self.setUp()
                self.card("card0", driver)
                self.assert_gpu(False)

    def test_no_cards(self):
        self.assert_gpu(False)

    def test_connectors_are_not_cards(self):
        # A connector's device is its card, not a PCI device with a driver.
        self.card("card0", "bochs-drm")
        (self.sys / "class/drm/card0-Virtual-1").mkdir()
        self.assert_gpu(False)

    def test_any_gpu_among_several_cards(self):
        self.card("card0", "simpledrm")
        self.card("card1", "amdgpu")
        self.assert_gpu(True)

    def test_virtual_gpu_needs_glx_acceleration(self):
        self.card("card0", "virtio_gpu")
        self.glxinfo("yes")
        self.assert_gpu(True)
        self.glxinfo("no")
        self.assert_gpu(False)

    def test_virtual_gpu_without_glxinfo_or_display(self):
        self.card("card0", "vmwgfx")
        self.assert_gpu(False)
        self.glxinfo("yes")
        result = self.run_script(display=None)
        self.assertEqual((result.stdout, result.returncode), ("0\n", 1))


if __name__ == "__main__":
    unittest.main()

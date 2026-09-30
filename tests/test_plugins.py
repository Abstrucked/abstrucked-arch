"""Plugin mutations use copied code, temporary homes and an allowlisted PATH."""
import fcntl
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PluginTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pluginctl-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo with spaces"
        self.plugins = self.repo / "plugins"
        self.plugins.mkdir(parents=True)
        shutil.copy2(ROOT / "plugins/pluginctl", self.plugins / "pluginctl")
        self.templates = self.repo / "themes/templates"
        self.templates.mkdir(parents=True)
        shutil.copy2(ROOT / "themes/templates/waybar-config.jsonc.base.tpl",
                     self.templates / "waybar-config.jsonc.base.tpl")
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "commands"
        self.bin.mkdir()
        for name in ("bash", "basename", "cat", "cp", "dirname", "flock", "ln",
                     "luac", "mkdir", "mktemp", "mv", "readlink", "realpath", "rm", "sort"):
            executable = shutil.which(name)
            self.assertIsNotNone(executable, name)
            (self.bin / name).symlink_to(executable)
        self.script(self.bin / "awesome", 'exec luac -p "${@: -1}"')
        self.script(self.repo / "themes/themectl",
                    '"$(dirname "$0")/../plugins/pluginctl" template-waybar >/dev/null\n')
        self.env = {
            "HOME": str(self.home), "PATH": str(self.bin), "LC_ALL": "C",
            "XDG_STATE_HOME": str(self.home / ".local/state"),
        }
        self.state = self.home / ".local/state/plugins/enabled"
        self.generated = [self.templates / "waybar-config.jsonc.tpl",
                          self.home / ".config/hypr/lua/plugins.lua",
                          self.home / ".config/awesome/plugins.lua"]
        self.plugin("one")
        self.plugin("two")

    def script(self, path, body):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/bash\nset -euo pipefail\n" + body + "\n")
        path.chmod(0o755)

    def plugin(self, name, helper=None):
        directory = self.plugins / name
        directory.mkdir(exist_ok=True)
        (directory / "manifest.conf").write_text(
            f'NAME="{name}"\nWAYBAR_MODULE="custom/{name}"\n')
        (directory / "waybar.jsonc").write_text('{"format": "widget"}')
        (directory / "hypr.lua").write_text('local example = "valid"\n')
        (directory / "awesome.lua").write_text('local example = "valid"\n')
        self.script(directory / "bin" / (helper or name), "exit 0")

    def run_tool(self, *args, success=True):
        result = subprocess.run([str(self.plugins / "pluginctl"), *args], env=self.env,
                                capture_output=True, text=True, timeout=10)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def live_snapshot(self):
        paths = [*self.generated, self.state, *sorted((self.home / ".local/bin").glob("*"))]
        return {str(path): os.readlink(path) if path.is_symlink() else path.read_bytes()
                for path in paths if path.exists() or path.is_symlink()}

    def fail_once(self, command, destination, after_publish=False):
        real = shutil.which(command)
        (self.bin / command).unlink()
        self.env["FAIL_DEST"] = str(destination)
        self.env["FAIL_MARKER"] = str(self.root / "failure-injected")
        publish = f'{real} "$@"\n' if after_publish else ""
        self.script(self.bin / command, '''
if [[ "${@: -1}" == "$FAIL_DEST" && ! -e "$FAIL_MARKER" ]]; then
  : >"$FAIL_MARKER"
''' + publish + '''
  exit 42
fi
exec ''' + real + ' "$@"')

    def test_enable_disable_and_refresh_manage_only_plugin_links(self):
        self.run_tool("enable", "one")
        helper = self.home / ".local/bin/one"
        self.assertEqual(helper.resolve(), self.plugins / "one/bin/one")
        unrelated = helper.parent / "unrelated"
        unrelated.symlink_to("missing-user-target")
        self.run_tool("refresh")
        self.run_tool("disable", "one")
        self.assertFalse(helper.is_symlink())
        self.assertEqual(os.readlink(unrelated), "missing-user-target")
        self.assertEqual(self.state.read_text(), "")
        self.assertEqual(list(self.plugins.glob(".transaction.*")), [])

    def test_unrelated_regular_symlink_and_directory_collisions_are_preserved(self):
        helper = self.home / ".local/bin/one"
        helper.parent.mkdir(parents=True)
        for kind in ("file", "symlink", "directory"):
            with self.subTest(kind=kind):
                if kind == "file":
                    helper.write_text("user-owned command")
                elif kind == "symlink":
                    helper.symlink_to("missing-user-target")
                else:
                    helper.mkdir()
                result = self.run_tool("enable", "one", success=False)
                self.assertIn("unrelated command", result.stderr)
                self.assertFalse(self.state.exists())
                self.assertFalse(any(path.exists() for path in self.generated))
                if kind == "file":
                    self.assertEqual(helper.read_text(), "user-owned command")
                elif kind == "symlink":
                    self.assertEqual(os.readlink(helper), "missing-user-target")
                if kind == "directory":
                    helper.rmdir()
                else:
                    helper.unlink()

    def test_duplicate_helper_names_are_rejected_before_activation(self):
        self.run_tool("enable", "one")
        self.plugin("duplicate", helper="one")
        before = self.live_snapshot()
        result = self.run_tool("enable", "duplicate", success=False)
        self.assertIn("multiple plugins", result.stderr)
        self.assertEqual(self.live_snapshot(), before)

    def test_syntax_error_leaves_every_live_artifact_unchanged(self):
        self.run_tool("enable", "one")
        before = self.live_snapshot()
        (self.plugins / "two/awesome.lua").write_text("invalid Lua !")
        self.run_tool("enable", "two", success=False)
        self.assertEqual(self.live_snapshot(), before)

    def test_publication_failures_restore_generated_links_and_state(self):
        self.run_tool("enable", "one")
        for destination in [*self.generated, self.home / ".local/bin/two", self.state]:
            with self.subTest(destination=destination):
                before = self.live_snapshot()
                self.fail_once("mv", destination)
                self.run_tool("enable", "two", success=False)
                self.assertEqual(self.live_snapshot(), before)
                self.assertEqual(list(self.plugins.glob(".transaction.*")), [])
                (self.root / "failure-injected").unlink()

    def test_failed_owned_link_removal_rolls_back_disable(self):
        self.run_tool("enable", "one")
        before = self.live_snapshot()
        self.fail_once("rm", self.home / ".local/bin/one")
        self.run_tool("disable", "one", success=False)
        self.assertEqual(self.live_snapshot(), before)

    def test_failure_immediately_after_publication_restores_previous_state(self):
        self.run_tool("enable", "one")
        before = self.live_snapshot()
        self.fail_once("mv", self.state, after_publish=True)
        self.run_tool("enable", "two", success=False)
        self.assertEqual(self.live_snapshot(), before)

    def test_rollback_restores_symlink_text_and_original_target(self):
        self.run_tool("enable", "one")
        original = self.root / "original-generated-file"
        original.write_bytes(self.generated[0].read_bytes())
        self.generated[0].unlink()
        self.generated[0].symlink_to(original)
        before = self.live_snapshot()
        self.fail_once("mv", self.state)
        self.run_tool("enable", "two", success=False)
        self.assertEqual(self.live_snapshot(), before)
        self.assertEqual(self.generated[0].resolve(), original)

    def test_failed_rollback_retains_recovery_material(self):
        self.run_tool("enable", "one")
        original = self.generated[0].read_bytes()
        (self.bin / "mv").unlink()
        real = shutil.which("mv")
        self.env["FAIL_DEST"] = str(self.generated[1])
        self.script(self.bin / "mv", '[[ "${@: -1}" != "$FAIL_DEST" ]] || exit 42\n'
                    f'exec {real} "$@"')
        result = self.run_tool("enable", "two", success=False)
        self.assertIn("recovery copies retained at", result.stderr)
        work = list(self.plugins.glob(".transaction.*"))
        self.assertEqual(len(work), 1)
        self.assertEqual((work[0] / "previous/0").read_bytes(), original)
        self.assertEqual(self.state.read_text(), "one\n")

    def test_removed_plugin_helpers_and_empty_bin_directories(self):
        self.run_tool("enable", "one")
        shutil.rmtree(self.plugins / "one")
        self.run_tool("disable", "one")
        self.assertFalse((self.home / ".local/bin/one").is_symlink())
        (self.plugins / "two/bin/two").unlink()
        self.run_tool("enable", "two")
        self.assertEqual(list((self.home / ".local/bin").iterdir()), [])

    def test_readers_do_not_touch_other_operations_staging_or_wait_on_lock(self):
        markers = [Path(str(path) + ".new") for path in [*self.generated, self.state]]
        for marker in markers:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("belongs to another operation")
        with (self.plugins / ".pluginctl.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.run_tool("list")
            self.run_tool("template-waybar")
        for marker in markers:
            self.assertEqual(marker.read_text(), "belongs to another operation")
        self.assertEqual(list(self.plugins.glob(".transaction.*")), [])

    def test_concurrent_enables_serialize_without_losing_state(self):
        processes = []
        with (self.plugins / ".pluginctl.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                for name in ("one", "two"):
                    process = subprocess.Popen([str(self.plugins / "pluginctl"), "enable", name],
                                               env=self.env, stdout=subprocess.PIPE,
                                               stderr=subprocess.PIPE, text=True)
                    processes.append(process)
                    with self.assertRaises(subprocess.TimeoutExpired):
                        process.wait(timeout=0.1)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
                for process in processes:
                    stdout, stderr = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertEqual(self.state.read_text(), "one\ntwo\n")
        self.assertIn('"custom/one"', self.generated[0].read_text())
        self.assertIn('"custom/two"', self.generated[0].read_text())

    def test_read_only_commands_on_fresh_checkout_create_nothing(self):
        self.run_tool("list")
        self.run_tool("template-waybar")
        self.assertEqual(list(self.home.iterdir()), [])
        self.assertFalse((self.plugins / ".pluginctl.lock").exists())


if __name__ == "__main__":
    unittest.main()

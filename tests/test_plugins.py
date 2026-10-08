"""Plugin mutations use copied code, temporary homes and an allowlisted PATH."""
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
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
        (self.bin / "python3").symlink_to(sys.executable)
        (self.repo / "scripts").mkdir()
        shutil.copy2(ROOT / "scripts/config_syntax.py", self.repo / "scripts/config_syntax.py")
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

    def test_manifest_is_data_and_rejects_malformed_lines_without_execution(self):
        sentinel = self.root / "manifest-was-sourced"
        manifest = self.plugins / "one/manifest.conf"
        manifest.write_text(f'NAME="$(touch {sentinel})"\nfalse\n')
        result = self.run_tool("list", success=False)
        self.assertIn("one", result.stderr)
        self.assertIn("line 2", result.stderr)
        self.assertFalse(sentinel.exists())

    def test_quoted_command_substitution_is_literal_data(self):
        sentinel = self.root / "manifest-was-sourced"
        manifest = self.plugins / "one/manifest.conf"
        manifest.write_text(f'NAME="$(touch {sentinel})"\n')
        result = self.run_tool("list")
        self.assertIn(f'$(touch {sentinel})', result.stdout)
        self.assertFalse(sentinel.exists())

    def test_manifest_comments_and_simple_quote_variants_are_valid(self):
        (self.plugins / "one/manifest.conf").write_text(
            "  # leading comment\n\n NAME = 'Named plugin' # trailing\n"
            'WAYBAR_MODULE = "custom/one" # module\nWAYBAR_SECTION=left\n')
        result = self.run_tool("list")
        self.assertIn("Named plugin", result.stdout)
        self.assertEqual(self.run_tool("template-waybar").returncode, 0)

    def test_unknown_and_duplicate_manifest_keys_are_rejected(self):
        cases = {
            "duplicate": 'NAME="one"\nNAME="again"\n',
            "unknown": 'NAME="one"\nUNEXPECTED="value"\n',
        }
        for kind, content in cases.items():
            with self.subTest(kind=kind):
                manifest = self.plugins / "one/manifest.conf"
                manifest.write_text(content)
                result = self.run_tool("list", success=False)
                self.assertIn("one", result.stderr)
                self.assertIn("line 2", result.stderr)
                self.assertIn("duplicate" if kind == "duplicate" else "unknown", result.stderr)

    def test_malformed_manifest_makes_list_fail(self):
        (self.plugins / "one/manifest.conf").write_text("not an assignment\n")
        result = self.run_tool("list", success=False)
        self.assertIn("invalid manifest assignment", result.stderr)

    def test_invalid_discovered_directory_ids_fail_without_word_splitting(self):
        for name in ("bad plugin", "bad\nplugin"):
            with self.subTest(name=name):
                directory = self.plugins / name
                directory.mkdir()
                try:
                    (directory / "manifest.conf").write_text('NAME="bad"\n')
                    result = self.run_tool("list", success=False)
                    self.assertIn("invalid discovered plugin id", result.stderr)
                finally:
                    shutil.rmtree(directory)

    def test_enable_and_disable_reject_path_like_ids_before_mutation(self):
        for command in ("enable", "disable"):
            with self.subTest(command=command):
                before = self.live_snapshot()
                result = self.run_tool(command, "../one", success=False)
                self.assertIn("invalid plugin id", result.stderr)
                self.assertEqual(self.live_snapshot(), before)

    def test_waybar_module_and_defs_must_validate_before_publication(self):
        self.run_tool("enable", "one")
        cases = (
            ("scalar module", "one/waybar.jsonc", "false"),
            ("malformed module syntax", "one/waybar.jsonc", '{"format": "missing close"'),
            ("malformed defs", "one/waybar-defs.jsonc", '"custom/child": {'),
            ("duplicate base definition", "one/waybar-defs.jsonc", '"clock": {}'),
        )
        for label, relative, content in cases:
            with self.subTest(case=label):
                target = self.plugins / relative
                existed = target.exists()
                old = target.read_bytes() if existed else None
                target.write_text(content)
                before = self.live_snapshot()
                self.run_tool("enable", "two", success=False)
                self.assertEqual(self.live_snapshot(), before)
                if existed:
                    target.write_bytes(old)
                else:
                    target.unlink()

    def test_jsonc_comments_trailing_commas_and_theme_strings_are_valid(self):
        (self.plugins / "one/waybar.jsonc").write_text(
            '{\n // module comment\n "format": "<span color=\'{{accent}}\'>{}</span>",\n}\n')
        (self.plugins / "one/waybar-defs.jsonc").write_text(
            '// fragment comment\n"custom/child": { "format": "{{fg}}", },\n')
        self.run_tool("enable", "one")
        rendered = self.generated[0].read_text()
        self.assertIn("{{accent}}", rendered)
        self.assertIn('"custom/child"', rendered)

    def test_ampersands_in_module_json_survive_bash_marker_replacement(self):
        module_json = '{"format": "left & right && {{accent}}", "exec": "printf x & y && z"}'
        (self.plugins / "one/waybar.jsonc").write_text(module_json)
        self.run_tool("enable", "one")
        self.run_tool("refresh")

        rendered = self.generated[0].read_text()
        self.assertIn('"custom/one": ' + module_json, rendered)
        self.assertNotIn("%%PLUGIN_", rendered)
        # The full config is JSONC (including its generated-file comments), but
        # this fixture's module body is strict JSON. Decode that exact body.
        document, _ = json.JSONDecoder().raw_decode(rendered.split('"custom/one": ', 1)[1])
        self.assertEqual(document, {
            "format": "left & right && {{accent}}",
            "exec": "printf x & y && z",
        })

    def test_waybar_module_quote_injection_is_rejected(self):
        sentinel = self.root / "module-was-evaluated"
        (self.plugins / "one/manifest.conf").write_text(
            f"NAME=one\nWAYBAR_MODULE='custom/one\" , \"evil$(touch {sentinel})'\n")
        result = self.run_tool("enable", "one", success=False)
        self.assertIn("invalid WAYBAR_MODULE", result.stderr)
        self.assertFalse(sentinel.exists())
        self.assertFalse(self.state.exists())

    def test_invalid_base_template_is_checked_even_with_no_enabled_plugins(self):
        self.templates.joinpath("waybar-config.jsonc.base.tpl").write_text("[]\n")
        result = self.run_tool("template-waybar", success=False)
        self.assertIn("invalid Waybar JSONC", result.stderr)

    def test_refresh_persists_normalized_state_and_rolls_back_state_failure(self):
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text("two\n\none\ntwo\n")
        self.run_tool("refresh")
        self.assertEqual(self.state.read_text(), "one\ntwo\n")

        self.state.write_text("two\n\none\none\n")
        before = self.live_snapshot()
        self.fail_once("mv", self.state)
        self.run_tool("refresh", success=False)
        self.assertEqual(self.live_snapshot(), before)
        self.assertEqual(list(self.plugins.glob(".transaction.*")), [])

    def test_lock_timeout_is_reported_without_waiting(self):
        (self.bin / "flock").unlink()
        self.script(self.bin / "flock", 'exit 1')
        result = self.run_tool("enable", "one", success=False)
        self.assertIn("timed out waiting for pluginctl lock", result.stderr)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()

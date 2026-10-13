"""The Yazi package parses, declares every plugin it uses, and is stowed."""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "yazi/.config/yazi"
PLUGINS = ("git", "full-border", "smart-enter", "toggle-pane", "chmod", "githead",
           "relative-motions", "piper", "duckdb", "mediainfo", "ouch")
# Built into Yazi, so it needs no package.toml entry.
BUILTIN_PLUGINS = {"zoxide", "fzf", "trash"}
# Plugins shipped in this repo under plugins/<name>.yazi/ instead of package.toml.
# zen is expected even before its directory exists (it lands in a separate commit).
LOCAL_PLUGINS = {"zen"}


def load(name):
    with (CONFIG / name).open("rb") as handle:
        return tomllib.load(handle)


class YaziPackageTests(unittest.TestCase):
    def test_toml_files_parse(self):
        for name in ("yazi.toml", "keymap.toml", "package.toml"):
            with self.subTest(name=name):
                self.assertTrue(load(name))

    def test_generated_files_are_not_shipped(self):
        # themectl renders theme.toml; ya pkg installs plugins and flavors.
        for name in ("theme.toml", "flavors"):
            self.assertFalse((CONFIG / name).exists(), name)
        # plugins/ may only hold the local zen.yazi; the rest comes from ya pkg.
        plugins = CONFIG / "plugins"
        if plugins.exists():
            self.assertEqual({path.name for path in plugins.iterdir()} - {"zen.yazi"}, set())

    def declared(self):
        deps = load("package.toml")["plugin"]["deps"]
        names = set()
        for dep in deps:
            # "owner/repo" (the plugin is the repo) or "owner/repo:plugin".
            match = re.fullmatch(r"[\w-]+/([\w-]+)(?::([\w-]+))?", dep["use"])
            self.assertIsNotNone(match, dep["use"])
            names.add(match.group(2) or match.group(1))
            self.assertRegex(dep["rev"], r"^[0-9a-f]{7,40}$")
            self.assertTrue(dep["hash"])
        return names

    def test_package_declares_requested_plugins(self):
        self.assertEqual(self.declared(), set(PLUGINS))

    def test_every_referenced_plugin_is_declared(self):
        referenced = set()
        keymap = load("keymap.toml")
        for section in keymap.values():
            for binding in section.get("prepend_keymap", []):
                match = re.match(r"plugin\s+([\w-]+)", binding["run"])
                if match:
                    referenced.add(match.group(1))
        for rule in load("yazi.toml").get("plugin", {}).values():
            for entry in rule:
                referenced.add(entry["run"].split()[0])
        referenced.update(re.findall(r'require\("([\w-]+)"\)', (CONFIG / "init.lua").read_text()))
        referenced -= BUILTIN_PLUGINS | {"mime"}
        self.assertTrue(referenced)
        local = LOCAL_PLUGINS | {path.name.removesuffix(".yazi")
                                 for path in (CONFIG / "plugins").glob("*.yazi")}
        self.assertLessEqual(referenced, self.declared() | local)

    def test_zen_is_bound_to_a_free_key(self):
        bindings = [b for b in load("keymap.toml")["mgr"]["prepend_keymap"]
                    if b["run"] == "plugin zen"]
        self.assertEqual([b["on"] for b in bindings], ["<A-z>"])
        self.assertEqual(bindings[0]["desc"], "Toggle Zen view")

    def test_keymap_binds_requested_keys_without_replacing_defaults(self):
        keymap = load("keymap.toml")
        self.assertNotIn("keymap", keymap["mgr"])
        bound = {tuple([b["on"]] if isinstance(b["on"], str) else b["on"]): b["run"]
                 for b in keymap["mgr"]["prepend_keymap"]}
        self.assertEqual(bound[("l",)], "plugin smart-enter")
        self.assertEqual(bound[("<Enter>",)], "plugin smart-enter")
        self.assertEqual(bound[("T",)], "plugin toggle-pane max-preview")
        self.assertEqual(bound[("c", "m")], "plugin chmod")
        self.assertEqual(bound[("g", ".")], "cd ~/.dotfiles")
        self.assertEqual(bound[("g", "_")], "cd ~/_dev")
        for digit in "123456789":
            self.assertEqual(bound[(digit,)], f"plugin relative-motions {digit}")

    def test_init_colours_are_ansi_names(self):
        # Hex would ignore the palette the terminal gets from themectl.
        self.assertNotRegex((CONFIG / "init.lua").read_text(), r"#[0-9a-fA-F]{3,8}\b")

    def test_packages_list_has_preview_tools(self):
        packages = (ROOT / "packages.list").read_text().split()
        for name in ("glow", "duckdb", "mediainfo", "ouch"):
            self.assertIn(name, packages)

    def test_core_settings(self):
        config = load("yazi.toml")
        self.assertEqual(config["mgr"]["sort_by"], "natural")
        self.assertTrue(config["mgr"]["sort_dir_first"])
        self.assertEqual(config["mgr"]["linemode"], "size_mtime")
        self.assertIn("function Linemode:size_mtime()", (CONFIG / "init.lua").read_text())
        self.assertFalse(config["mgr"]["show_hidden"])
        edit = config["opener"]["edit"][0]
        self.assertTrue(edit["block"])
        self.assertIn("$EDITOR", edit["desc"])

    def test_yazi_is_stowed_and_installable(self):
        steps = (ROOT / "lib/install-steps.sh").read_text()
        match = re.search(r"COMMON_STOW_PACKAGES=\(([^)]*)\)", steps)
        self.assertIn("yazi", match.group(1).split())
        packages = (ROOT / "packages.list").read_text().split()
        for name in ("yazi", "7zip", "zoxide", "resvg", "chafa", "poppler", "imagemagick"):
            self.assertIn(name, packages)

    def test_generated_content_is_ignored(self):
        for path in ("yazi/.config/yazi/theme.toml",
                     "yazi/.config/yazi/plugins/git.yazi/main.lua",
                     "yazi/.config/yazi/flavors/example.yazi/main.lua"):
            result = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT)
            self.assertEqual(result.returncode, 0, path)

    def test_tmux_allows_passthrough_and_resets_update_environment(self):
        text = (ROOT / "config/tmux/tmux.conf").read_text()
        self.assertIn("set -g allow-passthrough on", text)
        self.assertLess(text.index("set -gu update-environment"),
                        text.index("set -ga update-environment"))
        for variable in ("TERM", "TERM_PROGRAM"):
            self.assertIn(f"set -ga update-environment {variable}\n", text)


@unittest.skipUnless(shutil.which("sh"), "needs sh")
class YaziWrapperTests(unittest.TestCase):
    def run_wrapper(self, fake_body):
        with tempfile.TemporaryDirectory(prefix="yazi-wrapper-") as temporary:
            root = Path(temporary)
            (root / "target dir").mkdir()
            (root / "bin").mkdir()
            fake = root / "bin/yazi"
            fake.write_text("#!/bin/sh\n" + fake_body.replace("@TARGET@", str(root / "target dir")))
            fake.chmod(0o755)
            aliases = ROOT / "scripts/.config/shell/aliases.sh"
            script = f'. "{aliases}"; cd "$ROOT"; y -x; echo "status=$?"; pwd -P'
            env = {"PATH": f"{root / 'bin'}:/usr/bin:/bin", "ROOT": str(root), "TMPDIR": str(root)}
            result = subprocess.run(["sh", "-c", script], env=env, capture_output=True,
                                    text=True, timeout=10)
            leftovers = list(root.glob("yazi-cwd.*"))
            return result, root, leftovers

    def test_changes_directory_and_removes_temp_file(self):
        body = 'for a; do case $a in --cwd-file=*) printf "%s" "@TARGET@" > "${a#--cwd-file=}";; esac; done\n'
        result, root, leftovers = self.run_wrapper(body)
        self.assertEqual(result.stdout.splitlines(), ["status=0", str((root / "target dir").resolve())])
        self.assertEqual(leftovers, [])

    def test_stays_put_and_keeps_exit_status_when_no_cwd_written(self):
        result, root, leftovers = self.run_wrapper("exit 3\n")
        self.assertEqual(result.stdout.splitlines(), ["status=3", str(root.resolve())])
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()

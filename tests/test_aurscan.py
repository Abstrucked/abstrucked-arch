"""Hermetic tests for the pinned aurscan PKGBUILD, setup helper and yay hook.

Nothing here builds a package or touches the real home: the helper runs against
a throwaway TARGET with fake makepkg/stow/aurscan on PATH, and the Lua hook runs
under the system lua with stubbed `yay` and `os.execute`.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PKGBUILD = ROOT / "install/aurscan/PKGBUILD"
SETUP = ROOT / "install/setup-aurscan.sh"
HOOK = ROOT / "yay/.config/yay/init.lua"
COMMIT = "7ab80cac87b4db572c2494feef17ec27a904e302"

LUA_DRIVER = r"""
local hook, dir, match = arg[1], arg[2], arg[3]
local installed = os.getenv("T_INSTALLED") == "1"
local scan_ok = os.getenv("T_SCAN") == "0"
local legacy = os.getenv("T_STYLE") == "51"
local callbacks = {}
yay = {
  create_autocmd = function(name, opts) callbacks[name] = opts; print("AUTOCMD\t" .. name) end,
  abort = function(msg) print("ABORT\t" .. msg) end,
}
local function result(ok)
  if legacy then return ok and 0 or 1 end
  if ok then return true end
  return nil, "exit", 1
end
os.execute = function(cmd)
  print("EXEC\t" .. cmd)
  if cmd:find("^test %-x ") then return result(installed) end
  if cmd:find("--prebuild", 1, true) then return result(scan_ok) end
  return result(true)
end
dofile(hook)
local cmd = callbacks.AURPostDownload
assert(cmd and type(cmd.callback) == "function", "AURPostDownload not registered")
cmd.callback({ match = match, data = { dir = dir } })
"""


def run(command, **kwargs):
    return subprocess.run(command, capture_output=True, text=True, timeout=60, **kwargs)


class PkgbuildTests(unittest.TestCase):
    def setUp(self):
        self.text = PKGBUILD.read_text()

    def test_pins_exact_commit_and_skips_checksum(self):
        self.assertRegex(
            self.text,
            r'(?m)^source=\("aurscan::git\+https://github\.com/manticore-projects/aurscan\.git#commit=' + COMMIT + r'"\)$',
        )
        self.assertIn("sha256sums=('SKIP')", self.text)
        self.assertIn("pkgver=0.9.2", self.text)
        self.assertIn("makedepends=('go' 'git')", self.text)

    def test_no_other_remote_sources(self):
        urls = set(re.findall(r"https?://[^\s'\")]+", self.text))
        self.assertEqual(
            {u for u in urls if "manticore-projects/aurscan" not in u}, set()
        )
        self.assertEqual(len(re.findall(r"(?m)^source=", self.text)), 1)
        for word in ("curl", "wget", "go get", "go mod download"):
            self.assertNotIn(word, self.text)

    def test_offline_vendored_build_with_version_stamp(self):
        self.assertIn("-mod=vendor", self.text)
        self.assertIn("-X ${_pkgpath}.Version=v${pkgver}", self.text)
        self.assertIn("internal/version", self.text)
        self.assertIn("go test ./...", self.text)

    def test_package_contents(self):
        for token in ("/usr/bin/${pkgname}", "syay sparu aurscan-edit", "LICENSE", "README.md"):
            self.assertIn(token, self.text)

    @unittest.skipUnless(shutil.which("bash"), "bash required")
    def test_bash_syntax(self):
        self.assertEqual(run(["bash", "-n", str(PKGBUILD)]).returncode, 0)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aurscan-setup-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home dir"
        self.home.mkdir()
        self.bin = self.root / "fakebin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.log.write_text("")
        for name in ("makepkg", "pacman", "git", "stow"):
            self.fake(name, f'printf "{name}|%s|%s\\n" "$PWD" "$*" >>"$CALLS"')
        for tool in ("bash", "realpath", "dirname", "sed", "grep", "cp", "rm", "mktemp", "cat"):
            found = shutil.which(tool)
            (self.bin / tool).symlink_to(found)
        self.env = {"PATH": str(self.bin), "HOME": str(self.home), "CALLS": str(self.log), "LC_ALL": "C.UTF-8"}

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/bash\n" + body + "\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    def calls(self):
        return self.log.read_text().splitlines()

    def setup_run(self, *args):
        return run(["/bin/bash", str(SETUP), *args, "--target", str(self.home)], env=self.env, cwd=self.root)

    def test_help_and_syntax(self):
        result = run(["/bin/bash", str(SETUP), "--help"], env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for token in ("--apply", "--dry-run", "--no-build", "--target", "makepkg -sirc --needed"):
            self.assertIn(token, result.stdout)

    def test_refuses_root(self):
        if os.geteuid() == 0:
            result = self.setup_run()
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("not as root", result.stderr)
        else:
            source = SETUP.read_text()
            self.assertIn('"$EUID" -eq 0', source)
            self.assertIn("not as root", source)

    def test_never_uses_sudo_adopt_or_pacman_conf(self):
        source = SETUP.read_text()
        code = "\n".join(l for l in source.splitlines() if not l.lstrip().startswith("#"))
        self.assertIsNone(re.search(r"(^|[;&|(]\s*)sudo\s", code, re.M))
        for word in ("--adopt", "pacman.conf", "pacman -S", "pacman -U"):
            self.assertNotIn(word, code)

    def test_preview_changes_nothing(self):
        result = self.setup_run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Preview only", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])
        calls = self.calls()
        self.assertEqual([c for c in calls if c.startswith("makepkg")], [])
        stow = [c for c in calls if c.startswith("stow|")]
        self.assertEqual(len(stow), 1)
        self.assertIn("--simulate", stow[0])

    def test_apply_builds_in_temp_dir_then_stows(self):
        result = self.setup_run("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.calls()
        makepkg = [c for c in calls if c.startswith("makepkg|")]
        self.assertEqual(len(makepkg), 1)
        _, cwd, args = makepkg[0].split("|", 2)
        self.assertEqual(args, "-sirc --needed")
        self.assertNotEqual(Path(cwd).resolve(), ROOT)
        self.assertFalse(Path(cwd).exists(), "temp build dir should be removed")
        stow = [c for c in calls if c.startswith("stow|")]
        self.assertEqual(len(stow), 1)
        self.assertTrue(stow[0].endswith(f"--no-folding -d {ROOT} -t {self.home} yay"), stow[0])
        self.assertLess(calls.index(makepkg[0]), calls.index(stow[0]))

    def test_build_copies_pinned_pkgbuild(self):
        self.fake("makepkg", 'cp PKGBUILD "$CALLS.pkgbuild"')
        result = self.setup_run("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(Path(str(self.log) + ".pkgbuild").read_text(), PKGBUILD.read_text())

    def test_apply_skips_build_when_pinned_version_installed(self):
        self.fake("aurscan", 'echo "aurscan v0.9.2"')
        result = self.setup_run("--apply")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("already installed", result.stdout)
        self.assertEqual([c for c in self.calls() if c.startswith("makepkg")], [])
        self.assertEqual(len([c for c in self.calls() if c.startswith("stow|")]), 1)

    def test_older_installed_version_is_rebuilt(self):
        self.fake("aurscan", 'echo "aurscan v0.9.1"')
        self.setup_run("--apply")
        self.assertEqual(len([c for c in self.calls() if c.startswith("makepkg|")]), 1)

    def test_no_build_only_stows(self):
        self.setup_run("--apply", "--no-build")
        self.assertEqual([c for c in self.calls() if c.startswith("makepkg")], [])
        self.assertEqual(len([c for c in self.calls() if c.startswith("stow|")]), 1)

    def test_failed_build_does_not_stow(self):
        self.fake("makepkg", "exit 3")
        result = self.setup_run("--apply")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual([c for c in self.calls() if c.startswith("stow|")], [])

    def test_missing_build_tool_is_reported(self):
        (self.bin / "makepkg").unlink()
        for args in ((), ("--apply",)):
            result = self.setup_run(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("makepkg", result.stderr)
        self.assertEqual(self.calls(), [])

    def test_refuses_existing_regular_init_lua(self):
        init = self.home / ".config/yay/init.lua"
        init.parent.mkdir(parents=True)
        init.write_text("-- mine\n")
        for args in ((), ("--apply",), ("--apply", "--no-build")):
            result = self.setup_run(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("already exists", result.stderr)
        self.assertEqual(init.read_text(), "-- mine\n")
        self.assertFalse(init.is_symlink())
        self.assertEqual(self.calls(), [])

    def test_rejects_unknown_and_conflicting_arguments(self):
        for args in (("--adopt",), ("--apply", "--dry-run")):
            self.assertNotEqual(self.setup_run(*args).returncode, 0)
        self.assertEqual(self.calls(), [])

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
    def test_real_stow_links_hook(self):
        os.unlink(self.bin / "stow")
        (self.bin / "stow").symlink_to(shutil.which("stow"))
        for tool in ("perl", "env"):
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)
        result = self.setup_run("--apply", "--no-build")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        link = self.home / ".config/yay/init.lua"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), HOOK.resolve())
        self.assertFalse((self.home / ".config").is_symlink())


@unittest.skipUnless(shutil.which("lua"), "lua is required")
class YayHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="aurscan-lua-")
        self.addCleanup(self.tmp.cleanup)
        self.driver = Path(self.tmp.name) / "driver.lua"
        self.driver.write_text(LUA_DRIVER)

    def hook(self, directory="/tmp/build/foo", match="foo", installed=True, scan_ok=True, style="52"):
        env = dict(os.environ, T_INSTALLED="1" if installed else "0",
                   T_SCAN="0" if scan_ok else "1", T_STYLE=style)
        result = run(["lua", str(self.driver), str(HOOK), directory, match], env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = [line.split("\t", 1) for line in result.stdout.splitlines()]
        return (
            [e[1] for e in events if e[0] == "AUTOCMD"],
            [e[1] for e in events if e[0] == "EXEC"],
            [e[1] for e in events if e[0] == "ABORT"],
        )

    def test_registers_post_download_hook(self):
        autocmds, _, _ = self.hook()
        self.assertEqual(autocmds, ["AURPostDownload"])

    def test_runs_rules_only_scan_with_quoted_dir(self):
        _, execs, aborts = self.hook()
        self.assertIn("AURSCAN_RULES_ONLY=1 /usr/bin/aurscan --prebuild '/tmp/build/foo'", execs)
        self.assertEqual(aborts, [])

    def test_single_quote_in_dir_is_escaped(self):
        directory = "/tmp/it's a $(touch x) dir"
        _, execs, _ = self.hook(directory=directory)
        scan = next(e for e in execs if "--prebuild" in e)
        self.assertEqual(
            scan, "AURSCAN_RULES_ONLY=1 /usr/bin/aurscan --prebuild '/tmp/it'\\''s a $(touch x) dir'"
        )
        self.assertEqual(shlex.split(scan)[-1], directory)

    def test_aborts_on_nonzero_in_both_lua_result_styles(self):
        for style in ("51", "52"):
            _, execs, aborts = self.hook(match="evil-pkg", scan_ok=False, style=style)
            self.assertEqual(aborts, ["evil-pkg: blocked by aurscan"], style)
            notify = [e for e in execs if e.startswith("notify-send")]
            self.assertEqual(len(notify), 1)
            self.assertIn("-a os-assistant -u normal 'AUR scan blocked' 'evil-pkg'", notify[0])

    def test_no_abort_or_notice_on_success_in_both_styles(self):
        for style in ("51", "52"):
            _, execs, aborts = self.hook(scan_ok=True, style=style)
            self.assertEqual(aborts, [], style)
            self.assertEqual([e for e in execs if e.startswith("notify-send")], [])

    def test_fails_closed_when_aurscan_missing(self):
        for style in ("51", "52"):
            _, execs, aborts = self.hook(installed=False, style=style)
            self.assertEqual(len(aborts), 1)
            self.assertIn("aurscan is not installed", aborts[0])
            self.assertIn("install/setup-aurscan.sh --apply", aborts[0])
            self.assertEqual([e for e in execs if "--prebuild" in e], [])

    def test_hook_never_enables_model_backends(self):
        text = HOOK.read_text()
        self.assertIn("AURSCAN_RULES_ONLY=1", text)
        for word in ("--llm", "ollama", "anthropic", "claude"):
            self.assertNotIn(word, text.lower())

    def test_keeps_aurscan_managed_block_markers(self):
        lines = HOOK.read_text().splitlines()
        self.assertIn("-- >>> aurscan begin (managed block; do not edit by hand)", lines)
        self.assertIn("-- <<< aurscan end", lines)


if __name__ == "__main__":
    unittest.main()

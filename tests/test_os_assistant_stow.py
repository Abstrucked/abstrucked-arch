"""Tests for the optional os-assistant package: Stow helper, launcher, docs.

Everything runs against throwaway fixture homes and copied packages. The real
$HOME is never used as a stow target, the real package is never modified, and
the fake os_assistant.cli fixture is only ever written into copies.
"""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "os-assistant"
LAUNCHER = PACKAGE / ".local" / "bin" / "os-assistant"
SHARE = PACKAGE / ".local" / "share" / "os-assistant"
RUN_PY = SHARE / "run.py"
CONFIG = PACKAGE / ".config" / "os-assistant" / "config.toml"
README = PACKAGE / "README.md"
SETUP = ROOT / "install" / "setup-os-assistant.sh"
PYTHON = "/usr/bin/python3"

FAKE_CLI = '''\
"""Fixture stand-in for os_assistant.cli, written only into copied packages."""

import json
import sys


def main():
    print("FAKE-CLI:" + json.dumps(sys.argv[1:]))
    return 7
'''

DECOY_CLI = '''\
def main():
    print("DECOY-CLI")
    return 0
'''

ENTRY_ARGS = ["hello world", "--probe", "--tool", "find_files"]


def run_cmd(command, **kwargs):
    return subprocess.run(
        command, capture_output=True, text=True, timeout=60, **kwargs
    )


class FixtureHomeTests(unittest.TestCase):
    """Shared throwaway home; every target is a tempfile path with spaces."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="os-assistant-stow-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.env = {"PATH": "/usr/bin:/bin", "HOME": str(self.home), "LC_ALL": "C.UTF-8",
                    "XDG_CONFIG_HOME": str(self.home / ".config"),
                    "XDG_DATA_HOME": str(self.home / ".local/share"),
                    "XDG_STATE_HOME": str(self.home / ".local/state")}


class SetupHelperTests(FixtureHomeTests):
    def run_setup(self, *args, script=SETUP):
        return run_cmd(
            ["bash", str(script), *args], env=self.env, cwd=self.root
        )

    def test_help_lists_modes_and_flags(self):
        result = self.run_setup("--help")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for token in ("--apply", "--dry-run", "--target", "stow"):
            self.assertIn(token, result.stdout)

    def test_default_is_preview_and_creates_nothing(self):
        result = self.run_setup("--target", str(self.home))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Preview", result.stdout)
        self.assertIn("--apply", result.stdout)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_explicit_dry_run_creates_nothing(self):
        result = self.run_setup("--dry-run", "--target", str(self.home))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_apply_and_dry_run_conflict_in_either_order(self):
        for flags in (("--apply", "--dry-run"), ("--dry-run", "--apply")):
            result = self.run_setup(*flags, "--target", str(self.home))
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(self.home.iterdir()), [])

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
    def test_apply_links_leaf_files_without_folding(self):
        result = self.run_setup("--apply", "--target", str(self.home))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        expected = {
            self.home / ".local/bin/os-assistant": LAUNCHER,
            self.home / ".config/os-assistant/config.toml": CONFIG,
            self.home / ".local/share/os-assistant/run.py": RUN_PY,
        }
        for link, real in expected.items():
            self.assertTrue(link.is_symlink(), f"{link} is not a symlink")
            self.assertEqual(link.resolve(), real.resolve())
        self.assertNotIn("Keeping your existing", result.stdout)
        # --no-folding: intermediate directories stay real directories.
        self.assertFalse((self.home / ".local").is_symlink())
        self.assertTrue((self.home / ".local").is_dir())
        # Applying again is a no-op success.
        again = self.run_setup("--apply", "--target", str(self.home))
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
    def test_conflicts_fail_in_both_modes_and_preserve_files(self):
        victim = self.home / ".local" / "bin" / "os-assistant"
        victim.parent.mkdir(parents=True)
        victim.write_text("mine\n")
        for args in (
            ("--target", str(self.home)),
            ("--apply", "--target", str(self.home)),
        ):
            result = self.run_setup(*args)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(victim.is_symlink())
            self.assertEqual(victim.read_text(), "mine\n")
        untouched = {
            str(p.relative_to(self.home)) for p in self.home.rglob("*")
        }
        self.assertEqual(
            untouched,
            {".local", ".local/bin", ".local/bin/os-assistant"},
        )

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
    def test_existing_personal_config_is_kept_in_both_modes(self):
        config = self.home / ".config" / "os-assistant" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_bytes(b"[model]\nname = \"mine\"\n")
        for args in (("--target", str(self.home)), ("--apply", "--target", str(self.home))):
            result = self.run_setup(*args)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Keeping your existing ~/.config/os-assistant/config.toml", result.stdout)
            self.assertFalse(config.is_symlink())
            self.assertEqual(config.read_bytes(), b"[model]\nname = \"mine\"\n")
        self.assertTrue((self.home / ".local/bin/os-assistant").is_symlink())
        self.assertTrue((self.home / ".local/share/os-assistant/run.py").is_symlink())

    @unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
    def test_personal_config_does_not_hide_other_conflicts(self):
        config = self.home / ".config" / "os-assistant" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text("mine\n")
        victim = self.home / ".local" / "bin" / "os-assistant"
        victim.parent.mkdir(parents=True)
        victim.write_text("mine\n")
        for args in (("--target", str(self.home)), ("--apply", "--target", str(self.home))):
            result = self.run_setup(*args)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertFalse(victim.is_symlink())
            self.assertEqual(victim.read_text(), "mine\n")
            self.assertEqual(config.read_text(), "mine\n")
        self.assertFalse((self.home / ".local/share/os-assistant/run.py").exists())

    def test_relative_target_is_rejected(self):
        result = self.run_setup("--target", "relative/home")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute", result.stderr)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_missing_target_directory_is_rejected(self):
        result = self.run_setup("--target", str(self.root / "absent"))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_unknown_arguments_are_rejected(self):
        for args in (
            ("--adopt", "--target", str(self.home)),
            ("--bogus", "--target", str(self.home)),
        ):
            result = self.run_setup(*args)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(list(self.home.iterdir()), [])

    def test_helper_never_installs_or_elevates(self):
        source = SETUP.read_text()
        self.assertNotIn("--adopt", source)
        for word in (
            "sudo",
            "pacman",
            "systemctl",
            "journalctl",
            "curl",
            "wget",
            "yay",
            "pip",
        ):
            self.assertIsNone(
                re.search(r"\b" + word + r"\b", source),
                f"{SETUP} must not use {word!r}",
            )


class LauncherTests(FixtureHomeTests):
    """The launcher and run.py against a relocated copy with a fake cli."""

    def setUp(self):
        super().setUp()
        self.base = self.root / "relocated tree"
        shutil.copytree(PACKAGE / ".local", self.base / ".local")
        self.share = self.base / ".local" / "share" / "os-assistant"
        package = self.share / "os_assistant"
        self.fake_cli = True
        # Always isolate forwarding tests from real model/OS calls, even after the CLI exists.
        (package / "cli.py").write_text(FAKE_CLI)
        self.launcher = self.base / ".local" / "bin" / "os-assistant"
        self.run_py = self.share / "run.py"

    def assert_entry_works(self, invoke):
        """invoke(args) runs the entry point; behavior depends on the cli."""
        if self.fake_cli:
            result = invoke(ENTRY_ARGS)
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("FAKE-CLI:", result.stdout)
            for argument in ENTRY_ARGS:
                self.assertIn(argument, result.stdout)
        else:
            result = invoke(["--help"])
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def make_decoy(self):
        decoy = self.root / "decoy folder"
        (decoy / "os_assistant").mkdir(parents=True)
        (decoy / "os_assistant" / "__init__.py").write_text("")
        (decoy / "os_assistant" / "cli.py").write_text(DECOY_CLI)
        return decoy

    def test_launcher_runs_from_relocated_tree_with_spaces(self):
        self.assert_entry_works(
            lambda args: run_cmd(
                [str(self.launcher), *args], env=self.env, cwd=self.root
            )
        )

    def test_launcher_resolves_its_own_symlink(self):
        link_dir = self.root / "link dir"
        link_dir.mkdir()
        link = link_dir / "os-assistant"
        link.symlink_to(self.launcher)
        self.assert_entry_works(
            lambda args: run_cmd([str(link), *args], env=self.env, cwd=self.root)
        )

    def test_launcher_survives_relocation(self):
        moved = self.root / "moved spot" / "now here"
        moved.parent.mkdir(parents=True)
        shutil.move(str(self.base), str(moved))
        self.assert_entry_works(
            lambda args: run_cmd(
                [str(moved / ".local" / "bin" / "os-assistant"), *args],
                env=self.env,
                cwd=self.root,
            )
        )

    def test_launcher_ignores_pythonpath_decoys(self):
        decoy = self.make_decoy()
        env = dict(self.env, PYTHONPATH=str(decoy))
        self.assert_entry_works(
            lambda args: run_cmd(
                [str(self.launcher), *args], env=env, cwd=decoy
            )
        )
        result = run_cmd(
            [str(self.launcher), "probe"], env=env, cwd=decoy
        )
        self.assertNotIn("DECOY-CLI", result.stdout + result.stderr)

    def test_run_py_entry_under_isolated_python(self):
        decoy = self.make_decoy()
        env = dict(self.env, PYTHONPATH=str(decoy))
        self.assert_entry_works(
            lambda args: run_cmd(
                [PYTHON, "-B", "-I", str(self.run_py), *args], env=env, cwd=decoy
            )
        )
        result = run_cmd(
            [PYTHON, "-B", "-I", str(self.run_py), "probe"], env=env, cwd=decoy
        )
        self.assertNotIn("DECOY-CLI", result.stdout + result.stderr)

    def test_missing_entry_point_fails_clearly(self):
        self.run_py.unlink()
        result = run_cmd(
            [str(self.launcher), "hello"], env=self.env, cwd=self.root
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("entry point", result.stderr)

    def test_launcher_invokes_isolated_interpreter(self):
        source = LAUNCHER.read_text()
        self.assertIn("/usr/bin/python3", source)
        self.assertIn("-B -I", source)


@unittest.skipUnless(shutil.which("stow"), "GNU Stow is required")
class EndToEndStowTests(FixtureHomeTests):
    """Stow a copied fixture package into a fixture home and run the link."""

    def build_fixture_repo(self):
        repo = self.root / "fixture repo"
        (repo / "install").mkdir(parents=True)
        shutil.copy2(SETUP, repo / "install" / SETUP.name)
        shutil.copytree(PACKAGE, repo / "os-assistant")
        cli = repo / "os-assistant/.local/share/os-assistant/os_assistant/cli.py"
        cli.write_text(FAKE_CLI)
        return repo, True

    def test_stowed_launcher_runs_from_fixture_home(self):
        repo, fake_cli = self.build_fixture_repo()
        result = run_cmd(
            ["bash", str(repo / "install" / SETUP.name), "--apply", "--target", str(self.home)],
            env=self.env,
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        launcher = self.home / ".local" / "bin" / "os-assistant"
        self.assertTrue(launcher.is_symlink())
        self.assertEqual(
            launcher.resolve(),
            (repo / "os-assistant/.local/bin/os-assistant").resolve(),
        )
        if fake_cli:
            result = run_cmd(
                [str(launcher), *ENTRY_ARGS], env=self.env, cwd=self.root
            )
            self.assertEqual(result.returncode, 7, result.stdout + result.stderr)
            self.assertIn("FAKE-CLI:", result.stdout)
            for argument in ENTRY_ARGS:
                self.assertIn(argument, result.stdout)
        else:
            result = run_cmd([str(launcher), "--help"], env=self.env, cwd=self.root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertNotIn("Traceback", result.stdout + result.stderr)

    def test_documentation_and_bytecode_are_not_stowed(self):
        repo, _ = self.build_fixture_repo()
        cache = repo / "os-assistant/.local/share/os-assistant/os_assistant/__pycache__"
        cache.mkdir(exist_ok=True)
        (cache / "fixture.pyc").write_bytes(b"fixture, not actual bytecode")
        result = run_cmd(["bash", str(repo / "install" / SETUP.name), "--apply", "--target", str(self.home)],
                         env=self.env, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.home / "README.md").exists())
        self.assertFalse((self.home / ".stow-local-ignore").exists())
        self.assertFalse((self.home / ".local/share/os-assistant/os_assistant/__pycache__").exists())


class ConfigTests(FixtureHomeTests):
    def load(self):
        with CONFIG.open("rb") as stream:
            return tomllib.load(stream)

    def test_config_matches_the_documented_contract(self):
        data = self.load()
        self.assertEqual(set(data), {"model", "paths", "actions", "themes", "status", "limits", "bash", "web_search", "alerts"})
        self.assertEqual(
            data["model"],
            {
                "name": "qwen3:4b-instruct-2507-q4_K_M",
                "host": "http://127.0.0.1:11434",
                "context": 8192,
                "keep_alive": "2m",
                "timeout": 180,
                "max_output_tokens": 768,
            },
        )
        self.assertEqual(data["paths"], {"allowed_roots": []})
        self.assertEqual(data["actions"], {"enabled": False, "apps": {}})
        self.assertEqual(data["themes"], {"enabled": False, "timeout": 120})
        self.assertEqual(data["status"], {"enabled": ["desktop_status", "power_status", "plugin_status", "display_status", "dotfiles_status", "alerts_status"]})
        self.assertEqual(
            data["limits"],
            {
                "max_steps": 6,
                "tool_timeout": 5,
                "scan_entries": 3000,
                "scan_seconds": 3,
                "scan_depth": 8,
                "usage_entries": 100000,
                "usage_seconds": 10,
                "usage_depth": 64,
            },
        )
        self.assertEqual(data["bash"], {"enabled": False, "allowed_roots": [], "allow_writes": False})
        self.assertEqual(
            data["alerts"],
            {"interval": 60, "disk_paths": ["/"], "disk_warning_percent": 90, "disk_critical_percent": 95,
             "memory_warning_percent": 85, "memory_critical_percent": 95, "repeat_minutes": 60},
        )
        self.assertEqual(
            data["web_search"],
            {"enabled": False, "host": "http://127.0.0.1:8888", "timeout": 10},
        )

    def test_config_grants_no_file_or_action_access(self):
        data = self.load()
        self.assertEqual(data["paths"]["allowed_roots"], [])
        self.assertFalse(data["actions"]["enabled"])
        self.assertEqual(data["actions"]["apps"], {})
        self.assertFalse(data["themes"]["enabled"])
        self.assertFalse(data["bash"]["enabled"])
        self.assertEqual(data["bash"]["allowed_roots"], [])
        self.assertFalse(data["bash"]["allow_writes"])
        self.assertFalse(data["web_search"]["enabled"])
        self.assertTrue(data["model"]["host"].startswith("http://127.0.0.1:"))

    def test_config_contains_no_secrets_or_user_paths(self):
        text = CONFIG.read_text().lower().replace("max_output_tokens", "")
        for forbidden in (
            "/home/",
            "https://",
            "password",
            "token",
            "secret",
            "apikey",
            "api_key",
        ):
            self.assertNotIn(forbidden, text)

    def test_config_passes_the_shipped_strict_loader(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(SHARE)!r})\n"
            "from pathlib import Path\n"
            "from os_assistant.config import load_config\n"
            f"load_config(Path({str(CONFIG)!r}))\n"
        )
        result = run_cmd([PYTHON, "-B", "-I", "-c", code], env=self.env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class DocsTests(FixtureHomeTests):
    def test_docs_do_not_confuse_tuned_score_with_general_accuracy(self):
        text = README.read_text()
        self.assertIn("7/10 (70%)", text)
        self.assertIn("HISTORICAL QWEN BASELINE", text)
        self.assertIn("experimental", text)
        self.assertIn("Prefer direct", text)

    def test_minicpm_docs_record_failed_separate_check_and_explanation_limits(self):
        text = README.read_text()
        active, historical = text.split("### Measured local profile — HISTORICAL QWEN BASELINE", 1)
        self.assertIn("32/32 (100%)", active)
        self.assertIn("8/10 (80%)", active)
        self.assertIn("failed the accuracy target", active)
        self.assertIn("not validate explanation accuracy", active)
        self.assertIn("actions remain disabled", active)
        self.assertNotIn("still pending", active)
        self.assertIn("31/32 (96.9%)", historical)

    def test_probe_docs_require_real_model_and_digest_uses_tags(self):
        text = README.read_text()
        self.assertIn("requires a running local Ollama server", text)
        self.assertIn("/api/tags", text)
        self.assertNotIn("/api/show", text)
        self.assertNotIn("needs no model", text)

    def test_readme_documents_the_cli_contract(self):
        text = README.read_text()
        for token in (
            "os-assistant 'prompt'",
            "os-assistant chat",
            "--config",
            "--allow-root",
            "--dry-run",
            "--tool",
            "--arguments",
            "--probe",
            "--doctor",
            "--yes",
            "system_status",
            "processes",
            "find_files",
            "directory_usage",
            "launch_app",
            "set_volume",
            "set_brightness",
            "theme_status",
            "set_theme",
            "apply_theme",
            "desktop_status",
            "power_status",
            "plugin_status",
            "display_status",
            "dotfiles_status",
            "web_search",
            "[web_search]",
        ):
            self.assertIn(token, text, f"README is missing {token!r}")

    def test_readme_documents_manual_ollama_setup(self):
        text = README.read_text()
        for token in (
            "sudo pacman -S --needed ollama",
            "OLLAMA_HOST=127.0.0.1:11434 ollama serve",
            "ollama pull openbmb/minicpm5-2b:latest",
            "https://ollama.com/openbmb/minicpm5-2b",
            "https://huggingface.co/openbmb/MiniCPM5-2B",
            "1.6 GB",
            "digest",
        ):
            self.assertIn(token, text, f"README is missing {token!r}")

    def test_readme_states_safety_defaults(self):
        text = README.read_text()
        for token in (
            "never grants authority",
            "loopback",
            "persisted",
            "typed `yes`",
        ):
            self.assertIn(token, text, f"README is missing {token!r}")


    def test_readme_explains_theme_trust_and_recursive_size_limits(self):
        text = README.read_text()
        for token in ("[themes]", "compromised account", "possible desktop restarts",
                      "file_limit", "truncated_scan", "do not sum the rows", "not a sandbox"):
            self.assertIn(token, text)
        self.assertIn("9/12 (75%)", text)
        self.assertIn("No real theme change", text)

    def test_readme_explains_status_bounds_and_apply_permissions(self):
        text = README.read_text()
        for token in ("[status].enabled", "unavailable", "planned", "NUL-delimited",
                      "filters and includes", "typed", "takes **no arguments**",
                      "does not open its own state files", "not an OS sandbox"):
            self.assertIn(token, text)


class ScriptLintTests(FixtureHomeTests):
    def test_bash_syntax(self):
        for script in (LAUNCHER, SETUP):
            result = run_cmd(["bash", "-n", str(script)])
            self.assertEqual(result.returncode, 0, f"{script}: {result.stderr}")

    @unittest.skipUnless(shutil.which("shellcheck"), "shellcheck is required")
    def test_shellcheck(self):
        for script in (LAUNCHER, SETUP):
            result = run_cmd(["shellcheck", str(script)])
            self.assertEqual(
                result.returncode, 0, f"{script}: {result.stdout}{result.stderr}"
            )


if __name__ == "__main__":
    unittest.main()

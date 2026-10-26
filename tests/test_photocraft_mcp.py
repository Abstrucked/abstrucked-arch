"""Exercise the photocraft-mcp wrapper against a fake photocraft-cli."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/.local/bin/photocraft-mcp"


class PhotocraftMcpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.config = self.root / "config"
        self.config.mkdir()
        self.token_file = self.config / "control.token"
        self.token_file.write_text("0123456789abcdef" * 4 + "\n")
        self.log = self.root / "calls"
        self.ss_log = self.root / "ss_calls"
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "CALL_LOG": str(self.log),
            "SS_LOG": str(self.ss_log),
            "HOME": str(self.root),
            "PHOTOCRAFT_CONFIG_DIR": str(self.config),
            "LC_ALL": "C",
        }
        # The fake logs "<arg>|<arg>|..." then the two token env vars (or
        # "unset"), and prints a marker on stdout like an MCP server would.
        self.tool(
            "photocraft-cli",
            'for arg do printf "%s|" "$arg" >> "$CALL_LOG"; done\n'
            'printf "\\n%s\\n%s\\n" "${PHOTOCRAFT_CONTROL_TOKEN-unset}"'
            ' "${PHOTOCRAFT_CONTROL_TOKEN_FILE-unset}" >> "$CALL_LOG"\n'
            'echo "fake-mcp-output"',
        )
        # ss logs its arguments and, when LISTENING names a port, prints a
        # LISTEN line for it in the -H (no header) format.
        self.tool(
            "ss",
            'echo "$*" >> "$SS_LOG"\n'
            'if [ -n "${LISTENING:-}" ]; then\n'
            '    echo "LISTEN 0 128 127.0.0.1:$LISTENING 0.0.0.0:*"\n'
            "fi",
        )

    def tool(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_wrapper(self, *args, env=None):
        return subprocess.run(
            [str(SCRIPT), *args],
            text=True,
            capture_output=True,
            cwd=self.root,
            env={**self.env, **(env or {})},
            timeout=10,
        )

    def call(self):
        argv, token, token_file = self.log.read_text().splitlines()
        return argv.split("|")[:-1], token, token_file

    def roots(self, read=None, write=None):
        return [
            "--automation-read-root",
            read or str(self.root),
            "--automation-write-root",
            write or str(self.root / "Pictures"),
        ]

    def bridge(self, port="47800", token_file=None):
        return [
            "mcp",
            "--bridge",
            f"127.0.0.1:{port}",
            "--control-token-file",
            token_file or str(self.token_file),
        ]

    def assert_headless(self, result, reason):
        self.assertEqual(result.returncode, 0, result.stderr)
        argv, token, token_file = self.call()
        self.assertEqual(argv, ["mcp", *self.roots()])
        self.assertEqual((token, token_file), ("unset", "unset"))
        self.assertIn(reason, result.stderr)

    def test_listening_with_token_file_bridges(self):
        result = self.run_wrapper(env={"LISTENING": "47800"})
        self.assertEqual(result.returncode, 0, result.stderr)
        argv, _, _ = self.call()
        self.assertEqual(argv, [*self.bridge(), *self.roots()])
        self.assertEqual(result.stderr, "")

    def test_token_env_vars_are_not_inherited_by_the_cli(self):
        self.run_wrapper(
            env={
                "LISTENING": "47800",
                "PHOTOCRAFT_CONTROL_TOKEN": "f" * 64,
                "PHOTOCRAFT_CONTROL_TOKEN_FILE": str(self.token_file),
            }
        )
        argv, token, token_file = self.call()
        self.assertEqual(argv, [*self.bridge(), *self.roots()])
        self.assertEqual((token, token_file), ("unset", "unset"))

    def test_not_listening_starts_headless(self):
        result = self.run_wrapper()
        self.assert_headless(result, "no control server on 127.0.0.1:47800")

    def test_headless_does_not_inherit_token_env_vars(self):
        self.run_wrapper(
            env={
                "PHOTOCRAFT_CONTROL_TOKEN": "f" * 64,
                "PHOTOCRAFT_CONTROL_TOKEN_FILE": str(self.token_file),
            }
        )
        _, token, token_file = self.call()
        self.assertEqual((token, token_file), ("unset", "unset"))

    def test_listening_without_token_file_starts_headless(self):
        self.token_file.unlink()
        result = self.run_wrapper(env={"LISTENING": "47800"})
        self.assert_headless(result, "token file")
        self.assertIn("missing or unreadable", result.stderr)

    def test_listener_on_another_address_is_not_the_control_server(self):
        self.tool(
            "ss",
            'echo "$*" >> "$SS_LOG"\n'
            'echo "LISTEN 0 128 10.0.0.5:47800 0.0.0.0:*"',
        )
        self.assert_headless(self.run_wrapper(), "no control server")

    def test_ss_is_asked_about_the_configured_port(self):
        self.run_wrapper()
        self.assertEqual(self.ss_log.read_text().strip(), "-Hltn sport = :47800")
        self.ss_log.unlink()
        self.run_wrapper(env={"PHOTOCRAFT_CONTROL_PORT": "5555"})
        self.assertEqual(self.ss_log.read_text().strip(), "-Hltn sport = :5555")

    def test_port_and_token_file_overrides(self):
        other = self.root / "my token"
        other.write_text("x\n")
        result = self.run_wrapper(
            env={
                "LISTENING": "5555",
                "PHOTOCRAFT_CONTROL_PORT": "5555",
                "PHOTOCRAFT_CONTROL_TOKEN_FILE": str(other),
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.call()[0], [*self.bridge("5555", str(other)), *self.roots()]
        )

    def test_default_token_file_follows_xdg_config_home(self):
        xdg = self.root / "xdg"
        (xdg / "photocraft").mkdir(parents=True)
        (xdg / "photocraft/control.token").write_text("x\n")
        env = {k: v for k, v in self.env.items() if k != "PHOTOCRAFT_CONFIG_DIR"}
        result = subprocess.run(
            [str(SCRIPT)],
            text=True,
            capture_output=True,
            cwd=self.root,
            env={**env, "XDG_CONFIG_HOME": str(xdg), "LISTENING": "47800"},
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            self.call()[0],
            [*self.bridge(token_file=str(xdg / "photocraft/control.token")), *self.roots()],
        )

    def test_default_roots_create_pictures_directory(self):
        self.assertFalse((self.root / "Pictures").exists())
        self.run_wrapper()
        self.assertTrue((self.root / "Pictures").is_dir())
        self.assertEqual(self.call()[0], ["mcp", *self.roots()])

    def test_root_overrides(self):
        read = self.root / "read root"
        write = self.root / "write root"
        self.run_wrapper(
            env={
                "PHOTOCRAFT_MCP_READ_ROOT": str(read),
                "PHOTOCRAFT_MCP_WRITE_ROOT": str(write),
            }
        )
        self.assertEqual(self.call()[0], ["mcp", *self.roots(str(read), str(write))])
        self.assertTrue(write.is_dir())

    def test_extra_args_follow_the_roots(self):
        self.run_wrapper("--flag", "arg with spaces", env={"LISTENING": "47800"})
        self.assertEqual(
            self.call()[0],
            [*self.bridge(), *self.roots(), "--flag", "arg with spaces"],
        )

    def test_stdout_is_only_what_the_cli_prints(self):
        self.assertEqual(self.run_wrapper().stdout, "fake-mcp-output\n")
        result = self.run_wrapper(env={"LISTENING": "47800"})
        self.assertEqual(result.stdout, "fake-mcp-output\n")


if __name__ == "__main__":
    unittest.main()

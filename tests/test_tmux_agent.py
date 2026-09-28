"""Run with: pytest tests (or python3 -B -m unittest discover -s tests).

Classification fixtures, detection checks and CLI smoke tests for
scripts/.local/lib/tmux-agent/engine.sh and scripts/.local/bin/tmux-agent.
"""

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "scripts" / ".local" / "lib" / "tmux-agent" / "engine.sh"
CLI = ROOT / "scripts" / ".local" / "bin" / "tmux-agent"


def bash(script, *args, env=None):
    """Run script under bash with the engine sourced; args arrive as $1..."""
    prelude = f'set -euo pipefail; . "{ENGINE}"; '
    e = {**os.environ, "TMUX_AGENT_QUIET": "1", **(env or {})}
    return subprocess.run(
        ["bash", "-c", prelude + script, "ta", *args],
        capture_output=True, text=True, env=e,
    )


class ClassifyTests(unittest.TestCase):
    def classify(self, tail, cpu=0, prev="", seen=0):
        r = bash('ta_classify "$1" "$2" "$3" "$4"',
                 tail, str(cpu), prev, str(seen), )
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_blocked_prompt_wants_input(self):
        self.assertEqual(self.classify("Do you want to proceed?"), "blocked")

    def test_blocked_yn_prompt(self):
        self.assertEqual(self.classify("Create this file? [y/n]"), "blocked")

    def test_blocked_numbered_choice(self):
        self.assertEqual(self.classify(" 1. Yes"), "blocked")

    def test_working_when_cpu_moves(self):
        self.assertEqual(self.classify("just some output", cpu=200), "working")

    def test_working_marker_esc_to_interrupt(self):
        self.assertEqual(self.classify("Refactoring... esc to interrupt"), "working")

    def test_working_marker_spinner(self):
        self.assertEqual(self.classify("⠹ thinking about it"), "working")

    def test_ready_on_done_marker(self):
        self.assertEqual(self.classify("✓ Done"), "ready")

    def test_ready_on_completed_sentence(self):
        self.assertEqual(self.classify("All tests completed."), "ready")

    def test_ready_and_seen_is_idle(self):
        self.assertEqual(self.classify("✓ Done", seen=1), "idle")

    def test_working_goes_quiet_becomes_ready(self):
        self.assertEqual(self.classify("some output", prev="working"), "ready")

    def test_quiet_shell_is_idle(self):
        self.assertEqual(self.classify("$ ls"), "idle")

    def test_previous_state_persists(self):
        self.assertEqual(self.classify("$ ", prev="blocked"), "blocked")

    def test_seen_does_not_clear_blocked(self):
        self.assertEqual(self.classify("Approve this change? ", seen=1), "blocked")

    def test_cpu_wins_over_prompt_text(self):
        # Busy CPU takes precedence: churning output can leave prompt text
        # behind in the tail.
        self.assertEqual(self.classify("Do you want to proceed?", cpu=50), "working")

    def test_negative_delta_is_not_working(self):
        self.assertEqual(self.classify("$ ", cpu=-40, prev="working"), "ready")


class RollupTests(unittest.TestCase):
    def test_blocked_is_most_urgent(self):
        r = bash('ta_rollup working blocked ready idle')
        self.assertEqual(r.stdout.strip(), "blocked")

    def test_working_beats_ready(self):
        r = bash('ta_rollup ready idle working')
        self.assertEqual(r.stdout.strip(), "working")

    def test_ready_beats_idle(self):
        r = bash('ta_rollup idle ready')
        self.assertEqual(r.stdout.strip(), "ready")

    def test_empty_input_is_empty(self):
        r = bash('ta_rollup "" ""')
        self.assertEqual(r.stdout.strip(), "")

    def test_ranks_are_ordered(self):
        r = bash('echo "$(ta_state_rank blocked) $(ta_state_rank working) '
                 '$(ta_state_rank ready) $(ta_state_rank idle) $(ta_state_rank other)"')
        self.assertEqual(r.stdout.strip(), "0 1 2 3 4")

    def test_state_colors(self):
        r = bash('echo "$(ta_state_color blocked) $(ta_state_color working) '
                 '$(ta_state_color ready) $(ta_state_color idle)"')
        self.assertEqual(r.stdout.strip(), "red yellow blue green")


class GlyphTests(unittest.TestCase):
    def test_default_glyphs_differ(self):
        r = bash('ta_agent_glyph claude; ta_agent_glyph codex; ta_agent_glyph opencode; ta_agent_glyph other')
        glyphs = r.stdout.split()
        self.assertEqual(len(set(glyphs)), 4)

    def test_glyph_env_override(self):
        r = bash('ta_agent_glyph claude', env={"TMUX_AGENT_ICON_CLAUDE": "X"})
        self.assertEqual(r.stdout.strip(), "X")

    def test_agent_name_from_comm(self):
        r = bash('ta_agent_name_of claude-code ""')
        self.assertEqual(r.stdout.strip(), "claude")

    def test_agent_name_from_argv_path(self):
        r = bash('ta_agent_name_of node "/usr/lib/claude/dist/cli.js"')
        self.assertEqual(r.stdout.strip(), "claude")

    def test_agent_name_needs_word_boundary(self):
        r = bash('ta_agent_name_of vim "vim my-claude-notes.md"')
        self.assertEqual(r.returncode, 1)

    def test_unknown_process_has_no_agent(self):
        r = bash('ta_agent_name_of bash "bash"')
        self.assertEqual(r.returncode, 1)


class DetectTests(unittest.TestCase):
    def tearDown(self):
        for proc in getattr(self, "procs", []):
            proc.kill()
            proc.wait()

    def spawn(self, script):
        proc = subprocess.Popen(["bash", "-c", script])
        self.procs = getattr(self, "procs", [])
        self.procs.append(proc)
        time.sleep(0.2)
        return proc

    def test_detects_agent_running_directly(self):
        proc = self.spawn("exec -a claude sleep 300")
        r = bash('ta_detect_agent "$1"', str(proc.pid))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), ["claude", str(proc.pid)])

    def test_detects_agent_child_of_shell(self):
        proc = self.spawn('bash -c "exec -a codex sleep 300"; sleep 300')
        r = bash('ta_detect_agent "$1"', str(proc.pid))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split()[0], "codex")

    def test_ignores_plain_shell(self):
        proc = self.spawn("exec -a vim sleep 300")
        r = bash('ta_detect_agent "$1"', str(proc.pid))
        self.assertEqual(r.returncode, 1)

    def test_missing_pid_fails(self):
        r = bash('ta_detect_agent 999999')
        self.assertEqual(r.returncode, 1)

    def test_proc_cpu_is_a_number(self):
        r = bash('ta_proc_cpu "$1"', str(os.getpid()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertGreaterEqual(int(r.stdout.strip()), 0)


class CliSmokeTests(unittest.TestCase):
    def run_cli(self, *args):
        e = {**os.environ, "TMUX_AGENT_QUIET": "1",
             "TMUX_AGENT_STATE_DIR": tempfile.mkdtemp(prefix="ta-test-")}
        return subprocess.run([str(CLI), *args], capture_output=True, text=True, env=e)

    def test_strip_exits_clean(self):
        r = self.run_cli("strip")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_status_exits_clean(self):
        r = self.run_cli("status")
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_usage_on_unknown_command(self):
        r = self.run_cli("bogus")
        self.assertEqual(r.returncode, 1)

    def test_report_requires_args(self):
        r = self.run_cli("report")
        self.assertEqual(r.returncode, 1)

    def test_strip_shows_every_pane_with_distinct_state_colors(self):
        with tempfile.TemporaryDirectory(prefix="ta-strip-") as directory:
            state_dir = Path(directory)
            (state_dir / "stamp").write_text(str(int(time.time())) + "\n")
            for pane, state, agent in (
                (1, "idle", "claude"),
                (2, "ready", "codex"),
                (3, "working", "opencode"),
                (4, "blocked", "claude"),
            ):
                (state_dir / f"state-%{pane}").write_text(
                    f"{state}|{agent}|0|0|0|example:1.1|@1|/project\n"
                )
            r = subprocess.run(
                [str(CLI), "strip"], capture_output=True, text=True,
                env={**os.environ, "TMUX_AGENT_STATE_DIR": directory},
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(
                r.stdout,
                " #[fg=red]#[default] #[fg=yellow]#[default]"
                " #[fg=blue]#[default] #[fg=green]#[default]",
            )


if __name__ == "__main__":
    unittest.main()

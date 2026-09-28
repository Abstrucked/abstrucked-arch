"""Run with: pytest tests (or python3 -B -m unittest discover -s tests).

Classification fixtures, detection checks and CLI smoke tests for
scripts/.local/lib/tmux-agent/engine.sh and scripts/.local/bin/tmux-agent.
"""

import json
import os
import re
from pathlib import Path
import shutil
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
    def classify(self, tail, cpu=0, prev="", seen=0, output_changed=0):
        r = bash('ta_classify "$1" "$2" "$3" "$4" "$5"',
                 tail, str(cpu), prev, str(seen), str(output_changed))
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_blocked_prompt_wants_input(self):
        self.assertEqual(self.classify("Do you want to proceed?"), "blocked")

    def test_blocked_yn_prompt(self):
        self.assertEqual(self.classify("Create this file? [y/n]"), "blocked")

    def test_blocked_numbered_choice(self):
        self.assertEqual(self.classify(" 1. Yes"), "blocked")

    def test_idle_cpu_wakeup_does_not_mark_agent_working(self):
        self.assertEqual(self.classify("just some output", cpu=200, prev="idle"), "idle")

    def test_cpu_and_visible_output_change_mark_working(self):
        self.assertEqual(
            self.classify("new output", cpu=200, prev="idle", output_changed=1),
            "working",
        )

    def test_small_cpu_delta_does_not_mark_working_even_if_output_changes(self):
        self.assertEqual(
            self.classify("new output", cpu=5, prev="idle", output_changed=1),
            "idle",
        )

    def test_claude_thinking_ellipsis_is_working(self):
        self.assertEqual(self.classify("✶ Doodling…"), "working")

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
        # An approval prompt takes precedence over CPU churn from a TUI.
        self.assertEqual(self.classify("Do you want to proceed?", cpu=50), "blocked")

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
        # OpenCode shares the generic agent glyph until Nerd Fonts has its own.
        r = bash('ta_agent_glyph claude; ta_agent_glyph codex; ta_agent_glyph opencode; ta_agent_glyph other')
        glyphs = r.stdout.split()
        self.assertEqual(len(set(glyphs)), 3)
        self.assertEqual(glyphs[2], glyphs[3])

    def test_glyph_env_override(self):
        r = bash('ta_agent_glyph claude', env={"TMUX_AGENT_ICON_CLAUDE": "X"})
        self.assertEqual(r.stdout.strip(), "X")

    def test_default_codicons(self):
        r = bash('ta_agent_glyph claude; ta_agent_glyph codex; ta_agent_glyph opencode')
        self.assertEqual(r.stdout.split(), ["\uec82", "\uec81", "\uec67"])

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
                " #[fg=red]\uec82#[default] #[fg=yellow]\uec67#[default]"
                " #[fg=blue]\uec81#[default] #[fg=green]\uec82#[default]",
            )



    def test_pick_rows_align_columns_and_hide_the_pane_id(self):
        with tempfile.TemporaryDirectory(prefix="ta-pick-") as directory:
            state_dir = Path(directory)
            now = int(time.time())
            (state_dir / "stamp").write_text(f"{now}\n")
            for pane, agent, path in (
                (1, "claude", "/src/app"),
                (2, "opencode", "/src/a-longer-project"),
                (3, "codex", "/x"),
            ):
                (state_dir / f"state-%{pane}").write_text(
                    f"idle|{agent}|0|{now}|{now}|work:{pane}.1|@1|{path}|12345\n"
                )
            fake = state_dir / "bin"
            fake.mkdir()
            (fake / "fzf").write_text(f'#!/bin/sh\ncat >"{state_dir}/rows"\nexit 130\n')
            (fake / "fzf").chmod(0o755)
            r = subprocess.run(
                [str(CLI), "pick"], capture_output=True, text=True,
                env={**os.environ, "TMUX_AGENT_STATE_DIR": directory,
                     "PATH": f"{fake}:{os.environ['PATH']}"},
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            rows = [re.sub(r"\x1b\[[0-9;]*m", "", line).split("\t")
                    for line in (state_dir / "rows").read_text().splitlines()]
            self.assertEqual([pane for _, pane in rows], ["%1", "%2", "%3"])
            shown = [text for text, _ in rows]
            for column in ("work:", "0m"):
                self.assertEqual(len({line.index(column) for line in shown}), 1, shown)
            self.assertNotIn("12345", "".join(shown))

class HookTests(unittest.TestCase):
    def state_of(self, event):
        r = bash('ta_hook_state "$1"', event)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout.strip()

    def test_claude_and_codex_events_map_to_states(self):
        for event, state in (
            ("SessionStart", "idle"),
            ("UserPromptSubmit", "working"),
            ("PreToolUse", "working"),
            ("PostToolUse", "working"),
            ("PermissionRequest", "blocked"),
            ("Notification", "blocked"),
            ("Stop", "ready"),
            ("SessionEnd", "end"),
            ("SubagentStop", ""),
        ):
            with self.subTest(event=event):
                self.assertEqual(self.state_of(event), state)

    def test_opencode_events_map_to_states(self):
        for event, state in (
            ("session.execution.started", "working"),
            ("permission.asked", "blocked"),
            ("permission.replied", "working"),
            ("form.created", "blocked"),
            ("form.replied", "working"),
            ("session.execution.succeeded", "ready"),
            ("session.execution.failed", "ready"),
            ("session.execution.interrupted", "ready"),
            ("session.text.delta", ""),
        ):
            with self.subTest(event=event):
                self.assertEqual(self.state_of(event), state)

    def run_hook(self, state_dir, event, pane="%999"):
        # A pane id no tmux server knows: the background rescan drops it,
        # so only the synchronous report write is observed here.
        return subprocess.run(
            [str(CLI), "hook", "claude", event], input='{"session_id": "x"}',
            capture_output=True, text=True,
            env={**os.environ, "TMUX_AGENT_QUIET": "1",
                 "TMUX_AGENT_STATE_DIR": state_dir, "TMUX_PANE": pane},
        )

    def test_hook_reports_state_silently(self):
        with tempfile.TemporaryDirectory(prefix="ta-hook-") as directory:
            r = self.run_hook(directory, "Stop")
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            report = (Path(directory) / "report-%999").read_text()
            self.assertEqual(report.split("|")[0], "ready")

    def test_hook_session_end_clears_report(self):
        with tempfile.TemporaryDirectory(prefix="ta-hook-") as directory:
            (Path(directory) / "report-%999").write_text("working|1\n")
            r = self.run_hook(directory, "SessionEnd")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((Path(directory) / "report-%999").exists())

    def test_hook_outside_tmux_is_a_noop(self):
        with tempfile.TemporaryDirectory(prefix="ta-hook-") as directory:
            r = self.run_hook(directory, "Stop", pane="")
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            self.assertEqual(list(Path(directory).iterdir()), [])


class InstallHooksTests(unittest.TestCase):
    def test_merge_is_idempotent_and_keeps_foreign_hooks(self):
        with tempfile.TemporaryDirectory(prefix="ta-home-") as home:
            settings = Path(home) / ".claude" / "settings.json"
            settings.parent.mkdir()
            settings.write_text(
                '{"model": "x", "hooks": {"Stop": [{"hooks": '
                '[{"type": "command", "command": "other"}]}]}}'
            )
            env = {**os.environ, "HOME": home}
            for _ in range(2):
                r = subprocess.run([str(CLI), "install-hooks", "claude"],
                                   capture_output=True, text=True, env=env)
                self.assertEqual(r.returncode, 0, r.stderr)
            data = json.loads(settings.read_text())
            self.assertEqual(data["model"], "x")
            stop = [h["command"] for e in data["hooks"]["Stop"] for h in e["hooks"]]
            self.assertEqual(len(stop), 2)
            self.assertEqual(stop[0], "other")
            self.assertTrue(stop[1].endswith("tmux-agent hook claude Stop"))
            notification = data["hooks"]["Notification"]
            self.assertEqual(notification[0]["matcher"],
                             "permission_prompt|elicitation_dialog")

    def test_opencode_plugin_directory_is_linked(self):
        with tempfile.TemporaryDirectory(prefix="ta-home-") as home:
            r = subprocess.run([str(CLI), "install-hooks", "opencode"],
                               capture_output=True, text=True,
                               env={**os.environ, "HOME": home})
            self.assertEqual(r.returncode, 0, r.stderr)
            plugin = Path(home) / ".config/opencode/plugins/tmux-agent"
            self.assertEqual(plugin.resolve(), ENGINE.parent / "opencode")
            self.assertTrue((plugin / "index.js").is_file())
            self.assertTrue((plugin / "tui.js").is_file())


@unittest.skipUnless(shutil.which("node"), "node not installed")
class OpencodePluginTests(unittest.TestCase):
    """Drive the TUI plugin with a mocked OpenCode API and event stream."""

    SCRIPT = r"""
const { default: def } = await import(process.env.PLUGIN_URL);
const roots = { root: "root", child: "root" };
const events = [
  ["server.connected", {}],
  ["session.execution.started", { sessionID: "root" }],
  ["session.execution.started", { sessionID: "child" }],
  ["permission.asked", { sessionID: "child" }],
  ["permission.replied", { sessionID: "child" }],
  ["session.execution.succeeded", { sessionID: "child" }],
  ["session.execution.started", { sessionID: "elsewhere" }],
  ["form.created", { form: { sessionID: "root" } }],
  ["session.text.delta", { sessionID: "root" }],
  ["session.execution.interrupted", { sessionID: "root", reason: "shutdown" }],
  ["session.execution.succeeded", { sessionID: "root" }],
].map(([type, data]) => ({ type, data }));
const dispose = def.setup({
  data: { session: { root: (id) => roots[id] ?? id } },
  ui: { router: { current: () => ({ type: "session", sessionID: "root" }) },
        tabs: { list: () => [] } },
  client: { event: { subscribe: async function* ({ signal }) {
    yield* events;
    await new Promise((resolve) => signal.addEventListener("abort", resolve));
  } } },
});
await new Promise((resolve) => setTimeout(resolve, 500));
dispose();
"""

    def test_forwards_this_panes_root_session_and_prompts(self):
        plugin = ENGINE.parent / "opencode" / "tui.js"
        with tempfile.TemporaryDirectory(prefix="ta-oc-") as directory:
            log = Path(directory) / "calls"
            bin_ = Path(directory) / "tmux-agent"
            bin_.write_text(f'#!/bin/sh\necho "$*" >>"{log}"\n')
            bin_.chmod(0o755)
            r = subprocess.run(
                ["node", "--input-type=module", "-e", self.SCRIPT],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, "PLUGIN_URL": plugin.as_uri(),
                     "TMUX_PANE": "%1", "TMUX_AGENT_BIN": str(bin_)},
            )
            self.assertEqual(r.returncode, 0, r.stderr)
            deadline = time.time() + 5
            want = [
                "hook opencode session.execution.started",
                "hook opencode permission.asked",
                "hook opencode permission.replied",
                "hook opencode form.created",
                "hook opencode session.execution.succeeded",
            ]
            calls = []
            while time.time() < deadline:
                calls = log.read_text().splitlines() if log.exists() else []
                if len(calls) >= len(want):
                    break
                time.sleep(0.05)
            self.assertEqual(calls, want)


if __name__ == "__main__":
    unittest.main()

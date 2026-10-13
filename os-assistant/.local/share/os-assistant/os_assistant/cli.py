"""Terminal entry point. Confirmations cannot be supplied by pipes or model text."""

import argparse
import json
import os
from pathlib import Path
import sys

from . import alerts
from .agent import Agent, default_folder
from .config import load_config
from .contracts import AssistantError, ConfigurationError, ToolResult
from .ollama import OllamaClient
from . import presentation
from .policy import Policy
from .presentation import color_enabled, json_results, render_human_preview, write_block, write_line
from .replies import answer as readable_answer
from .runner import Runner


def confirm(call) -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        write_line("Approval requires an interactive terminal; action denied.", sys.stderr)
        return False
    write_line("Type yes to approve this exact action, or anything else to deny:", sys.stdout)
    return sys.stdin.readline().strip() == "yes"


def error_line(message: object) -> None:
    prefix = "error: "
    if color_enabled(sys.stderr):
        prefix = "\x1b[31m" + prefix + "\x1b[0m"
    sys.stderr.write(prefix + presentation.safe_text(message) + "\n")
    sys.stderr.flush()


class _LazyChatClient:
    """Local routing needs neither an Ollama connection nor client construction."""

    def __init__(self, config, *, warn: bool):
        self.config = config
        self.warn = warn
        self.client = None

    def chat(self, messages, tools):
        if self.client is None:
            if self.warn:
                write_line("(experimental model routing; verify results)", sys.stderr)
            self.client = OllamaClient(self.config)
        return self.client.chat(messages, tools)


def short_model(name: str) -> str:
    """Compact display name: drop the namespace and ':latest', cut a tag at its first '-'."""
    name = name.rsplit("/", 1)[-1]
    if name.endswith(":latest"):
        name = name[:-len(":latest")]
    base, sep, tag = name.partition(":")
    return base + sep + tag.split("-", 1)[0] if sep else name


def answer_header(agent: Agent, model: str) -> str:
    """One-line label for who produced the content below it."""
    results = agent.last_results
    if results and all(result.status == "preview" for result in results):
        label = "preview · nothing executed"
    elif agent.last_answer_kind == "tool":
        names = ", ".join(dict.fromkeys(result.name for result in results))
        label = "result · " + names if names else "result"
    elif agent.last_answer_kind == "local":
        label = "assistant"
    elif agent.last_answer_web:
        label = f"{model} · web summary (unverified)"
    elif agent.last_answer_is_summary:
        label = f"{model} · summary of read-only output"
    elif not results:
        label = f"{model} · no tools ran"
    else:
        label = model
    if agent.last_compacted:
        label += " · context compacted"
    return label


def ask_and_explain(agent: Agent, request: str) -> None:
    answer = agent.ask(request)
    if getattr(agent, "last_answer_format", "text") == "json":
        write_line(answer, sys.stdout)
        return
    header = answer_header(agent, short_model(agent.runner.policy.config.model))
    if answer.startswith("Stopped:") and agent.last_answer_kind == "tool":
        header = "stopped"
    write_block(header, answer, sys.stdout)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="os-assistant", description="Local OS assistant with explicit tool permissions.")
    result.add_argument("prompt", nargs="?", help="A quoted request, or 'chat' for interactive mode")
    result.add_argument("--config", type=Path, help="Explicit TOML settings file")
    result.add_argument("--allow-root", action="append", default=[], help="Approve a folder for metadata-only scans this session")
    result.add_argument("--dry-run", action="store_true", help="Validate and preview tools without executing them")
    result.add_argument("--json", action="store_true", help="Print structured result data")
    result.add_argument("--details", action="store_true", help="Show detailed plain-language results")
    modes = result.add_mutually_exclusive_group()
    modes.add_argument("--tool", help="Invoke a registered tool directly without the model")
    modes.add_argument("--doctor", action="store_true", help="Check local Ollama and print the model digest/settings")
    modes.add_argument("--probe", action="store_true", help="Evaluate model tool routing with mocked tools; no OS actions")
    modes.add_argument("--watch-alerts", action="store_true", help="Run the disk/RAM alert watcher (desktop notifications; started by the system-alerts plugin)")
    modes.add_argument("--check-alerts", action="store_true", help="Evaluate disk/RAM alert thresholds once; exit 6 if any is over")
    result.add_argument("--arguments", default="{}", help="JSON object for --tool")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if os.geteuid() == 0:
            raise ConfigurationError("Run os-assistant as your normal user, never with sudo.")
        if arguments.prompt and (arguments.tool or arguments.doctor or arguments.probe
                             or arguments.watch_alerts or arguments.check_alerts):
            raise ConfigurationError("Choose a prompt or one explicit mode, not both.")
        if not arguments.tool and arguments.arguments != "{}":
            raise ConfigurationError("--arguments is only valid with --tool.")
        if arguments.dry_run and (arguments.doctor or arguments.probe):
            raise ConfigurationError("--dry-run cannot run diagnostics or a model probe; nothing executed.")
        if arguments.dry_run and (arguments.watch_alerts or arguments.check_alerts):
            raise ConfigurationError("--dry-run cannot run the alert modes; nothing executed.")
        config = load_config(arguments.config, tuple(arguments.allow_root))
        if arguments.watch_alerts:
            return alerts.watch(config)
        if arguments.check_alerts:
            result = ToolResult("alerts_status", "ok", alerts.status(config))
            if arguments.json:
                write_line(json_results([result]), sys.stdout)
            else:
                write_block("alerts", readable_answer(result, details=arguments.details) or "Alert status unavailable.", sys.stdout)
            return 6 if any(m["level"] in ("warning", "critical") for m in result.data["metrics"]) else 0
        def preview(call):
            if not call.mutates and arguments.json:
                return
            if not call.mutates and not (arguments.dry_run or arguments.details):
                return
            sys.stdout.write("\n")
            render_human_preview(call, sys.stdout)

        runner = Runner(Policy(config), dry_run=arguments.dry_run, confirm=confirm,
                        preview=preview)
        if arguments.tool:
            if len(arguments.arguments) > 8192:
                raise ConfigurationError("--arguments exceeds the 8192-character limit.")
            try:
                data = json.loads(arguments.arguments)
            except (ValueError, RecursionError):
                raise ConfigurationError("--arguments must be valid JSON.") from None
            call = runner.policy.prepare(arguments.tool, data)
            result = runner.run(call)
            if result.status == "preview":
                if arguments.json:
                    write_line(json_results([result]), sys.stdout)
                else:
                    write_line("Preview only; nothing was executed.", sys.stdout)
            elif arguments.json:
                write_line(json_results([result]), sys.stdout)
            else:
                write_line(readable_answer(result, details=arguments.details) or
                           "No readable result available; request JSON for diagnostic data.", sys.stdout)
            return {"denied": 3, "error": 4}.get(result.status, 0)
        if arguments.doctor:
            result = ToolResult("doctor", "ok", OllamaClient(config).doctor())
            if arguments.json:
                write_line(json_results([result]), sys.stdout)
            else:
                write_line(readable_answer(result, details=arguments.details) or
                           "No readable result available; request JSON for diagnostic data.", sys.stdout)
            return 0
        if arguments.probe:
            from .probe import evaluate
            report = evaluate(OllamaClient(config))
            if arguments.json:
                write_line(json.dumps(report, ensure_ascii=True), sys.stdout)
            else:
                write_line(f"Routing probe: {report['passed']}/{report['cases']} cases passed "
                           f"({report['accuracy']:.0%}; target {report['target']:.0%}); "
                           f"model {report['model']}, digest {report['digest']}; "
                           f"latency {sum(case['seconds'] for case in report['results']):.3f}s total.", sys.stdout)
                if arguments.details:
                    for case in report["results"]:
                        write_line(f"  Case {case['id']}: {'passed' if case['passed'] else 'failed'} "
                                   f"({case['seconds']:.3f}s).", sys.stdout)
            return 0 if report["passed_gate"] else 5
        agent = Agent(_LazyChatClient(config, warn=arguments.prompt != "chat"), runner,
                      json_output=arguments.json, details=arguments.details)
        if arguments.prompt == "chat":
            if not sys.stdin.isatty():
                raise ConfigurationError("Chat requires an interactive terminal.")
            folder = default_folder(config)
            write_line(f"os-assistant · {config.model} (experimental routing; verify results) · actions need typed yes", sys.stdout)
            write_line("Commands: /help · default folder: " + folder if folder is not None else "Commands: /help", sys.stdout)
            while True:
                sys.stdout.write("You> ")
                sys.stdout.flush()
                request = sys.stdin.readline()
                if not request or request.strip() == "/quit":
                    break
                if request.strip() == "/reset":
                    agent.reset()
                    write_line("Chat cleared.", sys.stdout)
                    continue
                if request.strip() == "/clear":
                    agent.reset()
                    write_line("Chat cleared.", sys.stdout)
                    continue
                if request.strip() == "/compact":
                    write_line(agent.compact(), sys.stdout)
                    continue
                if request.strip() == "/details":
                    write_block("details", agent.show_details(json_output=False), sys.stdout)
                    continue
                if request.strip() == "/json":
                    write_line(agent.show_details(json_output=True), sys.stdout)
                    continue
                if request.strip() == "/help":
                    write_line("Commands: /clear (/reset), /compact, /details, /json, /help, /quit.", sys.stdout)
                    continue
                if not request.strip():
                    continue
                try:
                    ask_and_explain(agent, request.strip())
                    sys.stdout.write("\n")
                except AssistantError as error:
                    error_line(error)
                    # Denial/failure stops this turn; no permission change or automatic retries.
                    continue
            return 0
        if not arguments.prompt:
            parser().print_help()
            return 0
        ask_and_explain(agent, arguments.prompt)
        return {"denied": 3, "error": 4}.get(agent.last_status, 0)
    except KeyboardInterrupt:
        write_line("Cancelled; no further tools will execute.", sys.stderr)
        return 130
    except AssistantError as error:
        error_line(error)
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

"""Inert terminal rendering: sanitized text, exact previews and bounded results."""

import json
import os
import shutil
import textwrap
import unicodedata
from typing import TextIO

from .contracts import PolicyError, PreparedCall, ToolResult

KNOWN_STATUSES = frozenset({"ok", "preview", "denied", "error", "started"})
MAX_RENDER_CHARS = 8192
_TRUNCATION_NOTICE = "\n[output truncated: showing first {shown} of {total} characters]\n"


def _escape_controls(text: str) -> str:
    """Show every control or format character as a visible escape; keep newlines."""
    parts = []
    for char in text:
        if char != "\n" and unicodedata.category(char).startswith("C"):
            parts.append(ascii(char)[1:-1])
        else:
            parts.append(char)
    return "".join(parts)


def safe_text(value: object) -> str:
    """Stringify value so ANSI/OSC controls, bidi overrides and backspaces are inert."""
    return _escape_controls(value if isinstance(value, str) else str(value))


def write_line(text: object, stream: TextIO) -> None:
    """Write one sanitized line to stream."""
    stream.write(safe_text(text) + "\n")
    stream.flush()


def color_enabled(stream: TextIO) -> bool:
    """Colour only on a real terminal, honouring NO_COLOR and TERM=dumb."""
    try:
        tty = stream.isatty()
    except (AttributeError, ValueError):
        tty = False
    return tty and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def write_block(header: str, body: str, stream: TextIO, *, color: bool | None = None) -> None:
    """Header at column 0; all content indented so it cannot imitate the assistant's own UI."""
    if color is None:
        color = color_enabled(stream)
    utf8 = "utf" in (getattr(stream, "encoding", None) or "").lower()
    title = ("── " if utf8 else "-- ") + safe_text(header).replace("\n", " ")
    if color:
        title = "\x1b[1;36m" + title + "\x1b[0m"
    width = min(shutil.get_terminal_size(fallback=(100, 24)).columns, 100)
    text = safe_text(body)
    if len(text) > MAX_RENDER_CHARS:
        total = len(text)
        text = text[:MAX_RENDER_CHARS] + _TRUNCATION_NOTICE.format(shown=MAX_RENDER_CHARS, total=total).rstrip("\n")
    out = [title]
    for line in text.splitlines():
        if not line.strip():
            out.append("")
            continue
        indent = "  " + line[:len(line) - len(line.lstrip())]
        # Wrapped continuations inherit the indent; unbroken tokens (URLs, paths) may overflow.
        out.extend(textwrap.wrap(line.strip(), width=max(width, len(indent) + 20), initial_indent=indent,
                                 subsequent_indent=indent, break_long_words=False, break_on_hyphens=False))
    stream.write("\n".join(out) + "\n")
    stream.flush()


def _jsonable(value: object) -> object:
    """Convert containers and foreign objects into JSON-serializable shapes."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {(key if isinstance(key, str) else safe_text(key)): _jsonable(item) for key, item in value.items()}
    return safe_text(value)


def _json_text(value: object) -> str:
    """Single-line JSON rendering with ensure_ascii so quoting and controls cannot deceive."""
    try:
        dumped = json.dumps(_jsonable(value), ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError, RecursionError):
        dumped = json.dumps(safe_text(value), ensure_ascii=True)
    return _escape_controls(dumped)


def _status_text(status: object) -> str:
    """Canonical statuses stay bare tokens; anything else is JSON-escaped and quoted."""
    if isinstance(status, str) and status in KNOWN_STATUSES:
        return status
    return _json_text(status)


def _emit(lines: list[str], stream: TextIO) -> None:
    body = "".join(safe_text(line) + "\n" for line in lines)
    total = len(body)
    if total > MAX_RENDER_CHARS:
        body = body[:MAX_RENDER_CHARS] + _TRUNCATION_NOTICE.format(shown=MAX_RENDER_CHARS, total=total)
    stream.write(body)
    stream.flush()


def render_preview(call: PreparedCall, stream: TextIO) -> None:
    """Show the exact name, every argument value and the frozen argv; never a shell string."""
    lines = [f"tool: {_json_text(call.name)}"]
    if call.arguments:
        lines.append("arguments:")
        lines.extend(f"  {_json_text(key)}: {_json_text(value)}" for key, value in call.arguments)
    else:
        lines.append("arguments: (none)")
    lines.append(f"argv: {_json_text(call.argv)}")
    if call.name in ("set_theme", "apply_theme"):
        lines.append("effects: updates app configurations, runs trusted repository hooks/reloads, and may restart desktop components")
    if call.name == "web_search":
        lines.append("effects: sends this query to the local SearXNG, which forwards it to public search engines")
    if call.name == "bash":
        lines.append("executor: guarded fd-based file operation; no host shell" if call.mutates else
                     "executor: guarded live size metadata; no source contents or host shell" if call.argv and call.argv[0] == "/usr/bin/du" else
                     "executor: Bash in read-only bubblewrap snapshot; protected/linked files and oversized contents excluded")
        if call.mutates:
            lines.append("effects: creates, replaces, moves or removes approved files; content replacements are private, moves preserve existing mode")
    _emit(lines, stream)


def render_result(result: ToolResult, stream: TextIO) -> None:
    """Compact bounded rendering with a deterministic status line kept apart from data."""
    lines = [f"tool: {_json_text(result.name)}", f"status: {_status_text(result.status)}"]
    if result.data.get("metadata_kind") == "live_host_metadata_not_snapshot":
        lines.append("coverage: INCOMPLETE scan; partial totals only" if result.data.get("truncated_scan") else
                     "coverage: completed permitted view; protected/linked paths are excluded")
    if result.data:
        lines.append("data:")
        lines.extend(f"  {_json_text(key)}: {_json_text(result.data[key])}" for key in sorted(result.data, key=str))
    else:
        lines.append("data: (none)")
    _emit(lines, stream)


def render_human_preview(call: PreparedCall, stream: TextIO) -> None:
    """Exact literal values and argv in readable lines, never a shell command.

    An approval preview cannot be truncated: refuse rather than hiding part of
    the action the user is being asked to approve. repr quotes data, not code.
    """
    labels = {"root": "Folder", "cwd": "Working folder", "command": "Command",
              "palette": "Palette", "layout": "Layout", "percent": "Percent",
              "app": "Application", "path": "Subfolder", "query": "Query"}
    lines = [("Proposed change: " if call.mutates else "Preview: ") + safe_text(call.name.replace("_", " "))]
    for key, value in call.arguments:
        lines.append(f"{labels.get(key, key.replace('_', ' ').capitalize())}: {ascii(value)}")
    if call.argv:
        lines.append("Executable: " + ascii(call.argv[0]))
        lines.extend(f"Argument {index}: {ascii(value)}" for index, value in enumerate(call.argv[1:], 1))
    if call.name in ("set_theme", "apply_theme"):
        lines.append("This updates app configurations and runs trusted hooks/reloads; desktop components may restart.")
    elif call.name == "web_search":
        lines.append(f"Sends this query to SearXNG at {call.verification}, which forwards it to public search engines.")
    elif call.name == "bash":
        lines.append("Guarded file operation; no host shell." if call.mutates else
                     "Read-only filtered snapshot or live size metadata; no source files changed.")
    body = "\n".join(safe_text(line) for line in lines) + "\n"
    if len(body) > MAX_RENDER_CHARS:
        raise PolicyError("Exact preview exceeds the display limit; nothing executed or approved.")
    stream.write(body)
    stream.flush()


def json_results(results: list[ToolResult], *, historical: bool = False) -> str:
    """Explicit opt-in JSON, kept valid even when an oversized record is omitted."""
    records = [result.as_dict() for result in results]
    value = records[0] if len(records) == 1 else {"results": records}
    if historical:
        value = {"historical": True, "new_execution": False, "result": value}
    text = _json_text(value)
    if len(text) > MAX_RENDER_CHARS:
        if any(result.status == "preview" for result in results):
            raise PolicyError("Exact preview exceeds the display limit; nothing executed or approved.")
        records = [{"tool": result.name, "status": result.status,
                    "data": {key: result.data[key] for key in (
                        "truncated_scan", "scan_complete", "scope_filtered", "excluded_entries", "contents_read")
                             if key in result.data}, "output_omitted": "Request narrower results; data exceeded display limit."}
                   for result in results]
        value = {"results": records, "historical": historical, "output_truncated": True}
        if historical:
            value["new_execution"] = False
        text = _json_text(value)
    return text

"""Plain-language summaries of verified tool records; never performs I/O."""

import math
import re

from .contracts import ToolResult
from . import presentation

_MISSING = object()
_UNAVAILABLE = "unavailable"


def _text(value: object) -> str:
    """Sanitize untrusted labels and make every line break visible."""
    return presentation.safe_text(value).replace("\n", r"\n")


def _number(value: object, *, floating: bool = False) -> int | float | None:
    if floating:
        if type(value) is int:
            return value if value >= 0 else None
        if type(value) is not float or not math.isfinite(value) or value < 0:
            return None
        return value
    return value if type(value) is int and value >= 0 else None


def _human_bytes(value: object) -> str:
    number = _number(value)
    if number is None:
        return _UNAVAILABLE
    if number.bit_length() > 30000:
        return "size exceeds display range"
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB")
    power = 0
    while power < len(units) - 1 and number >= 1024 ** (power + 1):
        power += 1
    if power == 0:
        return f"{number} B"
    denominator = 1024 ** power
    tenths, remainder = divmod(number * 10, denominator)
    if remainder * 2 >= denominator:
        tenths += 1
    return f"{tenths // 10}.{tenths % 10} {units[power]}"


def _value(data: dict, key: str, *, byte_count: bool = False) -> str | None:
    value = data.get(key, _MISSING)
    if value is _MISSING:
        return None
    if value == _UNAVAILABLE:
        return _UNAVAILABLE
    if byte_count:
        return _human_bytes(value) if _number(value) is not None else None
    number = _number(value, floating=True)
    if type(number) is int and number.bit_length() > 30000:
        return "too large to display"
    return _text(number) if number is not None else None


def _count(data: dict, key: str) -> int | None:
    return _number(data.get(key))


def _scope(question: str, aliases: tuple[str, ...]) -> str:
    """Return the simple conjunction/comma clause addressing one metric."""
    clauses = re.split(r"\s+and\s+|[,;]", question.lower())
    match = next((i for i, clause in enumerate(clauses)
                  if any(re.search(rf"\b{re.escape(alias)}\b", clause) for alias in aliases)), None)
    if match is None:
        return ""
    clause = clauses[match]
    # Natural phrasing often separates a qualifier: "total and available RAM".
    if match and re.fullmatch(r"\s*(total|used|free|available|capacity|charging|percentage|percent)\s*", clauses[match - 1]):
        clause = clauses[match - 1] + " " + clause
    # Drop any qualifier for a different entity left in the same clause.
    return clause


def _asked(question: str, words: tuple[str, ...]) -> bool:
    forms = []
    for word in words:
        forms.append(word)
        forms.append(word[:-1] + "ies" if word.endswith("y") else word + "s")
    return any(re.search(rf"\b{re.escape(word)}\b", question, re.I) for word in forms)


def _bounded(lines: list[str], warnings: list[str]) -> str:
    # Warnings go first so a very long details section cannot hide caveats.
    warning_text = "\n".join(warnings)
    body = "\n".join(line for line in lines if line)
    if warning_text:
        full = f"{warning_text}\n{body}" if body else warning_text
    else:
        full = body
    limit = presentation.MAX_RENDER_CHARS
    if len(full) <= limit:
        return full
    notice = " [output truncated]"
    return full[:max(0, limit - len(notice))] + notice


def _directory(data: dict, question: str, details: bool, metric: str | None) -> str | None:
    path = data.get("path", _MISSING)
    root = data.get("root", _MISSING)
    if path is _MISSING or root is _MISSING or not isinstance(path, str) or not isinstance(root, str):
        return None
    label = _text(root.rstrip("/") + ("" if path in ("", ".") else "/" + path.lstrip("/")))
    allocated = _human_bytes(data.get("allocated_size_bytes")) if _count(data, "allocated_size_bytes") is not None else None
    logical = _human_bytes(data.get("total_size_bytes")) if _count(data, "total_size_bytes") is not None else None
    files = _count(data, "files_scanned")
    if metric is None and re.search(r"\b(?:logical\s+(?:file\s+)?(?:size|bytes)|apparent\s+size)\b", question, re.I):
        metric = "both" if re.search(r"\ballocated\b", question, re.I) else "logical"
    if metric in ("logical-h", "logical-b", "logical-k", "allocated-h", "allocated-b", "allocated-k"):
        kind, unit = metric.split("-")
        value = _count(data, "total_size_bytes" if kind == "logical" else "allocated_size_bytes")
        if value is None:
            return None
        shown = _human_bytes(value) if unit == "h" else f"{value} B" if unit == "b" else f"{(value + 1023) // 1024} KiB"
        main = f"{shown} {kind} (filtered view)."
        metric = "logical" if kind == "logical" else "size"
    elif metric == "files":
        if files is None:
            return None
        main = f"{files} {'file' if files == 1 else 'files'} (filtered view)."
    elif metric == "logical":
        if logical is None:
            return None
        main = f"{label}: {logical} logical file size (filtered view)."
    else:
        both = metric == "both" or (metric is None and bool(re.search(r"\ballocated\b.*\blogical\b|\blogical\b.*\ballocated\b", question, re.I)))
        if allocated is None or (both and logical is None):
            return None
        main = f"{label}: {allocated} allocated"
        if both:
            main += f", {logical} logical file size"
        main += " (filtered view)."
    warnings = []
    if data.get("truncated_scan") is True:
        warnings.append("Incomplete scan; partial total/count.")
    elif _number(data.get("unavailable_entries")) not in (None, 0):
        warnings.append("Some entries unavailable.")
    lines = [main]
    if details:
        if metric != "files":
            if metric != "logical" and allocated is not None:
                lines.append(f"Allocated total: {allocated}.")
            if logical is not None and (metric == "logical" or metric == "both" or
                                        re.search(r"\b(logical|apparent)\b", question, re.I)):
                lines.append(f"Logical total: {logical}.")
        dirs = data.get("directories")
        if isinstance(dirs, list):
            for item in dirs[:5]:
                if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                    continue
                count = _number(item.get("files_scanned"))
                if metric == "files":
                    lines.append(f"{_text(item['name'])}: {count if count is not None else 'unavailable'} files.")
                else:
                    size_key = "allocated_size_bytes" if metric != "logical" else "size_bytes"
                    size = _human_bytes(item.get(size_key))
                    lines.append(f"{_text(item['name'])}: {size} across {count if count is not None else 'unavailable'} files.")
        largest = data.get("files")
        if isinstance(largest, list):
            for item in largest[:5]:
                if isinstance(item, dict) and isinstance(item.get("relative_path"), str):
                    lines.append(f"Largest file: {_text(item['relative_path'])} ({_human_bytes(item.get('size_bytes'))}).")
        for flag, description in (("truncated_directories", "Directory list is partial."),
                                  ("truncated_files", "Largest-file list is partial.")):
            if data.get(flag) is True:
                warnings.append(description)
        for key, label_text in (("excluded_entries", "Excluded entries"), ("unavailable_entries", "Unavailable entries"),
                                ("directories_scanned", "Directories scanned")):
            count = _count(data, key)
            if count is not None:
                lines.append(f"{label_text}: {count}.")
        if data.get("scan_complete") is True:
            lines.append("Completed permitted view; protected and linked entries may be excluded.")
        elif data.get("truncated_scan") is not True:
            lines.append("Filtered view; not an unrestricted filesystem total.")
    return _bounded(lines, warnings)


def _system(data: dict, question: str) -> str | None:
    keys = ("memory", "battery", "disk", "load")
    q = question.lower()
    requested = [key for key, terms in (("memory", ("memory", "ram")), ("battery", ("battery", "charging")),
                                         ("disk", ("disk", "storage")), ("load", ("load",)))
                 if _asked(q, terms)]
    selected = requested or list(keys)
    memory_q = _scope(q, ("memory", "ram"))
    disk_q = _scope(q, ("disk", "storage"))
    battery_q = _scope(q, ("battery",)) or (q if _asked(q, ("charging",)) else "")
    known_fields = {"memory_bytes", "load_average", "battery", "disk_bytes"}
    if not known_fields.intersection(data):
        return None
    pieces = []
    if "memory" in selected:
        memory = data.get("memory_bytes")
        if isinstance(memory, dict):
            available_n, total_n = _number(memory.get("available")), _number(memory.get("total"))
            if "total" in memory_q and ("available" in memory_q or "free" in memory_q):
                pieces.append(f"Memory: {_human_bytes(available_n)} available of {_human_bytes(total_n)}.")
            elif "used" in memory_q:
                value = (total_n - available_n) if total_n is not None and available_n is not None and available_n <= total_n else None
                pieces.append(f"Memory used: {_human_bytes(value)}.")
            elif "total" in memory_q:
                pieces.append(f"Memory total: {_human_bytes(total_n)}.")
            elif "available" in memory_q or "free" in memory_q:
                pieces.append(f"Memory available: {_human_bytes(available_n)}.")
            else:
                pieces.append(f"Memory: {_human_bytes(available_n)} available of {_human_bytes(total_n)}.")
        elif memory == _UNAVAILABLE:
            pieces.append("Memory: unavailable.")
        else:
            pieces.append("Memory: unavailable.")
    if "battery" in selected:
        batteries = data.get("battery", _MISSING)
        if not isinstance(batteries, list):
            pieces.append("Battery: unavailable.")
            batteries = []
        if not batteries:
            if not pieces or not pieces[-1].startswith("Battery:"):
                pieces.append("Battery: unavailable.")
        else:
            for battery in batteries[:5]:
                if not isinstance(battery, dict) or not isinstance(battery.get("name"), str):
                    pieces.append("Battery: unavailable.")
                    break
                capacity = battery.get("capacity", _UNAVAILABLE)
                capacity_text = f"{capacity}%" if type(capacity) is int and 0 <= capacity <= 100 else _UNAVAILABLE
                state = battery.get("status", _UNAVAILABLE)
                if not isinstance(state, str):
                    state = _UNAVAILABLE
                if any(term in battery_q for term in ("percentage", "percent", "%")) and "charging" not in battery_q:
                    pieces.append(f"Battery: {capacity_text}.")
                elif "charging" in battery_q and not any(term in battery_q for term in ("percentage", "percent", "%")):
                    pieces.append(f"Battery: {_text(state)}.")
                else:
                    pieces.append(f"Battery {_text(battery['name'])}: {capacity_text}, {_text(state)}.")
    if "disk" in selected:
        disk = data.get("disk_bytes")
        if isinstance(disk, dict):
            total_n, used_n, free_n = (_number(disk.get(field)) for field in ("total", "used", "free"))
            if "total" in disk_q and "free" in disk_q:
                pieces.append(f"Disk: {_human_bytes(free_n)} free of {_human_bytes(total_n)}.")
            elif "used" in disk_q:
                pieces.append(f"Disk used: {_human_bytes(used_n)}.")
            elif "total" in disk_q or "capacity" in disk_q:
                pieces.append(f"Disk total: {_human_bytes(total_n)}.")
            elif "free" in disk_q or "available" in disk_q or "space" in disk_q:
                pieces.append(f"Disk free: {_human_bytes(free_n)}.")
            else:
                pieces.append(f"Disk: {_human_bytes(free_n)} free of {_human_bytes(total_n)}.")
        elif disk == _UNAVAILABLE:
            pieces.append("Disk: unavailable.")
        else:
            pieces.append("Disk: unavailable.")
    if "load" in selected:
        load = data.get("load_average")
        if isinstance(load, dict):
            vals = [_value(load, period) for period in ("1min", "5min", "15min")]
            if any(value is None for value in vals):
                pieces.append("Load average: unavailable.")
            else:
                pieces.append(f"Load average (1/5/15 min): {', '.join(vals)}.")
        elif load == _UNAVAILABLE:
            pieces.append("Load average: unavailable.")
        else:
            pieces.append("Load average: unavailable.")
    return _bounded(pieces, [])


def _files(data: dict, details: bool, question: str = "") -> str | None:
    files = data.get("files")
    if not isinstance(files, list):
        return None
    if re.search(r"\b(?:how\s+many|number\s+of|count(?:\s+the)?)\s+(?:matching\s+)?files?\b|\bfile\s+count\b", question, re.I):
        matches = _count(data, "matches")
        if matches is None:
            return None
        warnings = ["Incomplete scan; count covers only the scanned view."] if data.get("truncated_scan") is True else []
        return _bounded([f"{matches} matching {'file' if matches == 1 else 'files'} (bounded search)."], warnings)
    lines = []
    for entry in files[:20]:
        if not isinstance(entry, dict) or not isinstance(entry.get("relative_path"), str):
            return None
        size = _human_bytes(entry.get("size_bytes"))
        if size == _UNAVAILABLE:
            return None
        lines.append(f"{_text(entry['relative_path'])} — {size}")
    if not files:
        lines.append("No matching files in the returned view.")
    elif not lines:
        return None
    warnings = []
    if data.get("truncated_scan") is True:
        warnings.append("Incomplete search; results are a bounded search sample.")
    elif data.get("sample_only") is True:
        warnings.append("Results are a bounded search sample.")
    return _bounded(lines, warnings)


def _alerts(data: dict) -> str | None:
    metrics, running = data.get("metrics"), data.get("watcher_running")
    if not isinstance(metrics, list) or not metrics or len(metrics) > 9 or type(running) is not bool:
        return None
    lines = []
    for item in metrics:
        if not isinstance(item, dict) or not isinstance(item.get("metric"), str):
            return None
        warning, critical, level = _number(item.get("warning_percent")), _number(item.get("critical_percent")), item.get("level")
        if warning is None or critical is None or level not in ("ok", "warning", "critical", "unavailable"):
            return None
        metric = item["metric"]
        label = "RAM" if metric == "memory" else f"Disk {_text(metric.partition(':')[2])}"
        if level == "unavailable":
            lines.append(f"{label}: unavailable (not checked).")
            continue
        percent = _number(item.get("percent"), floating=True)
        if percent is None:
            return None
        lines.append(f"{label}: {math.floor(percent)}% used (warning at {warning}%, critical at {critical}%) — {level.upper()}")
    lines.append("Alert watcher: running." if running else
                 "Alert watcher: not running (enable with: pluginctl enable system-alerts).")
    return _bounded(lines, [])


def _status_tool(name: str, data: dict, question: str, details: bool) -> str | None:
    if name == "processes":
        items = data.get("processes")
        if not isinstance(items, list):
            return None
        lines = []
        for item in items[:20]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                return None
            pid, rss = _number(item.get("pid")), item.get("rss_bytes")
            if pid is None or _number(rss) is None:
                return None
            lines.append(f"{_text(item['name'])} (PID {pid}) — {_human_bytes(rss)}")
        if not lines:
            lines.append("No processes in the returned view.")
        return _bounded(lines, ["Process list truncated."] if data.get("truncated") is True else [])
    if name == "find_files":
        return _files(data, details, question)
    if name == "desktop_status":
        q = question.lower()
        selections = [("palette", "Palette"), ("layout", "Layout"), ("wallpaper_set", "Wallpaper set")]
        selected = [(key, label) for key, label in selections if
                    (key == "wallpaper_set" and _asked(q, ("wallpaper",))) or
                    (key == "palette" and _asked(q, ("palette",))) or
                    (key == "layout" and _asked(q, ("layout",)))]
        process_aliases = {"picom": ("picom",), "awesome": ("awesome",),
                           "tailscale": ("tailscaled", "tailscale"), "tailscaled": ("tailscaled", "tailscale"),
                           "waybar": ("waybar",), "swaync": ("swaync",),
                           "hyprland": ("Hyprland", "hyprland")}
        queried_processes = []
        for label, aliases in process_aliases.items():
            if _asked(q, (label,)) and aliases not in queried_processes:
                queried_processes.append(aliases)
        parts = []
        for key, label in selected:
            value = data.get(key)
            if not isinstance(value, str):
                return None
            parts.append(f"{label}: {_text(value)}.")
        if selected:
            parts.append("Appearance not verified.")
        if queried_processes:
            running = data.get("compositor_running")
            if not isinstance(running, dict):
                return None
            for aliases in queried_processes:
                value = next((running[alias] for alias in aliases if alias in running), _UNAVAILABLE)
                state = "running" if value is True else "not running" if value is False else "unavailable"
                parts.append(f"{_text(aliases[0])} process: {state}.")
            parts.append("Process presence only; service health is not verified.")
        elif not selected:
            for key, label in (("compositor", "Compositor"), *selections):
                value = data.get(key)
                if not isinstance(value, str):
                    return None
                parts.append(f"{label}: {_text(value)}.")
            parts.append("Process presence and saved selections only; appearance/service health not verified.")
        if not parts:
            return None
        return _bounded(parts, ["Process scan incomplete."] if data.get("truncated_process_scan") is True else [])
    if name == "power_status":
        q = question.lower()
        requested = []
        if _asked(q, ("governor",)):
            requested.append(("cpu_governor", "CPU governor"))
        if _asked(q, ("profile",)):
            requested.append(("platform_profile", "Power profile"))
        if _asked(q, ("backend", "supported", "support")):
            requested.append(("power_mode_backend", "Backend available"))
        if _asked(q, ("battery", "charging", "percentage", "percent")):
            battery = _system({"battery": data.get("battery", _MISSING)}, question)
            requested.append(("__battery__", ""))
        else:
            battery = None
        if requested:
            parts = []
            for key, label in requested:
                if key == "__battery__":
                    if battery is None:
                        return None
                    parts.append(battery)
                    continue
                value = data.get(key)
                if not isinstance(value, str):
                    value = _UNAVAILABLE
                qualifier = " (executable presence only; no power-mode change performed)" if key == "power_mode_backend" else ""
                parts.append(f"{label}: {_text(value)}{qualifier}.")
            return _bounded(parts, [])
        vals = [data.get("cpu_governor"), data.get("platform_profile"), data.get("power_mode_backend")]
        if any(not isinstance(value, str) for value in vals):
            return None
        parts = [f"CPU governor: {_text(vals[0])}.", f"Power profile: {_text(vals[1])}.",
                 f"Backend available: {_text(vals[2])} (executable presence only)."]
        batteries = data.get("battery")
        if isinstance(batteries, list):
            parts.extend(f"Battery {_text(item['name'])}: {_text(item.get('status', _UNAVAILABLE))}."
                         for item in batteries[:5] if isinstance(item, dict) and isinstance(item.get("name"), str))
        return _bounded(parts, [])
    if name == "plugin_status":
        plugins = data.get("plugins")
        if not isinstance(plugins, list):
            return None
        enabled_query = bool(re.search(r"\benabled\b", question, re.I))
        if enabled_query:
            if data.get("enabled_state_available") is False:
                return "Plugin enabled state unavailable."
            known = [item for item in plugins if isinstance(item, dict) and isinstance(item.get("name"), str)
                     and item.get("enabled") is True]
            unknown = [item for item in plugins if isinstance(item, dict) and isinstance(item.get("name"), str)
                       and item.get("enabled") not in (True, False)]
            lines = [f"Enabled: {_text(item['name'])}." for item in known]
            if unknown:
                lines.extend(f"Enabled state unavailable: {_text(item['name'])}." for item in unknown[:20])
            if not known and not unknown:
                complete = (data.get("enabled_state_available") is True and
                            _number(data.get("plugins_total")) == len(plugins) and data.get("truncated") is False)
                lines.append("No enabled plugins in the returned view." if complete else
                             "Enabled plugin list unavailable or incomplete.")
            warnings = ["Plugin list is partial."] if data.get("truncated") is True else []
            return _bounded(lines, warnings)
        lines = []
        for item in plugins[:20]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                return None
            enabled = item.get("enabled")
            state = "enabled" if enabled is True else "disabled" if enabled is False else "unavailable"
            lines.append(f"{_text(item['name'])}: {state}.")
        if not lines:
            if data.get("plugins_total") is None or data.get("truncated") is True:
                lines.append("Plugin list unavailable or incomplete.")
            else:
                lines.append("No plugins available in the returned view.")
        return _bounded(lines, ["Plugin list is partial."] if data.get("truncated") is True else [])
    if name == "alerts_status":
        return _alerts(data)
    if name == "display_status":
        monitors = data.get("monitors")
        if monitors == _UNAVAILABLE:
            return "Monitor plan unavailable; current display settings are not verified."
        if not isinstance(monitors, list):
            return None
        lines = []
        for item in monitors[:8]:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                return None
            width, height = _number(item.get("width")), _number(item.get("height"))
            if width is None or height is None:
                return None
            lines.append(f"{_text(item['name'])}: planned {width}×{height}.")
        if not lines:
            lines.append("No monitors in the returned plan.")
        lines.append("Planned monitor modes only; current settings are not verified or applied.")
        return _bounded(lines, ["Monitor list is partial."] if data.get("truncated") is True else [])
    if name == "dotfiles_status":
        available = data.get("git_available")
        branch = data.get("branch")
        pending = data.get("pending_changes")
        if type(available) is not bool or not isinstance(branch, str):
            return None
        if available and _number(pending) is None:
            return None
        lines = [f"Branch: {_text(branch)}.",
                 f"Pending changes: {pending}." if available else "Git status unavailable; cleanliness unknown."]
        tracking = data.get("tracking")
        if tracking is not None and isinstance(tracking, str):
            lines.append(f"Tracking: {_text(tracking)}.")
        if details:
            changes = data.get("changes")
            if isinstance(changes, list):
                for item in changes[:10]:
                    if isinstance(item, dict) and isinstance(item.get("path"), str):
                        lines.append(_text(item["path"]))
        warnings = ["Change list is partial."] if data.get("truncated_changes") is True else []
        return _bounded(lines, warnings)
    if name == "theme_status":
        q = question.lower()
        choices = bool(re.search(r"\b(available|list|choices|options)\b", q, re.I))
        want_layout = _asked(q, ("layout",))
        want_palette = _asked(q, ("palette",))
        if choices:
            requested = []
            if want_layout:
                requested.append(("layouts", "Layouts"))
            if want_palette:
                requested.append(("palettes", "Palettes"))
            if not requested:
                requested = [("layouts", "Layouts"), ("palettes", "Palettes")]
            parts = []
            for key, label in requested:
                values = data.get(key)
                if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                    return None
                shown = [_text(value) for value in values[:12]]
                if len(values) > 12:
                    shown.append(f"+{len(values) - 12} more choices")
                parts.append(f"{label}: {', '.join(shown) if shown else 'unavailable'}.")
            return _bounded(parts, [])
        requested = []
        if want_layout:
            requested.append(("current_layout", "Current layout"))
        if want_palette:
            requested.append(("current_palette", "Current palette"))
        if not requested:
            requested = [("current_layout", "Current layout"), ("current_palette", "Current palette")]
        parts = []
        for key, label in requested:
            value = data.get(key)
            if not isinstance(value, str):
                return None
            parts.append(f"{label}: {_text(value)}.")
        parts.append("Current selection only; desktop appearance is not verified.")
        return _bounded(parts, [])
    return None


def web_results(data: dict, *, snippets: bool = True) -> str | None:
    """Numbered source list; titles, URLs and snippets are untrusted and sanitized."""
    results, query = data.get("results"), data.get("query")
    if not isinstance(results, list) or not isinstance(query, str):
        return None
    warnings = []
    unresponsive = _number(data.get("unresponsive_engines"))
    if unresponsive:
        warnings.append(f"{unresponsive} search {'engine' if unresponsive == 1 else 'engines'} did not respond; results may be incomplete.")
    if not results:
        return _bounded(["SearXNG returned no results for that query."], warnings)
    lines = ["Sources (SearXNG, unverified):"]
    for index, item in enumerate(results[:10], 1):
        if not isinstance(item, dict) or not isinstance(item.get("url"), str):
            return None
        title = item.get("title")
        lines.append(f"{index}. {_text(title) if isinstance(title, str) and title else '(untitled)'}")
        lines.append(f"   {_text(item['url'])}")
        snippet = item.get("snippet")
        if snippets and isinstance(snippet, str) and snippet:
            lines.append(f"   {_text(snippet)[:160]}")
    return _bounded(lines, warnings)


def answer(result: ToolResult, question: str = "", *, details: bool = False,
           metric: str | None = None) -> str | None:
    """Summarize supported tool records without model prose or raw data dumps."""
    if not isinstance(result, ToolResult) or not isinstance(result.data, dict):
        return None
    data = result.data
    if metric is None and re.search(r"\b(?:how\s+many\s+files|(?:number|count)\s+of\s+files|file\s+count|count\s+(?:the\s+)?files)\b", question, re.I):
        metric = "files"
    if result.status in ("preview", "denied", "error"):
        messages = {"preview": "Preview only; nothing was executed.",
                     "denied": "Not approved for this call; it did not execute.",
                    "error": "The operation failed; do not assume changes were not made."}
        if result.status == "error" and isinstance(data.get("message"), str):
            # Known runner diagnostics are user-facing evidence; sanitize and cap.
            detail = _text(data["message"])
            if detail:
                return _bounded([detail[:400]], [])
        return messages[result.status]
    if result.status not in ("ok", "started"):
        return None
    if result.status == "started":
        if result.name == "launch_app" and isinstance(data.get("app"), str) and _number(data.get("pid")) is not None:
            return _bounded([f"Launch requested for {_text(data['app'])} (PID {_number(data['pid'])}); window visibility is not verified."], [])
        return None
    if result.name == "directory_usage":
        return _directory(data, question, details, metric)
    if result.name == "system_status":
        return _system(data, question)
    if result.name in ("processes", "find_files", "desktop_status", "power_status", "plugin_status",
                       "display_status", "dotfiles_status", "theme_status", "alerts_status"):
        return _status_tool(result.name, data, question, details)
    if result.name == "bash" and isinstance(data.get("stdout"), str) and data.get("snapshot_only") is True:
        stdout = data["stdout"].splitlines()
        output_lines = [f"  | {_text(line)}" for line in stdout[:200]]
        if not output_lines:
            output_lines = ["  | Command completed with no output."]
        warnings = ["Incomplete snapshot."] if data.get("truncated_snapshot") is True else []
        if data.get("output_truncated") is True or len(stdout) > 200:
            warnings.append("Command output truncated.")
        return _bounded(["Read-only command output (filtered snapshot):", *output_lines], warnings)
    if result.name == "bash" and data.get("executor") == "read_only_bubblewrap_snapshot" and isinstance(data.get("stdout"), str):
        stdout = data["stdout"].splitlines()
        output_lines = [f"  | {_text(line)}" for line in stdout[:200]]
        if not output_lines:
            output_lines = ["  | Command completed with no output."]
        warnings = ["Incomplete snapshot."] if data.get("truncated_snapshot") is True else []
        if data.get("output_truncated") is True or len(stdout) > 200:
            warnings.append("Command output truncated.")
        return _bounded(["Read-only command output (filtered snapshot):", *output_lines], warnings)
    if result.name == "bash" and data.get("executor") == "guarded_live_size_metadata" and isinstance(data.get("root"), str) and isinstance(data.get("path"), str):
        size, unit, kind = data.get("reported_size_bytes"), data.get("reported_unit"), data.get("reported_size_kind")
        if metric is None and _number(size) is not None and unit in ("h", "b", "k") and kind in ("logical", "allocated"):
            shown = _human_bytes(size) if unit == "h" else f"{size} B" if unit == "b" else f"{(size + 1023) // 1024} KiB"
            text = f"{shown} {kind} (filtered view)."
            warnings = ["Incomplete scan; partial total."] if data.get("truncated_scan") is True else []
            if details:
                details_text = _directory(data, question, True, "logical" if kind == "logical" else "size")
                return _bounded([text, details_text or ""], warnings)
            return _bounded([text], warnings)
        return _directory(data, question, details, metric)
    if result.name == "bash" and data.get("executor") == "guarded_fd_file_operation":
        paths = data.get("changed_paths")
        if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
            return None
        if "exit_code" in data and (type(data["exit_code"]) is not int or data["exit_code"] != 0):
            return None
        return _bounded([f"Approved file operation completed for {', '.join(_text(path) for path in paths)}."], [])
    if result.name in ("set_theme", "apply_theme") and data.get("desktop_verified") is False:
        if type(data.get("exit_code")) is not int or data["exit_code"] != 0 or not isinstance(data.get("selected"), dict):
            return None
        return "Theme helper completed; desktop appearance is not verified."
    if result.name in ("set_volume", "set_brightness"):
        percent = data.get("requested_percent")
        if type(percent) is int and 0 <= percent <= 100:
            label = "Volume" if result.name == "set_volume" else "Brightness"
            return f"{label} change requested: {percent}%."
    if result.name == "web_search":
        return web_results(data)
    if result.name == "doctor":
        model, host, digest = (data.get(key) for key in ("model", "host", "digest"))
        size, context, keep_alive = (data.get(key) for key in ("size_bytes", "context", "keep_alive"))
        if not all(isinstance(value, str) and value for value in (model, host, digest)):
            return None
        if _number(size) is None or _number(context) is None or not isinstance(keep_alive, (str, int)) or type(keep_alive) is bool:
            return None
        return _bounded([f"Local model: {_text(model)}.", f"Host: {_text(host)}.",
                         f"Artifact: {_text(digest)} ({_human_bytes(size)}).",
                         f"Context: {context} tokens; keep-alive: {_text(keep_alive)}."], [])
    return None

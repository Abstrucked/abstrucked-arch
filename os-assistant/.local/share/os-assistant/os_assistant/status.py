"""Read-only status for this machine and its dotfiles checkout.

The collectors and parsers here never change state: they turn already
authorized text (helper output, state files, /proc, /sys) into bounded,
validated values. Helper output is treated as untrusted text, so every field
is pattern-checked and length-capped before it reaches the model.
"""

import hashlib
import os
from pathlib import Path
import re
import stat
import time
import unicodedata

from . import diagnostics


REPOSITORY = Path(__file__).resolve().parents[5]
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state")))
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
THEMES = REPOSITORY / "themes"

_PROC_ENTRY_LIMIT = 2048
_LABEL_LIMIT = 96
_PATH_LIMIT = 512
_ENTRY_LIMIT = 20
_MONITOR_LIMIT = 8
_FILE_LIMIT = 4096
_SCAN_ENTRIES = 256
_SCAN_SECONDS = 1.0
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
_PLUGIN_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_BRANCH = re.compile(r"## (?P<branch>[A-Za-z0-9._/-]+?)(?:\.\.\.(?P<upstream>[A-Za-z0-9._/-]{1,128}))?"
                     r"(?: \[(?P<tracking>[^\]\n]{1,64})\])?\Z")
_ENTRY = re.compile(r"(?P<code>[ MADRCUT?!]{2}) (?P<path>.+)\Z", re.DOTALL)
_MANIFEST = re.compile(r"^NAME=(?:\"(?P<double>[^\"\n]{1,96})\"|'(?P<single>[^'\n]{1,96})'"
                       r"|(?P<plain>[A-Za-z0-9 ._-]{1,96}))$")
_PROCESSES = ("awesome", "picom", "waybar", "swaync", "Hyprland", "hyprland", "tailscaled")


def _clean(value: str | None, limit: int) -> str | None:
    """Return a control-free, length-capped label, else None."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value or len(value) > limit or any(unicodedata.category(char).startswith("C") for char in value):
        return None
    return value


def trusted_helper(path: Path) -> Path | None:
    """Return path when it is a regular, executable, trusted-owner helper file.

    Symlinks, special files, unknown owners and world/group-writable files are
    refused. Read-only status degrades to unavailable instead of raising.
    """
    try:
        if path.is_symlink() or not path.is_file():
            return None
        info = path.stat()
        if (info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022
                or not stat.S_ISREG(info.st_mode) or not os.access(path, os.X_OK)):
            return None
        # A safe leaf in a replaceable parent is not a trusted helper.
        for parent in path.absolute().parents:
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or (info.st_mode & 0o022 and not sticky_root)):
                return None
        return path
    except OSError:
        return None


def helper_snapshot(path: Path) -> str:
    """Metadata verification for fixed read-only helpers, including their parents."""
    if trusted_helper(path) is None:
        return ""
    try:
        info = path.stat()
        fields = [(str(path), info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                   info.st_size, info.st_mtime_ns, info.st_ctime_ns)]
        for parent in path.absolute().parents:
            info = parent.lstat()
            fields.append((str(parent), info.st_dev, info.st_ino, info.st_uid, info.st_mode))
        return hashlib.sha256(repr(fields).encode()).hexdigest()
    except OSError:
        return ""


def display_dependencies() -> list[str]:
    """Fixed utilities the helper's list branch runs; a seam so tests need no desktop tools."""
    dependencies = ["/bin/bash", "/usr/bin/sort", "/usr/bin/column", "/usr/bin/readlink"]
    dependencies += (["/usr/bin/hyprctl", "/usr/bin/jq"] if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
                     else ["/usr/bin/xrandr", "/usr/bin/awk"])
    return dependencies


def display_snapshot() -> str:
    """Trust the fixed helper and the root-owned dependencies its list branch uses."""
    helper = REPOSITORY / "scripts/.local/bin/display-detect"
    fingerprint = helper_snapshot(helper)
    if not fingerprint:
        return ""
    dependencies = display_dependencies()
    fields = [fingerprint]
    try:
        for name in dependencies:
            path = Path(name).resolve(strict=True)
            if path.stat().st_uid != 0:
                return ""
            # Allow distribution-managed links (e.g. awk -> gawk), never user-owned parents.
            for parent in path.parents:
                info = parent.stat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    return ""
            value = helper_snapshot(path)
            if not value:
                return ""
            fields.append((name, str(path), value))
        return hashlib.sha256(repr(fields).encode()).hexdigest()
    except (OSError, ValueError, RuntimeError):
        return ""


def display_wallpaper_set() -> str:
    """Supply a validated set so the shell helper never opens state files itself."""
    saved = _read_line(STATE_HOME / "display/wallpaper-set")
    if saved and _NAME.fullmatch(saved):
        return saved
    palette = _read_line(STATE_HOME / "themes/current")
    return palette if palette and _NAME.fullmatch(palette) else "default"


def git_argv() -> tuple[str, ...]:
    """One local-only Git status request, with optional writes/hooks disabled."""
    return ("/usr/bin/git", "--no-optional-locks", "--no-replace-objects",
            "-c", "core.fsmonitor=false", "-c", "core.untrackedCache=false",
            "-c", "core.hooksPath=/dev/null", "-c", "core.attributesFile=/dev/null",
            "-c", "core.excludesFile=/dev/null",
            "--git-dir", str(REPOSITORY / ".git"), "--work-tree", str(REPOSITORY),
            "-C", str(REPOSITORY), "status", "--porcelain=v1", "--branch",
            "--untracked-files=normal", "--ignore-submodules=all", "--no-renames", "-z")


def git_snapshot() -> str:
    """Verify local Git metadata before config/status; linked worktrees are unavailable."""
    executable = helper_snapshot(Path("/usr/bin/git"))
    if not executable:
        return ""
    fields = [executable]
    try:
        parents = [REPOSITORY / ".git", *REPOSITORY.absolute().parents, REPOSITORY]
        if os.path.lexists(REPOSITORY / ".git/info"):
            parents.append(REPOSITORY / ".git/info")
        for parent in parents:
            info = parent.lstat()
            sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or (info.st_mode & 0o022 and not sticky_root)):
                return ""
            fields.append((str(parent), info.st_dev, info.st_ino, info.st_uid, info.st_mode))
        # Worktree config would add a second config source at repository startup.
        # This phase deliberately supports only a regular checkout's local config.
        if any(os.path.lexists(REPOSITORY / ".git" / name) for name in ("config.worktree", "commondir")):
            return ""
        for name in ("config", "HEAD", "index", "info/exclude", "info/attributes", "info/sparse-checkout"):
            path = REPOSITORY / ".git" / name
            if not os.path.lexists(path):
                fields.append((name, "missing"))
                continue
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid())
                    or info.st_mode & 0o022 or (name != "index" and info.st_size > 65536)):
                return ""
            fields.append((name, info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                           info.st_size, info.st_mtime_ns, info.st_ctime_ns))
        return hashlib.sha256(repr(fields).encode()).hexdigest()
    except OSError:
        return ""


def _read_text(path: Path, limit: int, *, follow_parents: bool = False) -> str | None:
    """Bounded, nonblocking regular-file read; state paths also refuse parent links."""
    parent_fd = -1
    fd = -1
    try:
        if not path.is_absolute() or ".." in path.parts:
            return None
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        if follow_parents:
            fd = os.open(path, flags)
        else:
            parent_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            for component in path.parts[1:-1]:
                child_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   dir_fd=parent_fd)
                os.close(parent_fd)
                parent_fd = child_fd
            fd = os.open(path.name, flags, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            return None
        return raw.decode("utf-8")
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        if fd >= 0:
            os.close(fd)
        if parent_fd >= 0:
            os.close(parent_fd)


def _read_line(path: Path, limit: int = 128, *, follow_parents: bool = False) -> str | None:
    text = _read_text(path, limit, follow_parents=follow_parents)
    return text.strip() if text is not None else None


def _active_palette() -> str | None:
    # out is the intentional, atomic generation link; do not follow it outside themes.
    try:
        root = THEMES.resolve(strict=True)
        if root != THEMES.absolute():
            return None
        generation = (root / "out").resolve(strict=True)
        relative = generation.relative_to(root)
        if not relative.parts or relative.parts[0] not in {"out", ".generations"}:
            return None
        return _read_line(generation / ".theme-name")
    except (OSError, ValueError, RuntimeError):
        return None


def link_matches(path: Path, expected: Path) -> bool:
    try:
        return path.is_symlink() and path.resolve(strict=True) == expected.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        return False


def _process_names() -> tuple[set[str], bool]:
    names: set[str] = set()
    truncated = False
    deadline = time.monotonic() + _SCAN_SECONDS
    try:
        with os.scandir("/proc") as entries:
            for index, entry in enumerate(entries):
                if index >= _PROC_ENTRY_LIMIT or time.monotonic() >= deadline:
                    truncated = True
                    break
                if not entry.name.isascii() or not entry.name.isdecimal():
                    continue
                try:
                    owner = entry.stat(follow_symlinks=False).st_uid
                except OSError:
                    truncated = True
                    continue
                if owner not in (os.getuid(), 0):
                    continue
                name = _read_line(Path(entry.path) / "comm")
                if name is None:
                    truncated = True
                # Only report this user's desktop apps; tailscaled is usually root.
                elif name in _PROCESSES and (owner == os.getuid() or name == "tailscaled"):
                    names.add(name)
    except OSError:
        truncated = True
    return names, truncated


def collect_desktop_status() -> dict:
    """Describe the running session, theme selection and wallpaper set.

    Reads fixed state/attribute files and bounded /proc scans only. Values that
    cannot be read are reported as unavailable or unset; this never reports
    whether the desktop actually looks correct.
    """
    processes, truncated = _process_names()
    running = {name: True if name in processes else "unavailable" if truncated else False for name in _PROCESSES}
    if "Hyprland" in processes or "hyprland" in processes:
        compositor = "hyprland"
    elif "awesome" in processes:
        compositor = "awesome"
    else:
        compositor = "unavailable"
    layout = os.environ.get("AWESOME_THEME") or _read_line(STATE_HOME / "awesome" / "theme-layout")
    palette = _active_palette() or _read_line(STATE_HOME / "themes" / "current")
    wallpaper = _read_line(STATE_HOME / "display" / "wallpaper-set")
    return {
        "compositor": compositor,
        "compositor_running": running,
        "display_session": bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
        "layout": layout if layout and _NAME.fullmatch(layout) else "unset",
        "palette": palette if palette and _NAME.fullmatch(palette) else "unset",
        "wallpaper_set": wallpaper if wallpaper and _NAME.fullmatch(wallpaper) else "unset",
        "truncated_process_scan": truncated,
        "process_report_kind": "process_presence_not_service_health",
        "desktop_verified": False,
    }


def collect_power_status() -> dict:
    """Report the CPU governor, platform profile and power-mode backend.

    The backend is only reported, never switched: changing power modes needs a
    working backend and a separately gated action.
    """
    # Kernel-managed cpufreq directories can be symlinks; state-file readers cannot.
    governor = _read_line(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"), follow_parents=True)
    profile = _read_line(Path("/sys/firmware/acpi/platform_profile"), follow_parents=True)
    if trusted_helper(Path("/usr/bin/powerprofilesctl")):
        backend = "powerprofilesctl"
    elif trusted_helper(Path("/usr/local/lib/ryzenadj-power-profile")):
        backend = "ryzenadj-wrapper"
    else:
        backend = "unavailable"
    return {
        "cpu_governor": _clean(governor, _LABEL_LIMIT) or "unavailable",
        "platform_profile": _clean(profile, _LABEL_LIMIT) or "unavailable",
        "power_mode_backend": backend,
        "backend_report_kind": "executable_presence_only",
        "power_mode_change_supported": False,
        "battery": diagnostics.collect_system_status()["battery"],
    }


def collect_plugin_status() -> dict:
    """List this checkout's optional plugins and whether each is enabled."""
    enabled: set[str] = set()
    state = _read_text(STATE_HOME / "plugins" / "enabled", _FILE_LIMIT)
    state_available = state is not None
    lines = state.splitlines() if state is not None else []
    if len(lines) > _SCAN_ENTRIES or any(line.strip() and not _PLUGIN_ID.fullmatch(line.strip()) for line in lines):
        state_available = False
    elif state_available:
        enabled = {line.strip() for line in lines if line.strip()}
    plugins = []
    truncated = False
    directory_available = True
    deadline = time.monotonic() + _SCAN_SECONDS
    try:
        with os.scandir(REPOSITORY / "plugins") as entries:
            for index, entry in enumerate(entries):
                if index >= _SCAN_ENTRIES or time.monotonic() >= deadline:
                    truncated = True
                    break
                if not _PLUGIN_ID.fullmatch(entry.name) or not entry.is_dir(follow_symlinks=False):
                    continue
                manifest = _read_text(Path(entry.path) / "manifest.conf", _FILE_LIMIT)
                if manifest is None:
                    if os.path.lexists(Path(entry.path) / "manifest.conf"):
                        truncated = True
                    continue
                name = None
                for line in manifest.splitlines():
                    match = _MANIFEST.fullmatch(line.strip())
                    if match:
                        name = match.group("double") or match.group("single") or match.group("plain")
                        break
                plugins.append({"id": entry.name, "name": _clean(name, _LABEL_LIMIT) or entry.name,
                                "enabled": entry.name in enabled if state_available else "unavailable"})
    except OSError:
        directory_available = False
        truncated = True
    if directory_available and not truncated and enabled - {item["id"] for item in plugins}:
        # pluginctl rejects unknown enabled IDs too; do not present stale state as valid.
        state_available = False
        for item in plugins:
            item["enabled"] = "unavailable"
    plugins.sort(key=lambda item: item["id"])
    return {"plugins": plugins[:_ENTRY_LIMIT], "plugins_total": len(plugins) if directory_available and not truncated else None,
            "enabled_state_available": state_available, "truncated": truncated or len(plugins) > _ENTRY_LIMIT}


def collect_dotfiles_status(git_text: str | None, *, config_linked: bool, launcher_linked: bool) -> dict:
    """Parse bounded `git status` text plus link facts into validated fields.

    Only branch names, tracking hints, status codes and repository-relative
    paths are reported. No file contents are read, and anything that does not
    match the expected shapes is dropped.
    """
    branch, upstream, tracking = "unavailable", "unavailable", None
    changes: list[dict] = []
    pending, omitted = 0, 0
    records = git_text.split("\0") if git_text is not None and len(git_text) <= 8192 and "\0" in git_text else []
    available = bool(records and records[0].startswith("## "))
    for line in records:
        if line.startswith("## "):
            match = _BRANCH.fullmatch(line)
            if match:
                branch = match.group("branch")
                upstream = match.group("upstream") or "none"
                tracking = _clean(match.group("tracking"), 64)
            elif line == "## HEAD (no branch)":
                branch, upstream = "detached", "none"
            elif line.startswith("## No commits yet on "):
                branch, upstream = _clean(line.removeprefix("## No commits yet on "), 128) or "unavailable", "none"
            continue
        parsed = _ENTRY.fullmatch(line)
        path = _clean(parsed.group("path"), _PATH_LIMIT) if parsed else None
        if parsed:
            pending += 1
        if path is None:
            omitted += bool(line)
            continue
        if Path(path).is_absolute() or ".." in Path(path).parts:
            omitted += 1
            continue
        if len(changes) < _ENTRY_LIMIT:
            changes.append({"code": parsed.group("code"), "path": path})
    return {
        "branch": _clean(branch, 128) or "unavailable",
        "upstream": _clean(upstream, 128) or "none",
        "tracking": tracking,
        "git_available": available,
        "pending_changes": pending if available else None,
        "change_count_kind": "porcelain_records_untracked_dirs_may_be_collapsed",
        "changes_shown": len(changes),
        "changes": changes,
        "truncated_changes": pending > len(changes) or omitted > 0,
        "assistant_config_linked": config_linked,
        "assistant_launcher_linked": launcher_linked,
    }


def parse_display_list(text: str | None) -> dict:
    """Parse bounded monitor output; anything unrecognized is dropped."""
    monitors = []
    truncated = False
    context = {"desktop_verified": False, "report_kind": "helper_display_plan_not_verified_current_state"}
    if text is None or len(text.encode("utf-8")) > 8192:
        return {"monitors": "unavailable", "monitors_total": None, "truncated": text is not None, **context}
    for line in text.splitlines():
        # display-detect list has eight columns; whitespace in the last path is preserved.
        fields = line.split(None, 7)
        if len(fields) not in (7, 8):
            truncated = truncated or bool(line.strip())
            continue
        if len(fields) == 7:
            fields.append("")
        name, width, height, rate, kind, x, y, wallpaper = fields
        if (not _NAME.fullmatch(name) or not re.fullmatch(r"[0-9]{1,5}", width)
                or not re.fullmatch(r"[0-9]{1,5}", height) or int(width) == 0 or int(height) == 0
                or not re.fullmatch(r"[0-9]{1,3}(?:\.[0-9]{1,3})?", rate) or float(rate) == 0
                or kind not in {"internal", "wide", "ultrawide"}
                or not re.fullmatch(r"[+-]?[0-9]{1,5}", x) or not re.fullmatch(r"[+-]?[0-9]{1,5}", y)
                or (wallpaper and _clean(wallpaper, _PATH_LIMIT) is None)):
            truncated = True
            continue
        if len(monitors) >= _MONITOR_LIMIT:
            truncated = True
            break
        monitors.append({"name": name, "width": int(width), "height": int(height),
                         "refresh_hz": float(rate), "class": kind, "position": f"{int(x)},{int(y)}",
                          "wallpaper": _clean(wallpaper, _PATH_LIMIT) or "unavailable"})
    if not monitors:
        return {"monitors": "unavailable", "monitors_total": None, "truncated": truncated, **context}
    return {"monitors": monitors, "monitors_total": None if truncated else len(monitors),
            "truncated": truncated, **context}

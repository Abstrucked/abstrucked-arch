"""Explicit trust in this checkout's theme pipeline, never an arbitrary helper path.

The helper executes repository Lua, hooks and reload commands as the user. This
is a separately opted-in integration, not the root-owned generic app launcher
and not an OS sandbox. Metadata snapshots detect changes across approval; they
cannot defend against a compromised account racing execution.
"""

import hashlib
import os
from pathlib import Path
import re
import stat

from .contracts import PolicyError


THEME_ROOT = Path(__file__).resolve().parents[5] / "themes"
_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}\Z")
_MAX_ENTRIES = 1024
_MAX_NAMES = 128


def _trusted(path: Path) -> os.stat_result:
    info = path.stat()
    sticky_root = info.st_uid == 0 and stat.S_ISDIR(info.st_mode) and info.st_mode & stat.S_ISVTX
    if info.st_uid not in (0, os.getuid()) or (info.st_mode & 0o022 and not sticky_root):
        raise PolicyError("Theme integration requires trusted-owner, non-writable-by-others files and parents.")
    if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
        raise PolicyError("Theme integration refuses special files.")
    return info


def _parents(path: Path) -> None:
    for parent in path.resolve(strict=True).parents:
        _trusted(parent)


def _names(root: Path, *, palettes: bool) -> list[str]:
    names = []
    with os.scandir(root) as entries:
        for index, entry in enumerate(entries):
            if index >= _MAX_ENTRIES:
                raise PolicyError("Theme catalogue exceeded its entry limit.")
            name = entry.name.removesuffix(".lua") if palettes else entry.name
            if not _NAME.fullmatch(name):
                continue
            candidate = root / entry.name if palettes else root / entry.name / "theme.lua"
            if palettes and (not entry.name.endswith(".lua") or entry.is_symlink()):
                continue
            if candidate.is_file():
                _trusted(candidate.resolve(strict=True))
                names.append(name)
            if len(names) > _MAX_NAMES:
                raise PolicyError("Theme catalogue exceeded its name limit.")
    return sorted(names)


def _layout_root() -> Path:
    installed = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "awesome/themes"
    if installed.is_dir() and _names(installed, palettes=False):
        return installed
    return THEME_ROOT.parent / "awesome/.config/awesome/themes"


def catalogue() -> dict:
    """Discover only known theme metadata; do not execute Lua, hooks or themectl."""
    try:
        helper = THEME_ROOT / "themectl"
        if helper.is_symlink() or not os.access(helper, os.X_OK):
            raise PolicyError("This checkout's themectl helper is unavailable or is a symlink.")
        if not stat.S_ISREG(_trusted(helper).st_mode):
            raise PolicyError("This checkout's themectl helper must be a regular file.")
        _parents(helper)
        layout_root = _layout_root()
        layouts = _names(layout_root, palettes=False)
        palettes = _names(THEME_ROOT / "palettes", palettes=True)
        if not layouts or not palettes:
            raise PolicyError("This checkout has no usable layouts or palettes.")
        return {"layouts": layouts, "palettes": palettes}
    except (OSError, ValueError, RuntimeError):
        raise PolicyError("This checkout's theme catalogue is unavailable.") from None


def snapshot() -> str:
    """Fingerprint trusted pipeline metadata, excluding generated output/state."""
    try:
        digest = hashlib.sha256()
        count = 0

        def add(path: Path) -> None:
            nonlocal count
            count += 1
            if count > _MAX_ENTRIES:
                raise PolicyError("Theme pipeline exceeded its verification limit.")
            if path.is_symlink():
                raise PolicyError("Theme pipeline source symlinks are not supported.")
            info = _trusted(path)
            fields = (str(path), info.st_dev, info.st_ino, info.st_uid, info.st_mode)
            if stat.S_ISREG(info.st_mode):
                fields += (info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            digest.update(repr(fields).encode("utf-8"))
            if stat.S_ISDIR(info.st_mode):
                with os.scandir(path) as entries:
                    children = []
                    for index, entry in enumerate(entries):
                        if index >= _MAX_ENTRIES:
                            raise PolicyError("Theme pipeline exceeded its verification limit.")
                        if entry.name in {"out", ".generations", ".apply.lock", ".pluginctl.lock"}:
                            continue
                        children.append(path / entry.name)
                for child in sorted(children):
                    add(child)

        for path in (THEME_ROOT, THEME_ROOT.parent / "plugins"):
            _parents(path)
            add(path)
        # Fixed helper dependencies outside those trees, including live layout modules.
        installed = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "awesome"
        dependencies = [THEME_ROOT.parent / "scripts/.local/bin/display-detect",
                        THEME_ROOT.parent / "scripts/config_syntax.py"]
        for module in ("theme-layout.lua", "theme-session.lua"):
            dependencies.append(THEME_ROOT.parent / "awesome/.config/awesome" / module)
            if (installed / module).exists():
                dependencies.append((installed / module).resolve(strict=True))
        layout_root = _layout_root()
        for name in _names(layout_root, palettes=False):
            dependencies.append((layout_root / name / "theme.lua").resolve(strict=True))
        for path in sorted(set(dependencies)):
            _parents(path)
            add(path)
        return digest.hexdigest()
    except (OSError, ValueError, RuntimeError):
        raise PolicyError("Theme pipeline is unavailable or cannot be verified.") from None


def prepare(arguments: dict) -> tuple[tuple[str, ...], str]:
    available = catalogue()
    if not arguments or not arguments.keys() <= {"layout", "palette"}:
        raise PolicyError("Select a layout, palette, or both; no other theme arguments are allowed.")
    for key, value in arguments.items():
        if value not in available["layouts" if key == "layout" else "palettes"]:
            raise PolicyError("Unknown theme layout or palette; check theme_status.")
    argv = [str(THEME_ROOT / "themectl"), "set"]
    if "layout" in arguments:
        argv.append(arguments["layout"])
    if "palette" in arguments:
        argv.extend(("--colors", arguments["palette"]))
    return tuple(argv), snapshot()


def current_value(text: str, choices: list[str]) -> str:
    """Never expose unexpected contents from a theme selection/state file."""
    name = text.strip()
    return name if name in choices else "unavailable"

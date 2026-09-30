#!/bin/bash
# Publish the generated OpenCode TUI theme without editing user-owned cli.json.
set -euo pipefail

python3 - "$THEME_DIR/out/opencode-theme.json" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile

source = Path(sys.argv[1])
config_home = Path(os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config"))
state_home = Path(os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local/state"))
destination = config_home / "opencode" / "themes" / "dotfiles.json"
marker = state_home / "themes" / "opencode-dotfiles.sha256"

content = source.read_bytes()
theme = json.loads(content)
if not isinstance(theme, dict) or not isinstance(theme.get("base"), dict):
    raise ValueError("generated OpenCode theme is incomplete")

# Check the full generated V2 contract before touching the published file.
# No OpenCode installation or runtime schema download is required.
base = theme["base"]
modes = {name for name in ("light", "dark") if name in theme}
if len(modes) != 1:
    raise ValueError("generated OpenCode theme must provide exactly one palette mode")
mode = theme[next(iter(modes))]
hues = ("gray", "red", "orange", "yellow", "green", "cyan", "blue", "purple")
if not isinstance(mode, dict) or not isinstance(mode.get("hue"), dict):
    raise ValueError("generated OpenCode theme has no hue palette")


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        raise ValueError(f"invalid generated OpenCode color: {value!r}")


for hue in hues:
    ramp = mode["hue"].get(hue)
    if not isinstance(ramp, dict) or set(ramp) != {str(step) for step in range(100, 1000, 100)}:
        raise ValueError(f"incomplete OpenCode hue: {hue}")
    for value in ramp.values():
        color(value)
for alias in ("accent", "interactive", "neutral"):
    if mode["hue"].get(alias) not in {f"$hue.{hue}" for hue in hues}:
        raise ValueError(f"invalid OpenCode hue alias: {alias}")
categorical = base.get("categorical")
if not isinstance(categorical, list) or not categorical or any(
    not isinstance(hue, str) or hue not in mode["hue"] for hue in categorical
):
    raise ValueError("invalid OpenCode categorical hues")

required = ["text.base", "text.muted", "background.base", "border.base", "scrollbar.base"]
required += [f"background.raised.{level}" for level in ("base", "high", "max")]
required += [f"diff.text.{kind}" for kind in ("added", "removed", "context", "hunkHeader")]
required += [f"diff.background.{kind}" for kind in ("added", "removed", "context")]
required += [f"diff.highlight.{kind}" for kind in ("added", "removed")]
required += ["diff.lineNumber.text", "diff.lineNumber.background.added", "diff.lineNumber.background.removed"]
required += [f"syntax.{kind}" for kind in (
    "comment", "keyword", "function", "variable", "string", "number", "type", "operator", "punctuation",
)]
required += [f"markdown.{kind}" for kind in (
    "text", "heading", "link", "linkText", "code", "blockQuote", "emphasis", "strong",
    "horizontalRule", "listItem", "listEnumeration", "image", "imageText", "codeBlock",
)]
for group in ("text", "background"):
    for kind in ("primary", "secondary", "destructive"):
        required.append(f"{group}.action.{kind}.base")
    required.append(f"{group}.formfield.base")
    for kind in ("error", "warning", "success", "info"):
        required.append(f"{group}.feedback.{kind}.base")
for path in required:
    value = base
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"missing generated OpenCode token: {path}")
        value = value[key]
    color(value)


def validate_colors(tokens):
    for value in tokens.values():
        if isinstance(value, dict):
            validate_colors(value)
        else:
            color(value)


validate_colors({key: value for key, value in base.items() if key != "categorical"})
content_hash = hashlib.sha256(content).hexdigest()


def atomic_write(path, data, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.themectl-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


destination.parent.mkdir(parents=True, exist_ok=True)
exists = os.path.lexists(destination)
is_symlink = destination.is_symlink()
previous = None
if exists:
    if not destination.is_file() and not (is_symlink and not destination.exists()):
        raise ValueError(f"refusing to replace non-file OpenCode theme: {destination}")
    try:
        previous = destination.read_bytes()
    except FileNotFoundError:
        # A dangling symlink is still user data; back up the link before replacing it.
        previous = None

if exists and previous == content and not is_symlink:
    atomic_write(marker, (content_hash + "\n").encode())
    raise SystemExit(0)

managed_hash = marker.read_text().strip() if marker.is_file() else ""
previous_hash = hashlib.sha256(previous).hexdigest() if previous is not None else ""
if exists and (is_symlink or previous_hash != managed_hash):
    backup_dir = Path(os.environ.get("DOTFILES_BACKUP_ROOT", str(Path.home() / ".dotfiles-backups"))) / "themes"
    backup_dir.mkdir(parents=True, exist_ok=True)
    base = backup_dir / "opencode-dotfiles.json.orig"
    backup = base
    suffix = 1
    while os.path.lexists(backup):
        backup = Path(f"{base}.{suffix}")
        suffix += 1
    if is_symlink:
        os.symlink(os.readlink(destination), backup)
    else:
        shutil.copy2(destination, backup)

mode = stat.S_IMODE(destination.stat().st_mode) if exists and not is_symlink else 0o644
atomic_write(destination, content, mode)
atomic_write(marker, (content_hash + "\n").encode())
PY

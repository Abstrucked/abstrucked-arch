#!/bin/bash
# herdr's config.toml also holds your keybindings, so only replace the [theme*]
# sections and leave everything else alone.
set -euo pipefail
conf="${XDG_CONFIG_HOME:-$HOME/.config}/herdr/config.toml"
[[ -f "$conf" ]] || exit 0
python3 - "$conf" "$THEME_DIR/out/herdr-theme.toml" <<'PY'
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import tomllib

# Preserve stow-managed symlinks and the target file's permissions.
conf = Path(sys.argv[1]).resolve(strict=True)
original = conf.read_bytes()
before = tomllib.loads(original.decode())
fragment = Path(sys.argv[2]).read_text()
theme = tomllib.loads(fragment)
if set(theme) != {"theme"}:
    raise ValueError("generated fragment must contain only theme settings")
lines = []
skip = False
for line in original.decode().splitlines(keepends=True):
    if re.match(r"^\s*\[", line):
        skip = bool(re.match(r"^\s*\[\s*(?:theme|\"theme\"|'theme')\s*(?:\]|\.)", line))
    if not skip:
        lines.append(line)
updated = "".join(lines).rstrip() + "\n\n" + fragment
after = tomllib.loads(updated)
if after != dict(before, theme=theme["theme"]):
    raise ValueError("theme replacement would change unrelated settings")

fd, temporary = tempfile.mkstemp(prefix=".themectl-", dir=conf.parent)
try:
    with os.fdopen(fd, "w") as stream:
        stream.write(updated)
        stream.flush()
        os.fsync(stream.fileno())
    shutil.copymode(conf, temporary)
    backup_dir = Path(os.environ.get("DOTFILES_BACKUP_ROOT", str(Path.home() / ".dotfiles-backups"))) / "themes"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_fd, backup = tempfile.mkstemp(prefix="herdr-config.toml.", dir=backup_dir)
    with os.fdopen(backup_fd, "wb") as stream:
        stream.write(original)
    if conf.read_bytes() != original:
        raise ValueError("herdr config changed during theme update; retry")
    os.replace(temporary, conf)
finally:
    Path(temporary).unlink(missing_ok=True)
PY
herdr server reload-config >/dev/null 2>&1 || true

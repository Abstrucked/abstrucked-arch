#!/bin/bash
# rnmui rewrites its own config when you press t, so set just the theme line.
set -euo pipefail
conf="${XDG_CONFIG_HOME:-$HOME/.config}/rnmui/config.toml"
mkdir -p "$(dirname "$conf")"
python3 - "$conf" "$THEME_RNMUI" <<'PY'
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import tomllib

path = Path(sys.argv[1])
theme = sys.argv[2]
value = json.dumps(theme, ensure_ascii=False)
line = f"theme = {value}"

try:
    # Follow an existing config symlink, then atomically replace its target.
    target = path.resolve()
    exists = target.exists()
    original = target.read_text() if exists else ""
    parsed = tomllib.loads(original)
except (OSError, UnicodeError, tomllib.TOMLDecodeError):
    raise SystemExit("rnmui: config is unreadable or invalid TOML; refusing update") from None

# Only edit the root table. Restrict matching to the text before the first
# table header; final TOML comparison below rejects false headers in strings.
header = re.search(r"(?m)^[ \t]*\[", original)
root_end = header.start() if header else len(original)
root = original[:root_end]
assignment = re.compile(r"(?m)^(?P<indent>[ \t]*)(?:theme|\"theme\"|'theme')[ \t]*=.*(?:\n|$)")
match = assignment.search(root)
if match:
    indent = match.group("indent")
    ending = "\n" if match.group(0).endswith("\n") else ""
    candidate = original[:match.start()] + indent + line + ending + original[match.end():]
else:
    insertion = header.start() if header else len(original)
    prefix, suffix = original[:insertion], original[insertion:]
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    candidate = prefix + line + "\n" + suffix

try:
    expected = dict(parsed)
    expected["theme"] = theme
    if tomllib.loads(candidate) != expected:
        raise ValueError
    encoded = candidate.encode("utf-8")
except (UnicodeError, tomllib.TOMLDecodeError, ValueError):
    raise SystemExit("rnmui: config cannot be safely updated; refusing update") from None

# Publish beside the target so replace is atomic on the same filesystem. A
# missing config is private by default; existing mode bits are retained.
mode = stat.S_IMODE(target.stat().st_mode) if exists else 0o600
fd = -1
temporary = None
try:
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.fchmod(fd, mode)
    with os.fdopen(fd, "wb") as staged:
        fd = -1
        staged.write(encoded)
        staged.flush()
        os.fsync(staged.fileno())
    os.replace(temporary, target)
    temporary = None
except OSError:
    raise SystemExit("rnmui: could not publish config; original left unchanged") from None
finally:
    if fd >= 0:
        os.close(fd)
    if temporary is not None:
        try:
            os.unlink(temporary)
        except OSError:
            pass
PY

#!/bin/bash
# herdr's config.toml also holds your keybindings, so only replace the [theme*]
# sections and leave everything else alone.
set -euo pipefail
conf="$HOME/.config/herdr/config.toml"
[[ -f "$conf" ]] || exit 0
tmp="$(mktemp)"
awk '
  /^\[/ { skip = ($0 ~ /^\[theme(\]|\.)/) }
  !skip { print }
' "$conf" | sed -e :a -e '/^\n*$/{$d;N;ba' -e '}' >"$tmp"
{ cat "$tmp"; echo; cat "$THEME_DIR/out/herdr-theme.toml"; } >"$conf"
rm -f "$tmp"
herdr server reload-config >/dev/null 2>&1 || true

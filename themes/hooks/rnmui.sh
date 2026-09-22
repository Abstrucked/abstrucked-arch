#!/bin/bash
# rnmui rewrites its own config when you press t, so set just the theme line.
set -euo pipefail
conf="$HOME/.config/rnmui/config.toml"
mkdir -p "$(dirname "$conf")"
if [[ -f "$conf" ]] && grep -q '^theme *=' "$conf"; then
  sed -i "s|^theme *=.*|theme = \"$THEME_RNMUI\"|" "$conf"
else
  echo "theme = \"$THEME_RNMUI\"" >>"$conf"
fi

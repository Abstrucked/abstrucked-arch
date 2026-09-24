#!/bin/bash
# Stage what the login screen needs next to the gtk.css themectl links there:
# the background color and a wallpaper per monitor class, as symlinks.
# themectl-greeter-sync (install/lightdm-greeter.sh) reads this directory as
# root when the greeter starts, so a theme switch shows at the next login.
set -euo pipefail
stage="$HOME/.local/state/themes/greeter"
mkdir -p "$stage"
printf '%s\n' "$THEME_BG" >"$stage/bg.new"
mv -f "$stage/bg.new" "$stage/bg"

picker="$THEME_DIR/../scripts/.local/bin/display-detect"
[[ -x "$picker" ]] || exit 0
for class in ultrawide wide internal; do
  wallpaper="$("$picker" pick "$class" 2>/dev/null || true)"
  if [[ -n "$wallpaper" ]]; then
    ln -sfn "$wallpaper" "$stage/$class"
  else
    rm -f "$stage/$class"
  fi
done

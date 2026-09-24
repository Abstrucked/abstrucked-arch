#!/bin/bash
# Switch LightDM to lightdm-gtk-greeter, themed by themectl.
#
#   install/lightdm-greeter.sh           install (asks for sudo)
#   install/lightdm-greeter.sh --revert  go back to the previous greeter
#
# themectl renders the login screen's CSS and stages wallpapers under
# ~/.local/state/themes/greeter. LightDM runs themectl-greeter-sync as root
# before each login screen to copy them where the greeter can read them, so a
# theme switch needs no sudo and shows at the next login. Run this again after
# changing install/lightdm/.
set -euo pipefail

declare -r HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
declare -r DOTFILES="$(dirname "$HERE")"
declare -r LIGHTDM_CONF=/etc/lightdm/lightdm.conf
declare -r SYNC=/usr/local/libexec/themectl-greeter-sync
declare -r SYNC_CONF=/etc/lightdm/themectl-greeter.conf
declare -r GREETER_DIR=/etc/xdg/lightdm/lightdm-gtk-greeter.conf.d
declare -r MARK="# dotfiles: themectl login screen (install/lightdm-greeter.sh)"

die() { echo "lightdm-greeter: $*" >&2; exit 1; }

[[ "$EUID" -ne 0 ]] || die "run as your regular user; it uses sudo where needed"
[[ -f "$LIGHTDM_CONF" ]] || die "$LIGHTDM_CONF not found; is LightDM installed?"

# The greeter-session in effect under [Seat:*], ignoring our own block.
current_greeter() {
  awk -v mark="$MARK" '
    /^\[/ { seat = ($0 == "[Seat:*]") }
    $0 == mark { skip = 2; next }
    skip > 0 { skip--; next }
    seat && /^greeter-session=/ { sub(/^greeter-session=/, ""); value = $0 }
    END { print value }
  ' "$LIGHTDM_CONF"
}

# Print lightdm.conf with our block removed and, under [Seat:*], every active
# greeter-session/greeter-setup-script line dropped; $1, if set, is inserted
# right after the [Seat:*] header.
rewrite_conf() {
  awk -v mark="$MARK" -v block="$1" '
    $0 == mark { skip = 2; next }
    skip > 0 { skip--; next }
    /^\[/ { seat = ($0 == "[Seat:*]") }
    seat && /^(greeter-session|greeter-setup-script)=/ { next }
    { print }
    $0 == "[Seat:*]" && block != "" { print block }
  ' "$LIGHTDM_CONF"
}

install_conf() {
  local tmp="$1"
  grep -qx '\[Seat:\*\]' "$tmp" || die "no [Seat:*] section in $LIGHTDM_CONF"
  sudo cp --backup=numbered -- "$LIGHTDM_CONF" "$LIGHTDM_CONF.dotfiles-bak"
  sudo install -m644 -- "$tmp" "$LIGHTDM_CONF"
}

install_greeter() {
  local previous tmp
  previous="$(current_greeter)"
  # On a re-run our own block hides the original; keep the one saved then.
  if [[ -z "$previous" || "$previous" == lightdm-gtk-greeter ]]; then
    previous="$(sed -n 's/^previous_greeter=//p' "$SYNC_CONF" 2>/dev/null || true)"
  fi

  sudo pacman -S --needed lightdm-gtk-greeter
  sudo install -Dm755 -- "$HERE/lightdm/themectl-greeter-sync" "$SYNC"
  sudo install -Dm644 -- "$HERE/lightdm/40-dotfiles.conf" "$GREETER_DIR/40-dotfiles.conf"
  printf 'user=%s\nstage=%s\nprevious_greeter=%s\n' \
    "$(id -un)" "$HOME/.local/state/themes/greeter" "$previous" |
    sudo install -m644 /dev/stdin "$SYNC_CONF"

  tmp="$(mktemp)"
  trap 'rm -f -- "$tmp"' EXIT
  rewrite_conf "$MARK"$'\n'"greeter-session=lightdm-gtk-greeter"$'\n'"greeter-setup-script=$SYNC" >"$tmp"
  install_conf "$tmp"

  # Stage the current theme and publish it now, so the next login is themed
  # even before LightDM first runs the sync itself.
  "$DOTFILES/themes/themectl" apply
  sudo "$SYNC"
  echo "Done. The login screen follows themectl from the next logout or reboot."
  echo "Undo with: $0 --revert"
}

revert_greeter() {
  local previous tmp
  previous="$(sed -n 's/^previous_greeter=//p' "$SYNC_CONF" 2>/dev/null || true)"
  [[ -n "$previous" ]] || previous=lightdm-slick-greeter
  [[ -e "/usr/share/xgreeters/$previous.desktop" ]] || die "previous greeter $previous is not installed"
  tmp="$(mktemp)"
  trap 'rm -f -- "$tmp"' EXIT
  rewrite_conf "greeter-session=$previous" >"$tmp"
  install_conf "$tmp"
  sudo rm -f -- "$SYNC" "$SYNC_CONF" "$GREETER_DIR/40-dotfiles.conf" "$GREETER_DIR/60-themectl.conf"
  sudo rm -rf -- /usr/share/themes/themectl-greeter /usr/share/backgrounds/themectl
  echo "Restored greeter-session=$previous. lightdm-gtk-greeter is still installed;"
  echo "remove it with: sudo pacman -Rs lightdm-gtk-greeter"
}

case "${1:-}" in
  "") install_greeter ;;
  --revert) revert_greeter ;;
  -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//' ;;
  *) die "unknown option '$1' (try --help)" ;;
esac

#!/bin/bash
# Enable battery save mode (low power, low temp)

set -euo pipefail

if ! command -v ryzenadj &>/dev/null; then
  echo "Error: ryzenadj is not installed" >&2
  echo "Install with: sudo pacman -S ryzenadj" >&2
  exit 1
fi

sudo ryzenadj --stapm-limit=10000 --fast-limit=12000 --slow-limit=10000 --tctl-temp=70

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/awesome"
state_file="$state_dir/power-mode"
mkdir -p "$state_dir"
state_file_tmp=$(mktemp "$state_dir/power-mode.XXXXXX")
trap 'rm -f "$state_file_tmp"' EXIT
printf '%s\n' 'battery-save' > "$state_file_tmp"
mv "$state_file_tmp" "$state_file"
trap - EXIT

echo "Battery-Save mode enabled"

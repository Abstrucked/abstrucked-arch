#!/bin/bash
# Enable performance mode (high power, high temp)

set -euo pipefail

if ! command -v ryzenadj &>/dev/null; then
  echo "Error: ryzenadj is not installed" >&2
  echo "Install with: sudo pacman -S ryzenadj" >&2
  exit 1
fi

sudo ryzenadj --stapm-limit=20000 --fast-limit=25000 --slow-limit=20000 --tctl-temp=85

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/awesome"
state_file="$state_dir/power-mode"
mkdir -p "$state_dir"
state_file_tmp=$(mktemp "$state_dir/power-mode.XXXXXX")
trap 'rm -f "$state_file_tmp"' EXIT
printf '%s\n' 'performance' > "$state_file_tmp"
mv "$state_file_tmp" "$state_file"
trap - EXIT

echo "Performance mode enabled"

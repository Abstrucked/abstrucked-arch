#!/bin/bash
# Enable battery save mode (low power, low temp)

if ! command -v ryzenadj &>/dev/null; then
  echo "Error: ryzenadj is not installed" >&2
  echo "Install with: sudo pacman -S ryzenadj" >&2
  exit 1
fi

sudo ryzenadj --stapm-limit=10000 --fast-limit=12000 --slow-limit=10000 --tctl-temp=70
echo "Battery-Save mode enabled"

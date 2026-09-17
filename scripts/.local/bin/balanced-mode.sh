#!/bin/bash
# Enable balanced mode (medium power, medium temp)

if ! command -v ryzenadj &>/dev/null; then
  echo "Error: ryzenadj is not installed" >&2
  echo "Install with: sudo pacman -S ryzenadj" >&2
  exit 1
fi

sudo ryzenadj --stapm-limit=15000 --fast-limit=20000 --slow-limit=15000 --tctl-temp=80
echo "Balanced mode enabled"

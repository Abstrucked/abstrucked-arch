#!/bin/bash
# Enable performance mode (high power, high temp)

if ! command -v ryzenadj &>/dev/null; then
  echo "Error: ryzenadj is not installed" >&2
  echo "Install with: sudo pacman -S ryzenadj" >&2
  exit 1
fi

sudo ryzenadj --stapm-limit=20000 --fast-limit=25000 --slow-limit=20000 --tctl-temp=85
echo "Performance mode enabled"

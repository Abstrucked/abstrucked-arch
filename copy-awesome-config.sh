#!/bin/bash

set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SRC="$HOME/.config/awesome"

DEST="$DOTFILES_DIR/awesome/.config/awesome"

# Share exact-destination backup, staging, and rollback behavior.
source "$DOTFILES_DIR/bootstrap-configs.sh"
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help) echo "Usage: $0 [--dry-run]"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if validate_paths "$SRC" "$DEST"; then :; else
  status=$?
  [[ "$status" -eq 2 ]] && exit 0
  exit "$status"
fi

if check_sensitive_content "$SRC"; then
  echo "Refusing to import potential sensitive content; review it and use bootstrap-configs.sh if an explicit override is needed." >&2
  exit 1
else
  status=$?
  [[ "$status" -eq 1 ]] || exit "$status"
fi

if copy_config "$SRC" "$DEST" awesome; then
  exit 0
else
  status=$?
  [[ "$status" -eq 2 ]] && exit 0
  exit "$status"
fi

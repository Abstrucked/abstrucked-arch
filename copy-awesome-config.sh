#!/bin/bash

set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SRC="$HOME/.config/awesome"

DEST="$DOTFILES_DIR/awesome/.config/awesome/awesome"

if [ ! -d "$SRC" ]; then
  echo "Source $SRC does not exist"
  exit 1
fi

if [ ! -d "$DEST" ]; then
  echo "Destination $DEST does not exist, creating"
  mkdir -p "$DEST"
fi

echo "Copying contents from $SRC to $DEST"

cp -rf "$SRC"/* "$DEST"

echo "✓ Awesome config copied"


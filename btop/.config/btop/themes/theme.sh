#!/bin/bash
# Global theme selector
# Sources the selected theme based on THEME environment variable

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME="${THEME:-catppuccin-mocha}"

THEME_FILE="$DOTFILES_DIR/themes/$THEME.sh"
if [[ -f "$THEME_FILE" ]]; then
  source "$THEME_FILE"
else
  echo "Warning: Theme '$THEME' not found at $THEME_FILE, falling back to catppuccin-mocha"
  source "$DOTFILES_DIR/themes/catppuccin-mocha.sh"
fi

# Map THEME to app-specific variables
case "$THEME" in
  catppuccin-mocha) THEME_FLAVOUR="mocha" ;;
  catppuccin-latte) THEME_FLAVOUR="latte" ;;
  catppuccin-frappe) THEME_FLAVOUR="frappe" ;;
  catppuccin-macchiato) THEME_FLAVOUR="macchiato" ;;
  *) THEME_FLAVOUR="mocha" ;;
esac
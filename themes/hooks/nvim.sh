#!/bin/bash
# Running Neovim instances pick the theme up via the state file the config
# reads at startup and on the FocusGained event.
set -euo pipefail
state="${XDG_STATE_HOME:-$HOME/.local/state}/themes"
mkdir -p "$state"
printf '%s\n%s\n' "$THEME_NVIM_COLORSCHEME" "$THEME_NVIM_FLAVOUR" >"$state/nvim"

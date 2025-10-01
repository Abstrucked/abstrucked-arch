#!/bin/bash
# Main installation script for dotfiles

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${BLUE}=== Dotfiles Installation Script ===${NC}"
echo -e "${YELLOW}Dotfiles directory: $DOTFILES_DIR${NC}"

# Check if running on Arch Linux
if ! command -v pacman &>/dev/null; then
  echo -e "${RED}Error: This script is designed for Arch Linux systems.${NC}"
  exit 1
fi

# Install yay if not present
if ! command -v yay &>/dev/null; then
  echo -e "${YELLOW}yay not found. Installing yay first...${NC}"
  if [[ -f "$DOTFILES_DIR/install-yay.sh" ]]; then
    bash "$DOTFILES_DIR/install-yay.sh"
  else
    echo -e "${RED}Error: install-yay.sh not found in $DOTFILES_DIR${NC}"
    exit 1
  fi
fi

# Install packages
echo -e "${YELLOW}Installing packages from packages.list...${NC}"
if [[ -f "$DOTFILES_DIR/packages.list" ]]; then
  # Install all packages with yay (handles both official and AUR)
  all_packages=$(grep -v '^#' "$DOTFILES_DIR/packages.list" || true)
  if [[ -n "$all_packages" ]]; then
    echo -e "${BLUE}Installing packages with yay...${NC}"
    echo "$all_packages" | xargs yay -S --needed --noconfirm
  fi
else
  echo -e "${RED}Error: packages.list not found in $DOTFILES_DIR${NC}"
  exit 1
fi

echo -e "${YELLOW}Removing system nodejs and npm to allow version manager usage...${NC}"
yay -Rsn npm nodejs

echo -e "${YELLOW}Initializing git submodules...${NC}"
git submodule update --init --recursive

# List of packages to stow (directories in dotfiles repo)
stow_packages=("awesome" "ssh" "alacritty" "btop" "nvim" "picom" "zsh" "pcmanfm" "scripts")

# Unstow existing packages to clean up symlinks
for package in "${stow_packages[@]}"; do
  if [[ -d "$DOTFILES_DIR/$package" ]]; then
    echo -e "${BLUE}Unstowing $package...${NC}"
    stow -d "$DOTFILES_DIR" -t "$HOME" -D "$package" 2>/dev/null || true
  fi
done

# Remove existing .config directories for packages about to be stowed
for package in "${stow_packages[@]}"; do
  if [[ -d "$DOTFILES_DIR/$package/.config" ]]; then
    config_dir="$HOME/.config/$package"
    if [[ -d "$config_dir" ]]; then
      echo -e "${YELLOW}Removing existing $config_dir...${NC}"
      rm -rf "$config_dir"
    fi
  fi
done

# Setup symlinks with GNU Stow
echo -e "${YELLOW}Setting up symlinks with GNU Stow...${NC}"

for package in "${stow_packages[@]}"; do
  if [[ -d "$DOTFILES_DIR/$package" ]]; then
    echo -e "${BLUE}Stowing $package...${NC}"
    stow -d "$DOTFILES_DIR" -t "$HOME" "$package"
  else
    echo -e "${YELLOW}Warning: $package directory not found, skipping...${NC}"
  fi
done

# Make scripts executable
echo -e "${YELLOW}Making scripts executable...${NC}"
if [[ -d "$HOME/scripts/.local/bin" ]]; then
  chmod +x "$HOME/scripts/.local/bin"/*
  echo -e "${GREEN}✓ Scripts made executable${NC}"
else
  echo -e "${YELLOW}Warning: Scripts directory not found, skipping chmod${NC}"
fi

# Setup theme
echo -e "${YELLOW}Setting up theme...${NC}"
if [[ -f "$DOTFILES_DIR/themes/theme.sh" ]]; then
  source "$DOTFILES_DIR/themes/theme.sh"
  echo -e "${BLUE}Generating Alacritty theme.toml...${NC}"
  cat >"$HOME/.config/alacritty/theme.toml" <<EOF
[colors.primary]
background = "$PRIMARY_BACKGROUND"
foreground = "$PRIMARY_FOREGROUND"
dim_foreground = "$PRIMARY_DIM_FOREGROUND"
bright_foreground = "$PRIMARY_BRIGHT_FOREGROUND"

[colors.cursor]
text = "$CURSOR_TEXT"
cursor = "$CURSOR_CURSOR"

[colors.vi_mode_cursor]
text = "$VI_MODE_CURSOR_TEXT"
cursor = "$VI_MODE_CURSOR_CURSOR"

[colors.search.matches]
foreground = "$SEARCH_MATCHES_FOREGROUND"
background = "$SEARCH_MATCHES_BACKGROUND"

[colors.search.focused_match]
foreground = "$SEARCH_FOCUSED_MATCH_FOREGROUND"
background = "$SEARCH_FOCUSED_MATCH_BACKGROUND"

[colors.footer_bar]
foreground = "$FOOTER_BAR_FOREGROUND"
background = "$FOOTER_BAR_BACKGROUND"

[colors.hints.start]
foreground = "$HINTS_START_FOREGROUND"
background = "$HINTS_START_BACKGROUND"

[colors.hints.end]
foreground = "$HINTS_END_FOREGROUND"
background = "$HINTS_END_BACKGROUND"

[colors.selection]
text = "$SELECTION_TEXT"
background = "$SELECTION_BACKGROUND"

[colors.normal]
black = "$NORMAL_BLACK"
red = "$NORMAL_RED"
green = "$NORMAL_GREEN"
yellow = "$NORMAL_YELLOW"
blue = "$NORMAL_BLUE"
magenta = "$NORMAL_MAGENTA"
cyan = "$NORMAL_CYAN"
white = "$NORMAL_WHITE"

[colors.bright]
black = "$BRIGHT_BLACK"
red = "$BRIGHT_RED"
green = "$BRIGHT_GREEN"
yellow = "$BRIGHT_YELLOW"
blue = "$BRIGHT_BLUE"
magenta = "$BRIGHT_MAGENTA"
cyan = "$BRIGHT_CYAN"
white = "$BRIGHT_WHITE"

[[colors.indexed_colors]]
index = 16
color = "$INDEXED_16"

[[colors.indexed_colors]]
index = 17
color = "$INDEXED_17"
EOF
  echo -e "${GREEN}✓ Theme setup complete${NC}"
else
  echo -e "${YELLOW}Warning: Theme setup script not found${NC}"
fi

# Setup backgrounds
echo -e "${YELLOW}Setting up backgrounds...${NC}"
if [[ -d "$DOTFILES_DIR/backgrounds" ]]; then
  ln -sf "$DOTFILES_DIR/backgrounds" "$HOME/.backgrounds"
  echo -e "${GREEN}✓ Backgrounds linked to ~/.backgrounds${NC}"
else
  echo -e "${YELLOW}Warning: Backgrounds directory not found${NC}"
fi

# Generate Tmux theme
echo -e "${BLUE}Generating Tmux theme configuration...${NC}"
mkdir -p "$HOME/.config/tmux"
ln -sf "$DOTFILES_DIR/config/tmux/tmux.conf" "$HOME/.config/tmux/tmux.conf"
cat >"$HOME/.config/tmux/theme.conf" <<EOF
# Tmux theme colors from $THEME
set -g status-bg black
set -g status-fg white
set -g status-left-bg black
set -g status-left-fg brightblue
set -g status-right-bg black
set -g status-right-fg brightblue

set -g pane-border-fg black
set -g pane-active-border-fg blue

set -g window-status-current-bg blue
set -g window-status-current-fg black
set -g window-status-bg black
set -g window-status-fg white

set -g message-bg brightyellow
set -g message-fg black
EOF
echo -e "${GREEN}✓ Tmux theme generated${NC}"

# Symlink tmux config
ln -sf "$HOME/.config/tmux/tmux.conf" "$HOME/.tmux.conf"
echo -e "${GREEN}✓ Tmux config symlinked${NC}"

# Handle ghossty if it exists
if [[ -d "$DOTFILES_DIR/ghossty" ]]; then
  echo -e "${BLUE}Stowing ghossty...${NC}"
  stow -d "$DOTFILES_DIR" -t "$HOME" "ghossty"
fi

echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo -e "${YELLOW}LazyVim has been installed and configured.${NC}"
echo -e "${YELLOW}Please restart your terminal or run 'source ~/.zshrc' to apply changes.${NC}"
echo -e "${YELLOW}You may need to log out and back in for some changes to take effect.${NC}"
echo -e "${YELLOW}Run 'nvim' to start using your new LazyVim setup!${NC}"


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
if ! command -v pacman &> /dev/null; then
    echo -e "${RED}Error: This script is designed for Arch Linux systems.${NC}"
    exit 1
fi

# Install yay if not present
if ! command -v yay &> /dev/null; then
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
    # Install official packages with pacman
    pacman_packages=$(grep -v '^#' "$DOTFILES_DIR/packages.list" | grep -v 'zsh-theme-powerlevel10k' || true)
    if [[ -n "$pacman_packages" ]]; then
        echo -e "${BLUE}Installing pacman packages...${NC}"
        echo "$pacman_packages" | xargs sudo pacman -S --needed --noconfirm
    fi

    # Install AUR packages with yay
    aur_packages=$(grep 'zsh-theme-powerlevel10k' "$DOTFILES_DIR/packages.list" || true)
    if [[ -n "$aur_packages" ]]; then
        echo -e "${BLUE}Installing AUR packages...${NC}"
        echo "$aur_packages" | xargs yay -S --noconfirm
    fi
else
    echo -e "${RED}Error: packages.list not found in $DOTFILES_DIR${NC}"
    exit 1
fi

# Setup symlinks with GNU Stow
echo -e "${YELLOW}Setting up symlinks with GNU Stow...${NC}"

# List of packages to stow (directories in dotfiles repo)
stow_packages=("tmux" "awesome" "ssh" "alacritty" "btop" "nvim" "picom" "zsh" "pcmanfm" "scripts")

for package in "${stow_packages[@]}"; do
    if [[ -d "$DOTFILES_DIR/$package" ]]; then
        echo -e "${BLUE}Stowing $package...${NC}"
        stow -d "$DOTFILES_DIR" -t "$HOME" "$package"
    else
        echo -e "${YELLOW}Warning: $package directory not found, skipping...${NC}"
    fi
done

# Handle ghossty if it exists
if [[ -d "$DOTFILES_DIR/ghossty" ]]; then
    echo -e "${BLUE}Stowing ghossty...${NC}"
    stow -d "$DOTFILES_DIR" -t "$HOME" "ghossty"
fi

# Install LazyVim by default
echo -e "${YELLOW}Installing LazyVim Neovim distribution...${NC}"
if [[ -f "$DOTFILES_DIR/install-lazyvim.sh" ]]; then
    bash "$DOTFILES_DIR/install-lazyvim.sh"
else
    echo -e "${RED}Warning: install-lazyvim.sh not found. Skipping LazyVim installation.${NC}"
fi

echo -e "${GREEN}=== Installation Complete! ===${NC}"
echo -e "${YELLOW}LazyVim has been installed and configured.${NC}"
echo -e "${YELLOW}Please restart your terminal or run 'source ~/.zshrc' to apply changes.${NC}"
echo -e "${YELLOW}You may need to log out and back in for some changes to take effect.${NC}"
echo -e "${YELLOW}Run 'nvim' to start using your new LazyVim setup!${NC}"
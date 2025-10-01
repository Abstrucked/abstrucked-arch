#!/bin/bash
# Install LazyVim Neovim distribution

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Installing LazyVim ===${NC}"

# Check if Neovim is installed
if ! command -v nvim &> /dev/null; then
    echo -e "${RED}Error: Neovim is not installed. Please run install.sh first.${NC}"
    exit 1
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is required but not installed.${NC}"
    exit 1
fi

# Create config directory
mkdir -p "$HOME/.config"

# Set config directory
NVIM_CONFIG_DIR="$HOME/.config/nvim"

# Clone LazyVim starter
echo -e "${YELLOW}Cloning LazyVim starter configuration...${NC}"
git clone https://github.com/LazyVim/starter "$NVIM_CONFIG_DIR"

# Remove .git directory to avoid confusion
rm -rf "$NVIM_CONFIG_DIR/.git"

# Install LazyVim
echo -e "${YELLOW}Installing LazyVim...${NC}"
cd "$NVIM_CONFIG_DIR"
if command -v nvim &> /dev/null; then
    # Run Neovim to install plugins (headless mode)
    nvim --headless "+Lazy! sync" +qa
else
    echo -e "${RED}Warning: Could not run Neovim to install plugins automatically.${NC}"
    echo -e "${YELLOW}Please run 'nvim' manually after installation to complete plugin setup.${NC}"
fi

echo -e "${GREEN}=== LazyVim installation complete! ===${NC}"
echo -e "${YELLOW}Your LazyVim configuration is ready at $NVIM_CONFIG_DIR${NC}"
echo -e "${YELLOW}Run 'nvim' to start using LazyVim${NC}"
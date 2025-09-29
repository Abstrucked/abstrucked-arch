#!/bin/bash
# Install yay AUR helper

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Installing yay AUR helper...${NC}"

# Check if yay is already installed
if command -v yay &> /dev/null; then
    echo -e "${GREEN}yay is already installed!${NC}"
    exit 0
fi

# Check if git is installed
if ! command -v git &> /dev/null; then
    echo -e "${RED}Error: git is required but not installed.${NC}"
    exit 1
fi

# Create temporary directory
temp_dir=$(mktemp -d)
cd "$temp_dir"

echo "Cloning yay from AUR..."
git clone https://aur.archlinux.org/yay.git

cd yay

echo "Building and installing yay..."
makepkg -si --noconfirm

# Clean up
cd /
rm -rf "$temp_dir"

echo -e "${GREEN}yay installed successfully!${NC}"
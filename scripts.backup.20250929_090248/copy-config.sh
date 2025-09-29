#!/bin/bash
# copy-config.sh - Manually copy configurations to dotfiles repo

set -euo pipefail

# Change to dotfiles directory
cd "$(dirname "$0")/.."

echo "Starting manual config copy..."

mkdir -p "nvim/.config"
cp -r "/home/abstrucked/.config/nvim" "nvim/.config/nvim"
echo "✓ Copied nvim"

mkdir -p "vlc/.config"
cp -r "/home/abstrucked/.config/vlc" "vlc/.config/vlc"
echo "✓ Copied vlc"

mkdir -p "awesome/.config"
cp -r "/home/abstrucked/.config/awesome" "awesome/.config/awesome"
echo "✓ Copied awesome"

mkdir -p "alacritty/.config"
cp -r "/home/abstrucked/.config/alacritty" "alacritty/.config/alacritty"
echo "✓ Copied alacritty"

mkdir -p "btop/.config"
cp -r "/home/abstrucked/.config/btop" "btop/.config/btop"
echo "✓ Copied btop"

mkdir -p "picom/.config"
cp -r "/home/abstrucked/.config/picom" "picom/.config/picom"
echo "✓ Copied picom"

mkdir -p "obs-studio/.config"
cp -r "/home/abstrucked/.config/obs-studio" "obs-studio/.config/obs-studio"
echo "✓ Copied obs-studio"

mkdir -p "pcmanfm/.config"
cp -r "/home/abstrucked/.config/pcmanfm" "pcmanfm/.config/pcmanfm"
echo "✓ Copied pcmanfm"

mkdir -p "zsh"
cp -r "/home/abstrucked/.p10k.zsh" "zsh/.p10k.zsh"
echo "✓ Copied .p10k.zsh"

mkdir -p "tmux"
cp -r "/home/abstrucked/.tmux.conf" "tmux/.tmux.conf"
echo "✓ Copied .tmux.conf"

mkdir -p "zsh"
cp -r "/home/abstrucked/.zshrc" "zsh/.zshrc"
echo "✓ Copied .zshrc"

mkdir -p "scripts"
cp -r "/home/abstrucked/load-api-keys.sh" "scripts/load-api-keys.sh"
echo "✓ Copied load-api-keys.sh"

mkdir -p "scripts/.local/bin"
cp -r "/home/abstrucked/.local/bin/tmux-sessionizer" "scripts/.local/bin/tmux-sessionizer"
echo "✓ Copied tmux-sessionizer"

mkdir -p "scripts/.local/bin"
cp -r "/home/abstrucked/.local/bin/screenshot" "scripts/.local/bin/screenshot"
echo "✓ Copied screenshot"

mkdir -p "scripts/.local/bin"
cp -r "/home/abstrucked/.local/bin/screenshot_1" "scripts/.local/bin/screenshot_1"
echo "✓ Copied screenshot_1"

mkdir -p "scripts/.local/bin"
cp -r "/home/abstrucked/.local/bin/screenshot_2" "scripts/.local/bin/screenshot_2"
echo "✓ Copied screenshot_2"

mkdir -p "scripts/.local/bin"
cp -r "/home/abstrucked/.local/bin/nvim-launcher" "scripts/.local/bin/nvim-launcher"
echo "✓ Copied nvim-launcher"

echo ""
echo "🎉 All configurations copied successfully!"
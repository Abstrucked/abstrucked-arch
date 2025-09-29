#!/bin/bash
# copy-config.sh - Manually copy configurations to dotfiles repo

set -euo pipefail

# Change to dotfiles directory
cd "$(dirname "$0")/.."

echo "Starting manual config copy..."

cp -r "/home/abstrucked/.config/nvim" "nvim/.config/nvim"
echo "✓ Copied nvim"

cp -r "/home/abstrucked/.config/vlc" "vlc/.config/vlc"
echo "✓ Copied vlc"

cp -r "/home/abstrucked/.config/awesome" "awesome/.config/awesome"
echo "✓ Copied awesome"

cp -r "/home/abstrucked/.config/alacritty" "alacritty/.config/alacritty"
echo "✓ Copied alacritty"

cp -r "/home/abstrucked/.config/btop" "btop/.config/btop"
echo "✓ Copied btop"

cp -r "/home/abstrucked/.config/picom" "picom/.config/picom"
echo "✓ Copied picom"

cp -r "/home/abstrucked/.config/obs-studio" "obs-studio/.config/obs-studio"
echo "✓ Copied obs-studio"

cp -r "/home/abstrucked/.config/pcmanfm" "pcmanfm/.config/pcmanfm"
echo "✓ Copied pcmanfm"

cp -r "/home/abstrucked/.p10k.zsh" "zsh/.p10k.zsh"
echo "✓ Copied .p10k.zsh"

cp -r "/home/abstrucked/.tmux.conf" "tmux/.tmux.conf"
echo "✓ Copied .tmux.conf"

cp -r "/home/abstrucked/.zshrc" "zsh/.zshrc"
echo "✓ Copied .zshrc"

cp -r "/home/abstrucked/load-api-keys.sh" "scripts/load-api-keys.sh"
echo "✓ Copied load-api-keys.sh"

cp -r "/home/abstrucked/.local/bin/tmux-sessionizer" "scripts/.local/bin/tmux-sessionizer"
echo "✓ Copied tmux-sessionizer"

cp -r "/home/abstrucked/.local/bin/screenshot" "scripts/.local/bin/screenshot"
echo "✓ Copied screenshot"

cp -r "/home/abstrucked/.local/bin/screenshot_1" "scripts/.local/bin/screenshot_1"
echo "✓ Copied screenshot_1"

cp -r "/home/abstrucked/.local/bin/screenshot_2" "scripts/.local/bin/screenshot_2"
echo "✓ Copied screenshot_2"

cp -r "/home/abstrucked/.local/bin/nvim-launcher" "scripts/.local/bin/nvim-launcher"
echo "✓ Copied nvim-launcher"

echo ""
echo "🎉 All configurations copied successfully!"
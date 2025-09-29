# Dotfiles

A comprehensive dotfiles setup for Arch Linux featuring AwesomeWM, LazyVim, and various productivity tools.

## 🚀 Quick Start

```bash
# Clone this repository
git clone <your-repo-url> ~/dotfiles
cd ~/dotfiles

# Run the installation script
./install.sh
```

The installation script will:
- Install yay (AUR helper) if not present
- Install all required packages
- Set up symlinks using GNU Stow
- Install and configure LazyVim

## 🔄 Bootstrap Your Existing Configs

If you already have configurations you want to import:

```bash
# Interactive mode (recommended) - reviews each config
./bootstrap-configs.sh

# Preview what would be copied
./bootstrap-configs.sh --dry-run

# Non-interactive mode (dangerous!)
./bootstrap-configs.sh --yes

# Force copy configs with sensitive files (dangerous!)
./bootstrap-configs.sh --force-sensitive
```

The bootstrap script will:
- Scan your `~/.config/` directory for known applications
- Check for dotfiles in your home directory (`.zshrc`, `.tmux.conf`, etc.)
- **Automatically skip configs containing sensitive files** (SSH keys, passwords, API tokens, etc.)
- Interactively copy safe configurations to the proper stow structure
- Create backups of existing dotfiles configs
- Provide security guidance for sensitive configurations

**Security First:** The script prioritizes security by automatically skipping any configuration containing sensitive files. Use `--force-sensitive` only if you understand the risks and have proper encryption in place.

## 🟢 Node.js Version Manager

Choose between two popular Node.js version managers:

```bash
./install-node-manager.sh
```

**Options:**
- **`n`** - Simple, fast, lightweight (recommended for most users)
- **`nvm`** - Feature-rich, supports `.nvmrc` auto-switching
- **`skip`** - Don't install any Node.js manager

**Comparison:**
- **n**: Faster, simpler, bash-only
- **nvm**: More features, works with any shell, supports `.nvmrc`

## 📦 Included Tools

### Core System
- **GNU Stow** - Symlink management
- **yay** - AUR package manager
- **git** - Version control

### Terminal & Shell
- **zsh** - Shell with Powerlevel10k theme
- **tmux** - Terminal multiplexer
- **alacritty** - GPU-accelerated terminal

### Window Manager & Desktop
- **AwesomeWM** - Tiling window manager
- **picom** - Compositor for transparency and effects
- **pcmanfm** - File manager

### Development Tools
- **Neovim** - Text editor with LazyVim distribution
- **ripgrep** - Fast text search tool
- **fd** - Simple, fast alternative to find
- **lazygit** - Simple terminal UI for git

### System Monitoring
- **btop** - Resource monitor

### Security
- **pass** - Password manager
- **gnupg** - GPG encryption tools

## 🏗️ Project Structure

```
dotfiles/
├── tmux/                    # Tmux configuration
├── awesome/                 # AwesomeWM configuration
│   └── .config/awesome/
│       ├── rc.lua
│       ├── themes/
│       ├── plugins/
│       └── backgrounds/
├── ssh/                     # SSH configuration
├── alacritty/               # Alacritty terminal config
├── btop/                    # System monitor config
├── nvim/                    # Neovim config (LazyVim ready)
├── picom/                   # Compositor config
├── zsh/                     # Zsh shell config
├── pcmanfm/                 # File manager config
├── scripts/                 # Custom bash scripts
│   └── .local/bin/
├── ghossty/                 # Ghossty configuration
├── packages.list            # Package list for installation
├── install.sh               # Main installation script
├── install-yay.sh           # Yay AUR helper installer
├── install-lazyvim.sh       # LazyVim installer
├── install-node-manager.sh  # Node.js version manager installer
└── README.md
```

## 🔧 Configuration Files

### AwesomeWM
- `awesome/.config/awesome/rc.lua` - Main configuration
- `awesome/.config/awesome/themes/` - Custom themes
- `awesome/.config/awesome/plugins/` - Custom plugins
- `awesome/.config/awesome/backgrounds/` - Wallpaper files

### Neovim (LazyVim)
- `nvim/.config/nvim/` - LazyVim configuration
- Automatically installed and configured by `install-lazyvim.sh`

### Zsh
- `zsh/.zshrc` - Zsh configuration
- `zsh/.p10k.zsh` - Powerlevel10k theme configuration

### Scripts
- `scripts/.local/bin/` - Custom executable scripts
- Add your scripts here and they'll be available in `~/.local/bin`

## 📋 Manual Installation

If you prefer to install manually:

1. **Install yay** (AUR helper):
   ```bash
   ./install-yay.sh
   ```

2. **Install packages**:
   ```bash
   yay -S --needed - < packages.list
   ```

3. **Set up symlinks**:
   ```bash
   stow -t ~ tmux awesome ssh alacritty btop nvim picom zsh pcmanfm scripts
   ```

4. **Install LazyVim**:
   ```bash
   ./install-lazyvim.sh
   ```

5. **Install Node.js version manager** (optional):
   ```bash
   ./install-node-manager.sh
   ```

## 🎨 Customization

### Adding New Configurations
1. Create a new directory: `mkdir newtool`
2. Add your config files with proper directory structure
3. Update `packages.list` if needed
4. Add the directory to the stow list in `install.sh`

### Custom Scripts
Add executable scripts to `scripts/.local/bin/` and they'll be available system-wide.

### Themes and Wallpapers
- AwesomeWM themes: `awesome/.config/awesome/themes/`
- Wallpapers: `awesome/.config/awesome/backgrounds/`

## 🔄 Updating

To update your dotfiles:

```bash
cd ~/dotfiles
git pull
./install.sh  # Re-run to update symlinks
```

## 🐛 Troubleshooting

### Common Issues

1. **Permission denied**: Make sure scripts are executable:
   ```bash
   chmod +x install.sh install-yay.sh install-lazyvim.sh
   ```

2. **Stow conflicts**: If you have existing config files:
   ```bash
   # Backup existing configs first
   mkdir ~/config_backup
   mv ~/.config/some_config ~/config_backup/
   ```

3. **LazyVim issues**: If LazyVim doesn't install properly:
   ```bash
   rm -rf ~/.config/nvim
   ./install-lazyvim.sh
   ```

### Getting Help

- Check the [AwesomeWM documentation](https://awesomewm.org/doc/)
- Visit [LazyVim](https://www.lazyvim.org/) for Neovim help
- Review [GNU Stow documentation](https://www.gnu.org/software/stow/)

## 📄 License

This dotfiles setup is provided as-is. Feel free to modify and distribute according to your needs.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

---

**Happy hacking!** 🎉
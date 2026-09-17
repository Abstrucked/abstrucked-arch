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

Run the installer as a regular user on Arch Linux, with `git` and `curl` installed. Building yay also requires `base-devel` (`sudo pacman -S --needed base-devel git`).

With the default components selected, the installation script will:
- Install yay (AUR helper) if not present
- Install all required packages
- Prompt you to select a default shell (zsh or bash)
- Set up symlinks using GNU Stow
- Configure terminal defaults for the selected shell
- Install and configure LazyVim

### Installer Flags

These flags belong to `install.sh`; standalone helpers support only their own options.

| Flag | Behavior |
|------|----------|
| `--dry-run` | Preview actions without making changes; prerequisite and selection validation still applies. |
| `--non-interactive`, `-y` | Use default selections without prompting; shell selection defaults to zsh and Node manager installation is skipped. |
| `--only STEP` | Restrict selection to a step; repeat the flag for each additional step. |
| `--skip STEP` | Exclude a step; repeat the flag for each additional exclusion. |
| `--verbose`, `-v` | Enable debug output. |
| `--quiet`, `-q` | Suppress non-error logging. |
| `--help`, `-h` | Show usage. |

Supported steps: `yay`, `packages`, `node`, `yubikey`, `stow`, `shell`, `theme`, `backgrounds`, `tmux`, and `lazyvim`. Unknown steps and a step listed in both `--only` and `--skip` are rejected. Filters also apply to interactive selections.

```bash
# Preview selected components without prompts
./install.sh --dry-run -y --only yay --only packages --only stow

# Skip multiple components
./install.sh --skip node --skip yubikey
```

Dependencies are validated before installation, not automatically added: `packages` and `yubikey` require yay already installed or the `yay` step selected; `stow` requires GNU Stow already installed or `packages` selected; `shell` requires the `stow` step selected. Package list entries are validated, and package installation failures stop the installer.

### Helpers and Safety

`install-yay.sh`, `install-node-manager.sh`, and `install-lazyvim.sh` support `--dry-run`, `--non-interactive` (or `-y`), and `--help` (or `-h`). The Node helper additionally supports `--manager n|nvm|skip`. `bootstrap-configs.sh` and `copy-awesome-config.sh` also support `--dry-run`.

```bash
./install-yay.sh --dry-run
./install-node-manager.sh --dry-run --manager nvm
./install-lazyvim.sh --dry-run
./copy-awesome-config.sh --dry-run
```

Dry runs do not install packages, download installers, copy configurations, create backups, or sync plugins. They are previews, not proof that a real installation will succeed. Unattended yay installation requires usable cached sudo credentials (`sudo -v` beforehand).

Backups use unique directories so repeated operations do not overwrite earlier backups. Shared installer backups live under `~/.dotfiles-backups/backup.*`; bootstrap and LazyVim replacements use unique backups beside the destination. Stow conflicts stop installation for manual reconciliation without deleting unrelated configurations. Earlier successful steps are not automatically rolled back.

Run the isolated regression suite with `python3 -B -m unittest discover -s tests -v`. It uses temporary homes and copied scripts with mocked install commands, not your real home or package manager.

## 🐚 Shell Selection

During installation, you'll be prompted to choose your default shell:

| Shell | Prompt | Features |
|-------|--------|----------|
| **zsh** | Powerlevel10k | zsh-autocomplete, instant prompt, git status in prompt |
| **bash** | Starship | Cross-shell prompt, bash-completion, minimal config |

### Switching Shells

You can switch shells at any time by re-running the installer:

```bash
./install.sh --only stow --only shell
```

Select both "stow" and "shell", then choose your shell (GNU Stow must already be installed for this command). The installer stows the selected shell configuration and updates existing Alacritty and tmux shell settings through their resolved targets, preserving symlinks. It does not unstow the old shell or change your account's login shell. Stow also processes the base configuration packages, not just the shell.

### Customizing Starship (Bash)

Starship works out of the box. To customize:

```bash
# Use a preset theme
starship preset catppuccin-mocha -o ~/.config/starship.toml

# Or edit the config directly
$EDITOR ~/.config/starship.toml
```

See [Starship documentation](https://starship.rs/) for all options.

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
- Skip configs flagged by best-effort checks for sensitive filenames and common credential patterns
- Interactively copy approved configurations to the proper stow structure
- Create backups of existing dotfiles configs
- Provide security guidance for sensitive configurations

**Review before committing:** The scanner is best effort, not a guarantee that copied files are free of secrets. Review all imported files and the staged diff before committing, including backups created inside the repository. `--yes` skips copy prompts, not sensitive-content checks. `--force-sensitive` overrides detected-content warnings, but does not override scan errors; use it only after reviewing the contents yourself.

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
- **n**: Simple executable manager; usable from Bash or Zsh
- **nvm**: Shell-based manager for compatible shells including Bash and Zsh; supports `.nvmrc`

`./install.sh -y` skips Node manager installation because it does not choose a manager. For unattended installation, explicitly select a manager with the standalone helper:

```bash
./install-node-manager.sh --non-interactive --manager n
# Or:
./install-node-manager.sh --non-interactive --manager nvm
```

Without `--manager`, the helper skips in non-interactive mode, dry-run mode, or when standard input is not a terminal. It installs/verifies the manager only, not a Node.js version, and prints shell setup instructions without sourcing or rewriting your shell profiles.

## 📦 Included Tools

### Core System
- **GNU Stow** - Symlink management
- **yay** - AUR package manager
- **git** - Version control

### Terminal & Shell
- **zsh** - Shell with Powerlevel10k theme (optional)
- **bash** - Shell with Starship prompt (optional)
- **starship** - Cross-shell prompt (used with bash)
- **bash-completion** - Tab completion for bash
- **tmux** - Terminal multiplexer
- **alacritty** - GPU-accelerated terminal
- **ghostty** - Modern terminal emulator with dynamic theming

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

### Utilities
- **create-app-launcher** - Interactive script to generate app launchers and aliases
- **pass-insert-utility** - Helper for inserting passwords into apps
- **nvim-launcher** - Pre-configured Neovim launcher with API key loading

## 🚀 App Launchers

Generate custom app launchers that automatically load API keys and run programs. Launchers are created in `~/.local/bin/` with corresponding aliases in `zsh/aliases.zsh`.

### Creating a Launcher
Run the interactive script:
```bash
create-app-launcher
```
- Enter the program name (e.g., `code` for VS Code).
- Enter a category (e.g., `ai` for AI tools).
- The script generates:
  - A launcher script (e.g., `code-launcher`) that sources `~/load-api-keys.sh` and runs the program.
  - An alias (e.g., `code-ai`) in `zsh/aliases.zsh`.

### Using Launchers
- After creation, reload your shell: `source ~/.zshrc`
- Use the alias: `code-ai` (loads API keys and launches the app).
- Existing launchers: `nvim-launcher` (for Neovim with API keys).

### Managing Launchers
- Edit `zsh/aliases.zsh` to modify or remove aliases.
- Delete launcher scripts from `~/.local/bin/` as needed.
- For security, ensure `~/load-api-keys.sh` is properly configured (see below).

## 🏷️ Aliases Management

Aliases are centralized in the shell-specific aliases file for easy management and organization.

### Adding Aliases
- Edit the aliases file directly:
  - **zsh**: `zsh/.config/zsh/aliases.zsh`
  - **bash**: `bash/.config/bash/aliases.sh`
- Use `create-app-launcher` to auto-generate aliases for apps.
- Reload after changes:
  - **zsh**: `source ~/.zshrc`
  - **bash**: `source ~/.bashrc`

### Current Aliases
- App-specific aliases (generated by `create-app-launcher`).
- Custom aliases (add your own in the aliases file).

### Best Practices
- Keep aliases simple and descriptive.
- Avoid conflicts with existing commands.
- Use categories for app aliases (e.g., `program-category`).

## 🔐 Password Manager (pass)

Use `pass` for secure password storage with GPG encryption. The `pass-insert-utility` helps insert passwords into applications.

### Initial Setup
1. Initialize pass store:
   ```bash
   pass init <your-gpg-key-id>
   ```
2. Add passwords:
   ```bash
   pass insert service/name
   ```

### Using pass-insert-utility
This script inserts passwords into apps or clipboards securely.

```bash
pass-insert-utility
```
- Select a password entry.
- Choose to copy to clipboard or insert into an active app (e.g., via xdotool).

### Integration with Launchers
- Launchers source `~/load-api-keys.sh`, which can load pass-stored API keys.
- Example: In `load-api-keys.sh`, add `export API_KEY=$(pass show api/key)`.

### Tips
- Use `pass git` for version-controlled password stores.
- Backup your `~/.password-store/` directory.
- For apps, prefer environment variables over hardcoded keys.

## 🏗️ Project Structure

```
dotfiles/
├── themes/                  # Global theme system
│   ├── theme.sh             # Theme selector and mappings
│   ├── catppuccin-mocha.sh  # Mocha color definitions
│   ├── catppuccin-latte.sh  # Latte color definitions
│   ├── catppuccin-frappe.sh # Frappe color definitions
│   └── catppuccin-macchiato.sh # Macchiato color definitions
│   └── [future-theme].sh    # Add new theme files here
├── backgrounds/             # Wallpaper collection
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
├── zsh/                     # Zsh shell config (Powerlevel10k)
│   ├── .zshrc               # Main Zsh config (sources aliases.zsh)
│   ├── .config/zsh/
│   │   ├── .zshrc           # Zsh configuration
│   │   ├── aliases.zsh      # Centralized aliases
│   │   └── zsh-autocomplete/ # zsh-autocomplete plugin
│   └── aliases.zsh          # Centralized aliases
├── bash/                    # Bash shell config (Starship)
│   ├── .bashrc              # Main Bash config entry point
│   └── .config/bash/
│       ├── bashrc           # Bash configuration
│       └── aliases.sh       # Centralized aliases
├── pcmanfm/                 # File manager config
├── scripts/                 # Custom bash scripts
│   └── .local/bin/
│       ├── create-app-launcher  # Launcher generator
│       ├── nvim-launcher        # Neovim launcher
│       └── pass-insert-utility  # Pass helper
├── ghossty/                 # Ghostty configuration
│   └── .config/ghostty/
│       └── config.sh            # Dynamic config script
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
- `install-lazyvim.sh` preserves existing repository-managed configuration and runs `nvim --headless '+Lazy! sync' +qa` to synchronize plugins.
- Unknown existing configurations are kept without modification in non-interactive mode (including non-terminal input) and dry runs. Existing configuration symlinks are never replaced.
- An interactive replacement of an unmanaged directory requires explicit confirmation. The helper stages the starter first, makes a unique backup, and attempts to restore the previous configuration if installation or synchronization fails.
- With no existing configuration, the helper installs the LazyVim starter. Real installation/synchronization requires Neovim and git; `XDG_CONFIG_HOME` and `NVIM_APPNAME` select the configuration location.

### Zsh (Powerlevel10k)
- `zsh/.zshrc` - Zsh configuration
- `zsh/.p10k.zsh` - Powerlevel10k theme configuration (not in repo, created by `p10k configure`)
- `zsh/.config/zsh/aliases.zsh` - Centralized aliases (sourced by `.zshrc`)

### Bash (Starship)
- `bash/.bashrc` - Bash configuration entry point
- `bash/.config/bash/bashrc` - Main Bash config (starship, keybindings, history)
- `bash/.config/bash/aliases.sh` - Centralized aliases (sourced by bashrc)

### Scripts
- `scripts/.local/bin/` - Custom executable scripts
- Add your scripts here and they'll be available in `~/.local/bin`

### Ghostty
- `ghossty/.config/ghostty/config.sh` - Dynamic config script (generates theme from `themes/theme.sh`)

## 📋 Manual Installation

If you prefer to install manually:

1. **Install yay** (AUR helper):
   ```bash
   ./install-yay.sh
   ```

2. **Install packages**:
   ```bash
    ./install.sh -y --only packages
   ```

3. **Set up symlinks** (choose your shell):
    ```bash
    # For zsh:
     stow -t ~ awesome ssh alacritty btop nvim picom zsh pcmanfm scripts ghossty gnupg

    # For bash:
     stow -t ~ awesome ssh alacritty btop nvim picom bash pcmanfm scripts ghossty gnupg

     # Tmux uses config/tmux rather than a Stow package:
     ./install.sh -y --only tmux
    ```

4. **Configure terminal shell**: Back up and edit the resolved targets of `~/.config/alacritty/alacritty.toml` and `~/.config/tmux/tmux.conf` (use `readlink -f` to locate them). Set the Alacritty shell and tmux `default-shell` to your chosen shell. Do not replace the Stow symlinks with regular files. Alternatively, use `./install.sh --only stow --only shell` to apply the installer's backed-up, symlink-preserving updates.

5. **Install LazyVim**:
   ```bash
   ./install-lazyvim.sh
   ```

6. **Install Node.js version manager** (optional):
    ```bash
    ./install-node-manager.sh
    ```

7. **Set up app launchers and aliases** (optional):
    ```bash
    create-app-launcher  # Generate as needed
    source ~/.zshrc      # For zsh
    # OR
    source ~/.bashrc     # For bash
    ```

7. **Configure pass** (optional):
    ```bash
    pass init <gpg-key>
    # Add passwords and use pass-insert-utility
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
- **Global Theme System**: Centralized theming for Alacritty, Neovim, Tmux, and AwesomeWM backgrounds
- AwesomeWM themes: `awesome/.config/awesome/themes/`
- Wallpapers: `backgrounds/` (linked to `~/.backgrounds`)

#### Switching Themes
The dotfiles include support for Catppuccin themes (Mocha, Latte, Frappe, Macchiato) and are extensible for others (e.g., Tokyo Night). Themes are abstracted via `themes/theme.sh` for dynamic app integration.

1. Set the `THEME` environment variable (edit your shell config or export in shell):
    ```bash
    export THEME=catppuccin-latte  # Options: catppuccin-mocha, catppuccin-latte, catppuccin-frappe, catppuccin-macchiato, tokyo-night, [add more]
    ```

2. Re-run the installation script:
    ```bash
    ./install.sh
    ```

3. Restart your applications or reload your shell:
    ```bash
    # For zsh:
    source ~/.zshrc
    # For bash:
    source ~/.bashrc

    tmux source ~/.tmux.conf
    # For Ghostty: Restart or use the launcher (theme updates dynamically)
    ```

This will automatically update:
- Alacritty colors (via generated `theme.toml`)
- Neovim Catppuccin plugin flavor
- Tmux status bar colors
- AwesomeWM background directory
- Ghostty theme (via `config.sh` sourcing `theme.sh`)

#### Adding New Themes
1. Create a theme file: `touch themes/[theme-name].sh` (add color vars if needed).
2. Update `themes/theme.sh` case statement to map `THEME=[theme-name]` to app-specific vars (e.g., `GHOSTTY_THEME="[Theme Name]"`).
3. Example for Tokyo Night:
   - Add `tokyo-night) ;;` to the flavour case.
   - Add `tokyo-night) GHOSTTY_THEME="Tokyo Night" ;;` to the GHOSTTY_THEME case.
   - Set `THEME=tokyo-night` and reload.
4. For non-Catppuccin themes, ensure apps support the theme name (e.g., Ghostty built-ins).

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
    chmod +x install.sh install-yay.sh install-lazyvim.sh scripts/.local/bin/create-app-launcher scripts/.local/bin/pass-insert-utility
    ```

2. **Stow conflicts**: The installer stops at the conflicting package. Inspect the paths Stow reports, back up any files you choose to move, and reconcile only those conflicts before rerunning. Do not delete whole configuration directories or unrelated symlinks to force installation.

3. **LazyVim issues**: Preview the helper's decision, then rerun interactively if appropriate:
     ```bash
     ./install-lazyvim.sh --dry-run
     ./install-lazyvim.sh
     ```
   Managed configurations are preserved while plugins sync. Unknown configurations are kept unless you explicitly approve an interactive directory replacement; do not delete `~/.config/nvim` as a troubleshooting step. Inspect Neovim's error output and any reported backup location if synchronization fails.

4. **Launcher or alias issues**: If aliases don't load:
    ```bash
    # For zsh:
    source ~/.zshrc
    # For bash:
    source ~/.bashrc
    # Check the aliases file for syntax errors:
    # zsh: zsh/aliases.zsh
    # bash: bash/aliases.sh
    ```

5. **Pass issues**: If passwords don't insert:
    ```bash
    gpg --list-keys  # Ensure GPG key exists
    pass  # Test basic functionality
    ```

6. **Theme not applying**: For Ghostty, ensure `config.sh` is executable and sourced correctly. Check `THEME` var and `themes/theme.sh` mappings.

### Getting Help

- Check the [AwesomeWM documentation](https://awesomewm.org/doc/)
- Visit [LazyVim](https://www.lazyvim.org/) for Neovim help
- Review [GNU Stow documentation](https://www.gnu.org/software/stow/)
- See [pass documentation](https://www.passwordstore.org/) for password management
- Check [Ghostty docs](https://ghostty.org/) for terminal theming

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

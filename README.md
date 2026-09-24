# Dotfiles

A comprehensive dotfiles setup for Arch Linux featuring AwesomeWM, Hyprland, LazyVim, and various productivity tools.

## 🚀 Quick Start

On a fresh Arch installation, log in as a regular user with sudo access and an
internet connection. Install curl if needed (`sudo pacman -Syu --needed curl`),
then run:

```bash
curl -fsSL https://raw.githubusercontent.com/Abstrucked/abstrucked-arch/main/install/bootstrap.sh | bash
```

This command becomes available after `install/bootstrap.sh` is merged into `main`.
The bootstrap updates the system and installs `base-devel`, `git`, and `curl`,
clones `main` into `~/.dotfiles`, and starts the interactive installer. It reconnects
standard input to your terminal so the installer menus work when launched through
a pipe. An existing `~/.dotfiles` path is left untouched and stops the bootstrap;
use the existing checkout's `./install.sh` to rerun installation.

To use `curl -fsSL https://abstrucked.com/dotfiles/install | bash`, configure that
HTTPS route on your website to redirect to the raw GitHub URL above, or serve
`install/bootstrap.sh` directly as `text/plain`. This repository does not configure
the domain or deploy that route. Cloning provides a Git checkout for future updates;
no archive extraction is needed.

Alternatively, clone and run the installer yourself:

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
- Use AwesomeWM by default, or select AwesomeWM + Hyprland / Hyprland only
- Prompt you to select a default shell (zsh or bash)
- Set up symlinks using GNU Stow
- Configure terminal defaults for the selected shell
- Set your account's login shell with `chsh`
- Install and configure LazyVim

### Installer Flags

These flags belong to `install.sh`; standalone helpers support only their own options.

| Flag | Behavior |
|------|----------|
| `--dry-run` | Preview actions without making changes; prerequisite and selection validation still applies. |
| `--non-interactive`, `-y` | Use default selections without prompting; shell selection defaults to zsh and Node manager installation is skipped. |
| `--only STEP` | Restrict selection to a step; repeat the flag for each additional step. |
| `--skip STEP` | Exclude a step; repeat the flag for each additional exclusion. |
| `--window-manager MODE`, `--wm MODE` | Select `awesome` (default), `both`, or `hyprland`. |
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

### Interactive UI and Window Managers

Normal terminal runs use [Gum](https://github.com/charmbracelet/gum) for keyboard-driven component, window-manager, shell, and confirmation menus. If Gum is missing, the installer offers to install it with `sudo pacman -S --needed gum`; declining or failing falls back to the plain-text menus. Gum is never installed during `--non-interactive`, redirected-input, or `--dry-run` runs.

The window-manager choice is shown only when `packages` or `stow` is selected. The default is AwesomeWM. Use an explicit mode for automation or repeatable installs:

```bash
./install.sh -y --wm awesome
./install.sh -y --wm both
./install.sh -y --wm hyprland
```

Shared packages are in `packages.list`; WM-specific packages are in `packages-awesome.list` and `packages-hyprland.list`. Stow follows the same choice, so a Hyprland-only install does not stow the AwesomeWM or Picom packages.

### Helpers and Safety

`install-yay.sh`, `install-node-manager.sh`, and `install-lazyvim.sh` support `--dry-run`, `--non-interactive` (or `-y`), and `--help` (or `-h`). The Node helper additionally supports `--manager n|nvm|skip`. `bootstrap-configs.sh` and `copy-awesome-config.sh` also support `--dry-run`.

```bash
./install-yay.sh --dry-run
./install-node-manager.sh --dry-run --manager nvm
./install-lazyvim.sh --dry-run
./copy-awesome-config.sh --dry-run
```

Dry runs do not install packages, download installers, copy configurations, create backups, or sync plugins. They are previews, not proof that a real installation will succeed. Unattended yay installation requires usable cached sudo credentials (`sudo -v` beforehand).

Backups use unique directories so repeated operations do not overwrite earlier backups. Shared installer, bootstrap, and LazyVim backups live outside the repository under `~/.dotfiles-backups/`. Stow conflicts stop installation for manual reconciliation without deleting unrelated configurations. Earlier successful steps are not automatically rolled back.

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

Select both "stow" and "shell", then choose your shell (GNU Stow must already be installed for this command). The installer stows the selected shell configuration and updates existing Alacritty and tmux shell settings through their resolved targets, preserving symlinks. It then sets your account's login shell with `sudo chsh`, skipping that when the shell is already current. It does not unstow the old shell. Stow also processes the base configuration packages, not just the shell.

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

**Review before committing:** The scanner is best effort, not a guarantee that copied files are free of secrets. Review all imported files and the staged diff before committing, including external backups under `~/.dotfiles-backups/`. `--yes` skips copy prompts, not sensitive-content checks. `--force-sensitive` overrides detected-content warnings, but does not override scan errors; use it only after reviewing the contents yourself.

Bootstrap copies configurations but deliberately leaves the original files in place. Before running Stow, compare the imported files, back up the originals, and remove or rename only the originals that Stow reports as conflicts. The installer will not adopt or delete those files automatically.

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
├── hyprland/                # Hyprland/Wayland configuration
│   ├── .config/hypr/        # Lua config for 0.55+ and legacy fallback
│   ├── .config/waybar/      # Status bar
│   ├── .config/swaync/      # Notifications and control center
│   └── .local/bin/          # Session and workflow helpers
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
│       └── config              # Ghostty configuration
├── packages.list            # Shared package list
├── packages-awesome.list    # AwesomeWM/X11 package list
├── packages-hyprland.list   # Hyprland/Wayland package list
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

### Hyprland and Wayland
- `hyprland/.config/hypr/hyprland.lua` - Hyprland 0.55+ entry point
- `hyprland/.config/hypr/lua/` - Modular Lua settings and bindings
- `hyprland/.config/hypr/hyprland.conf` - Legacy fallback for Hyprland 0.54 and earlier
- `hyprland/.config/waybar/` - Status bar configuration
- `hyprland/.config/swaync/` - Notification center configuration
- `hyprland/.local/bin/` - Launchers, layout, monitor, wallpaper, and session helpers

AwesomeWM remains the X11 session and Hyprland is the Wayland session. LightDM
discovers both session desktop files after the corresponding packages are
installed. `install/lightdm-greeter.sh` themes the login screen from the active
themectl palette (see `themes/README.md`). The Hyprland setup keeps the existing Awesome keybindings where
possible; dynamic Awesome tags are represented with fixed workspaces and named
special workspaces.

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
- `ghossty/.config/ghostty/config` - Ghostty configuration

## 📋 Manual Installation

If you prefer to install manually:

1. **Install yay** (AUR helper):
   ```bash
   ./install-yay.sh
   ```

2. **Install packages**:
   ```bash
   ./install.sh -y --only packages --wm awesome
   ```

3. **Set up symlinks** (choose a window manager and shell):
   ```bash
   # The installer handles conditional WM Stow packages:
   ./install.sh -y --only stow --wm awesome
   ./install.sh -y --only stow --wm both
   ./install.sh -y --only stow --wm hyprland

   # Tmux uses config/tmux rather than a Stow package:
   ./install.sh -y --only tmux
   ```

4. **Configure terminal shell**: Back up and edit the resolved targets of `~/.config/alacritty/alacritty.toml` and `~/.config/tmux/tmux.conf` (use `readlink -f` to locate them). Set the Alacritty shell and tmux `default-shell` to your chosen shell. Do not replace the Stow symlinks with regular files. Alternatively, use `./install.sh --only stow --only shell` to apply the installer's backed-up, symlink-preserving updates and set the login shell.

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

8. **Configure pass** (optional):
    ```bash
    pass init <gpg-key>
    # Add passwords and use pass-insert-utility
    ```

## 🎨 Customization

### Adding New Configurations
1. Create a new directory: `mkdir newtool`
2. Add your config files with proper directory structure
3. Update the appropriate package manifest (`packages.list`, `packages-awesome.list`, or `packages-hyprland.list`) if needed
4. Add the directory to the shared or window-manager-specific Stow list in `install.sh`

### Custom Scripts
Add executable scripts to `scripts/.local/bin/` and they'll be available system-wide.

### Themes and Wallpapers
- **Theme files**: Shared Alacritty color definitions and AwesomeWM themes
- Alacritty theme selector: `btop/.config/btop/themes/theme.sh`
- AwesomeWM themes: `awesome/.config/awesome/themes/`
- Hyprland configuration: `hyprland/.config/hypr/`
- Wallpapers: `backgrounds/` (linked to `~/.backgrounds`)
- Monitors: `display-detect` lays out whatever is connected (ultrawide
  first, 16:9 to its right, a laptop panel alone or below) and picks each
  output's wallpaper from `backgrounds/sets/`, under both Awesome and
  Hyprland, so the desktop and laptop share one config. Plugging or
  unplugging a monitor re-applies it (Hyprland's monitor events; under
  Awesome, `display-detect watch` following udev), and `Super+P` does it by
  hand. See `backgrounds/sets/README.md`.

#### Switching Themes
The dotfiles include support for Catppuccin themes (Mocha, Latte, Frappe, Macchiato). The Alacritty installer uses `btop/.config/btop/themes/theme.sh` and the selected `THEME` value to generate `~/.config/alacritty/theme.toml`.

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
     # For Ghostty: Restart the application after changing its static config
    ```

This updates:
- Alacritty colors (via generated `theme.toml`)
- Tmux status bar colors when the tmux component is selected

#### Adding New Themes
1. Create a theme file under `btop/.config/btop/themes/`, following the existing `catppuccin-*.sh` variable definitions.
2. Update `btop/.config/btop/themes/theme.sh` if the new theme needs selector mapping.
3. Set `THEME=tokyo-night` and rerun `./install.sh --only theme` after adding the required color variables.

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

6. **Theme not applying**: Check `THEME` and the selector at `btop/.config/btop/themes/theme.sh`, then rerun `./install.sh --only theme`.

### Getting Help

- Check the [AwesomeWM documentation](https://awesomewm.org/doc/)
- Check the [Hyprland documentation](https://wiki.hypr.land/)
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

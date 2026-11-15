# Dotfiles

A comprehensive dotfiles setup for Arch Linux featuring AwesomeWM, Hyprland, LazyVim, and various productivity tools.

## 🚀 Quick Start

On a fresh Arch installation, log in as a regular user with sudo access and an
internet connection. Install curl if needed (`sudo pacman -Syu --needed curl`),
then run:

```bash
curl -fsSL https://raw.githubusercontent.com/Abstrucked/abstrucked-arch/main/install/bootstrap.sh | bash
```

The bootstrap updates the system and installs `base-devel`, `git`, and `curl`,
clones `main` into `~/.dotfiles`, and starts the interactive installer. It reconnects
standard input to your terminal so the installer menus work when launched through
a pipe. An existing `~/.dotfiles` path is left untouched and stops the bootstrap;
use the existing checkout's `./install.sh` to rerun installation.
The clone is a blobless partial clone: history is complete, but old file versions
are downloaded on demand, so commands like `git log -p` or `git blame` on old
revisions need network access.

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

Run `./install.sh --help` for the available steps and descriptions, generated from `lib/component-registry.sh`. Unknown steps and a step listed in both `--only` and `--skip` are rejected. Filters also apply to interactive selections. Selected steps run in the registry's execution order, not the order of your `--only` arguments.

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

Backups use unique temporary directories so repeated operations do not overwrite earlier backups. Shared installer and bootstrap backups use `${DOTFILES_BACKUP_ROOT:-$HOME/.dotfiles-backups}`. The root must be absolute and outside the checkout, including symlinked paths; a directory backup cannot store its backup inside itself. Validation also applies to dry runs. LazyVim uses a separate external temporary backup directory. A failed LazyVim replacement attempts to restore the previous configuration; if recovery fails, the helper reports the retained backup or quarantine path. Stow conflicts stop installation for manual reconciliation without deleting unrelated configurations. Earlier successful steps are not automatically rolled back.

Run the regression suite with `python3 -B -m pytest tests`. It uses temporary homes and mocked install commands, not your real home or package manager.

Run `python3 -B scripts/check-syntax.py` for first-party shell, Zsh, Lua,
Python, and supported config syntax validation (requires ShellCheck, Bash, Zsh,
Lua, Python 3.11+, and PyYAML for YAML files).
CI runs both checks, including a real Stow/theme/plugin integration test in a
temporary home. Validate Stow manually with `--simulate --verbose`, never
`--adopt`: adoption moves existing user files into the repository.

### Legacy folded Stow links

Older installs ran Stow without `--no-folding`, so some home directories became
symlinks into the checkout, for example `~/.ssh` → `~/.dotfiles/ssh/.ssh` or
`~/.local` → `~/.dotfiles/scripts/.local`. Applications then write private state
(SSH keys, app data) into the repository working tree, where only `.gitignore`
keeps it out of commits and `git clean -fdx` would delete it. `--no-folding`
prevents new folds but does not undo existing ones, so the installer refuses to
stow while `~/.ssh`, `~/.gnupg`, `~/.local`, `~/.local/bin`, `~/.local/share`, or
`~/.local/state` is a symlink into the checkout.

`readlink ~/.ssh` shows where a link points; the directory just below the checkout
in the target is the Stow package (`ssh`). To unfold `~/.ssh`:

```bash
mv ~/.ssh ~/.ssh.folded                  # renames only the symlink
install -d -m 700 ~/.ssh
# Files the repository does not track belong to you; review, then move them:
git -C ~/.dotfiles ls-files --others --directory ssh/.ssh
mv ~/.dotfiles/ssh/.ssh/<file> ~/.ssh/   # repeat for each listed file
stow --no-folding -d ~/.dotfiles -t ~ ssh
rm ~/.ssh.folded                         # the old link: no -r, no trailing slash
```

Use mode 700 only for private directories such as `.ssh` and `.gnupg`; a plain
`mkdir` is enough for `.local` directories. Moved entries keep their path below
the package directory, so `gnupg/.gnupg/private-keys-v1.d/` belongs at
`~/.gnupg/private-keys-v1.d/`. `--directory` lists a wholly untracked
subdirectory as one entry; move those whole, and create missing parent
directories before moving a file from a deeper path.

Verify with `ls -la ~/.ssh`, and check that `git -C ~/.dotfiles status --ignored`
lists nothing under `ssh/.ssh`. Applications that recorded absolute paths in
their own config may need those paths updated after their data moves.

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

### Shared Environment Defaults

Bash, Zsh, and Xsession source `scripts/.config/shell/env.sh`, installed as
`~/.config/shell/env.sh` by the `scripts` Stow package. Stow `scripts` alongside
shell or Xsession packages when installing them manually. The helper defaults
`EDITOR` and `VISUAL` to Neovim and shares the Node, asdf, pnpm, and background
paths, while preserving existing nonempty environment overrides. Managed PATH
entries are prepended once, so reloading a shell does not accumulate duplicates.

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

The scanner checks common shell, TOML, JSON and YAML credential assignments,
including dotted token values. Complete environment references remain
importable. If replacing an imported destination fails during removal, its
complete backup is retained and the recovery path is printed.

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
- **ghostty** - Default terminal, opened through `ghostty-window` (resident instance) with dynamic theming
- **alacritty** - GPU-accelerated terminal, kept for the Hyprland dropdown and the `nmtui` popup

### Window Manager & Desktop
- **AwesomeWM** - Tiling window manager
- **picom** - Compositor for transparency and effects
- **pcmanfm** - File manager
- **yazi** - Terminal file manager (Mod+e), with preview dependencies and plugins

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

## AUR pre-build scan (aurscan + yay)

`install/setup-aurscan.sh` builds [aurscan](https://github.com/manticore-projects/aurscan) and links the `yay` stow package, whose `~/.config/yay/init.lua` makes yay (v13+) scan every AUR package after download and before anything is built or installed.

```bash
install/setup-aurscan.sh            # preview; changes nothing
install/setup-aurscan.sh --apply    # build aurscan, then stow the yay package
```

- **Pinned build.** `install/aurscan/PKGBUILD` is a local copy of upstream's PKGBUILD that builds v0.9.2 from one reviewed git commit (offline, vendored Go dependencies). `makepkg` runs as your user and asks for sudo itself; the helper never calls sudo, never uses `--adopt`, and refuses to touch an existing personal `~/.config/yay/init.lua` (merge the block by hand instead).
- **Static rules only.** The hook always sets `AURSCAN_RULES_ONLY=1`. aurscan's own docs rate models of 3B parameters or fewer as near-random for this job and recommend 14B at minimum, and without the flag it would auto-detect a cloud CLI and send package files off-machine. Neither is acceptable here, so only the built-in rules run.
- **On a flag** aurscan aborts the build and prints a report; to continue anyway you must type `INSTALL` at the prompt. It reads the prompt from the terminal, so without a TTY a flagged package is blocked (fail closed). A desktop notification is also sent. If `/usr/bin/aurscan` is missing the hook aborts every AUR build rather than skipping the scan.
- **Uninstall.** `stow -D --no-folding -d ~/.dotfiles -t ~ yay` removes the hook; `sudo pacman -Rns aurscan` removes the scanner.

## Tmux: Vi navigation and SSH clipboard

The prefix is **Ctrl+a**. Use tmux 3.2+ and an OSC 52-capable terminal such as
Alacritty or Ghostty. Both terminal configs allow clipboard writes; paste from
your computer with **Ctrl+Shift+V** (Cmd+V on macOS).

| Keys | Action |
|------|--------|
| `prefix` then `h/j/k/l` | Select a pane |
| `prefix` then `[` | Enter Vi copy mode |
| `h/j/k/l`, `w/b/e`, `0/^/$` | Move by character, word or line boundary |
| `H/M/L`, `g/G`, `Ctrl+u/d`, `Ctrl+b/f` | Viewport top/middle/bottom, history top/bottom, half/full pages |
| `/`, `?`, `n/N` | Search forward/backward and repeat/reverse |
| `v`, `V`, `Ctrl+v` | Character, line or rectangular selection |
| `y` or Enter | Copy selection to tmux and your computer's clipboard, then exit |
| `Y` or `Alt+y` in copy mode | Copy the selection, exit and paste it into the pane |
| Escape or `q` | Exit copy mode |
| `prefix` then `y` | Copy the cursor's displayed line (including any shell prompt) |
| `prefix` then `Y` | Copy the pane's working directory |
| `prefix` then `]` | Paste the latest tmux buffer, using bracketed paste when supported |
| `prefix` then `a` / `A` | Agent picker / direct jump to the most urgent agent |

Mouse-drag selection uses the same clipboard path as keyboard copying. Standard
tmux Vi motions apply in copy mode; for example, tmux uses a single `g` for the
top of history. `Ctrl+h/j/k/l` also navigate panes, forwarding to Vim/Neovim when
one is running in the pane.

### Over SSH, including nested tmux

Load `config/tmux/tmux.conf` on the remote host too. Copying in remote tmux sends
OSC 52 through SSH to the terminal on your computer. It needs neither X11
forwarding nor `wl-copy`/`xclip` on the remote host. Clipboard writes must be
enabled in the terminal you connect from.

For **local tmux → SSH → remote tmux**, each tmux layer needs clipboard support.
This config enables it for `tmux*` and `screen*` terminals and uses
`set-clipboard on` so the outer tmux forwards inner clipboard writes. With the
same prefix on both layers, press **Ctrl+a, Ctrl+a, [** to enter the inner copy
mode; **Ctrl+a, Ctrl+a, ]** pastes its buffer.

`prefix` then `]` pastes that tmux server's buffer. **Ctrl+Shift+V** pastes your
computer's current clipboard into the active application, including through
SSH and nested tmux. It works even if you copied text in another desktop app;
the remote application does not need permission to read your clipboard.

Reload with `prefix` then `r`. When upgrading from the old clipboard config,
detach and reattach each existing client once (`prefix` then `d`, then
`tmux attach -t SESSION`) so terminal capabilities are rebuilt. Existing
sessions and programs keep running. Reattach each layer for nested tmux.

Check with `tmux info | grep 'Ms:'`: the capability should contain
`52;%p1%s;%p2%s`, with both the selection and data arguments. To verify the full
path, copy multiline/Unicode text remotely, paste it into a local app, then
copy different text locally and paste it into a remote editor. `tmux save-buffer -`
shows the tmux buffer independently of the system clipboard. If the remote
host lacks `tmux-256color` terminfo, install it there before using nested tmux.

## 🚀 App Launchers

Generate custom app launchers that automatically load API keys and run programs. Launchers are created in `~/.local/bin/` with corresponding aliases in the shell-specific files `zsh/.config/zsh/aliases.zsh` or `bash/.config/bash/aliases.sh`.

### Creating a Launcher
Run the interactive script:
```bash
create-app-launcher
```
- Enter the program name (e.g., `code` for VS Code).
- Enter a category (e.g., `ai` for AI tools).
- The script generates:
  - A launcher script (e.g., `code-launcher`) that sources `$HOME/.local/bin/load-api-keys.sh` and runs the program.
  - An alias (e.g., `code-ai`) in the selected shell's aliases file.

### Using Launchers
- After creation, reload your shell: `source ~/.zshrc`
- Use the alias: `code-ai` (loads API keys and launches the app).
- Existing launchers: `nvim-launcher` and `opencode-launcher` (aliases `nvim-ai` and `opencode-ai`).
- Launchers forward arguments (for example, `nvim-ai README.md`) and stop if the API-key loader fails.
- OpenCode uses `--standalone` so its server inherits the loaded keys. Neovim's Sidekick OpenCode tool uses the same launcher.

### Managing Launchers
- Edit the selected shell's aliases file to modify or remove aliases.
- Delete launcher scripts from `~/.local/bin/` as needed.
- For security, ensure `$HOME/.local/bin/load-api-keys.sh` is properly configured (see below).

## 🏷️ Aliases Management

Common aliases live in `scripts/.config/shell/aliases.sh`, installed under
`~/.config/shell/`. The shell-specific alias files source it, then apply local
additions and overrides. Generated launcher aliases remain shell-specific.

### Adding Aliases
- Edit `scripts/.config/shell/aliases.sh` for aliases shared by both shells.
- Add shell-specific aliases or overrides to:
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
- Launchers source `$HOME/.local/bin/load-api-keys.sh`, which can load pass-stored API keys.
- Example: In `$HOME/.local/bin/load-api-keys.sh`, add `export API_KEY=$(pass show api/key)`.

### Tips
- Password input is hidden, and generated passwords are stored without being printed.
- Use `pass git` for version-controlled password stores.
- Backup your `~/.password-store/` directory.
- For apps, prefer environment variables over hardcoded keys.

## 🏗️ Project Structure

First-party configuration packages are organized for GNU Stow: `alacritty/`,
`awesome/`, `bash/`, `btop/`, `ghostty/`, `hyprland/`, `nvim/`, `pcmanfm/`,
`picom/`, `ssh/`, `yazi/`, and
`zsh/`. Other main areas are:

- `install.sh`, `install/`, `lib/`, and the root `install-*.sh` helpers —
  installer, component registry, phase functions, and supporting libraries.
- `config/tmux/` — tmux configuration (not a Stow package).
- `scripts/.local/bin/` — user commands, including `themectl` and `pluginctl`.
- `scripts/.config/shell/` — shared shell environment and aliases.
- `themes/` — palette/layout theme engine, templates, hooks, and previews;
  see [themes/README.md](themes/README.md).
- `plugins/` — optional AwesomeWM/Waybar/Hyprland integrations; see
  [plugins/README.md](plugins/README.md).
- `backgrounds/` — wallpapers and sets; `packages*.list` — package manifests;
  `tests/` — isolated regression tests.

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

### Portable Helper Settings

Stow `scripts` before using these helpers or reloading shells. Shared defaults
preserve exported overrides; shell-specific alias files can still override
the shared aliases.

| Setting | Default / behavior |
|---------|--------------------|
| `DOTFILES_DEV_DIR` | `$HOME/_dev`; used by `dev`, the sessionizer, and tmux prefix-D. |
| `DOTFILES_CONFIG_DIR` | `$XDG_CONFIG_HOME` (normally `$HOME/.config`); used by the sessionizer and tmux prefix-C. |
| `BALENA_ETCHER` | `balenaEtcher.appImage` on `PATH`; one executable name or path, not an inline option string. |
| `TAILSCALE_SSH_HOST` | No default; `tailscale-ssh HOST` or `_omen HOST` takes precedence. |
| `SCREENSHOT_DIR` | `$HOME/screenshots`; images are uniquely named and private (mode `0600`). |
| `SCREENSHOT_OUTPUT_1`, `SCREENSHOT_OUTPUT_2` | Select connected output names for `screenshot_1` / `screenshot_2` (`scrot1` / `scrot2`). |
| `SCREENSHOT_GEOMETRY_1`, `SCREENSHOT_GEOMETRY_2` | Explicit `x,y WIDTHxHEIGHT` rectangles, taking precedence over output discovery. |

Without screenshot overrides, active outputs are ordered left-to-right, then
top-to-bottom; both shortcuts use the same output on a single-monitor machine.
X11 uses `xrandr --current` and `scrot`. Wayland uses `grim -o` so output scaling
and rotation are handled by the capture tool, with discovery via `hyprctl` in
Hyprland or `wlr-randr --json` on compatible wlroots compositors. GNOME-specific
discovery is not supported. Discovery failures stop rather than capturing the
whole desktop. Project selection needs `fzf`; passing a directory directly to
`tmux-sessionizer` does not.
Export custom project paths before starting tmux, or update the environment of
an already running tmux session before using the shortcuts.

`batt`, `balanced`, and `perf` retain their command names but delegate to
`power-mode`, which defaults to `powerprofilesctl` (`power-profiles-daemon`, now
in the shared package list). A working service and the requested profile are
required; unsupported profiles fail without recording a successful switch.
The helper does not enable services or replace another power-policy manager.
Use only one such manager at a time. Widget state follows `XDG_STATE_HOME` and
is updated only after the backend succeeds.

Raw Ryzen controls are no longer applied implicitly. To opt in, install
`ryzenadj`, set `POWER_MODE_BACKEND=ryzenadj`, and provide the corresponding
`POWER_MODE_RYZEN_BATTERY_SAVE`, `POWER_MODE_RYZEN_BALANCED`, or
`POWER_MODE_RYZEN_PERFORMANCE` as `STAPM_mW,FAST_mW,SLOW_mW,TEMP_C`. There are no
built-in limits; positive-integer validation is **not** a hardware-safety check.
Use only settings verified for your machine. Run `power-mode --help` for details.

### Ghostty
- `ghostty/.config/ghostty/config` - Ghostty configuration.
- `ghossty -> ghostty` is a compatibility alias, not a second package to install.
  Existing folded or file-level Stow links keep working after the rename.
  The installer's Stow step migrates recognized legacy links with one combined
  Stow transaction, so a reported conflict leaves the old links intact.
  Absolute or unrelated user-created links are not automatically replaced;
  reconcile any reported conflicts manually.

To preview migration of Ghostty alone from the checkout root:

```bash
stow --simulate --verbose --no-folding -d "$PWD" -t "$HOME" -D ghossty -S ghostty
```

Resolve conflicts first; remove `--simulate` only when ready to apply. Never use
`--adopt` for this migration.

### Default terminal

Ghostty is the default terminal. `scripts/.local/bin/ghostty-window` opens
windows in one resident Ghostty instance with `ghostty +new-window`, which is
faster than a cold start. If nothing owns the bus name it starts that instance
itself, so D-Bus never activates the reduced-environment systemd unit; without
a reachable session bus it falls back to plain `ghostty`. The session starts the
resident instance (awesome's `run_once`, Hyprland's `exec-once`), and
`scripts/.config/shell/env.sh` exports `TERMINAL=ghostty-window`. Alacritty
stays for the Hyprland dropdown terminal and the `nmtui` popup. The Ghostty
config sets JetBrainsMono Nerd Font at size 10.

### PhotoCraft MCP

`scripts/.local/bin/photocraft-mcp` starts PhotoCraft's MCP server
(`photocraft-cli mcp`, stdio) with one stable command. If the PhotoCraft app's
control server is listening on `127.0.0.1:47800` and the token file exists, it
bridges to the running app; otherwise it starts the headless engine and says so
on stderr. The token is passed to `photocraft-cli` by file path only.

The control server only runs when the app is launched with a control port. The
token file is created on first use, so port and token stay stable:

```bash
photocraft --control 47800 \
    --control-token-file ~/.config/photocraft/control.token \
    --automation-read-root ~ --automation-write-root ~/Pictures
```

Setting `PHOTOCRAFT_CONTROL_PORT` and `PHOTOCRAFT_CONTROL_TOKEN_FILE` in the
app's environment does the same. (The app's `instance.json` is its
single-instance socket, not the control server.) Then register the wrapper:

```bash
claude mcp add --scope user photocraft -- ~/.local/bin/photocraft-mcp
```

Variables the wrapper reads:
- `PHOTOCRAFT_CONTROL_PORT` (default `47800`)
- `PHOTOCRAFT_CONTROL_TOKEN_FILE` (default `~/.config/photocraft/control.token`,
  under `PHOTOCRAFT_CONFIG_DIR` or `XDG_CONFIG_HOME` when set)
- `PHOTOCRAFT_MCP_READ_ROOT` (default `$HOME`) and `PHOTOCRAFT_MCP_WRITE_ROOT`
  (default `$HOME/Pictures`, created if missing): file tools only work beneath
  these roots.

### Yazi
- `yazi/.config/yazi/` - `yazi.toml`, `keymap.toml`, `init.lua` and `package.toml`.
  Mod+e opens Yazi in the default terminal.
- Plugins are pinned in `package.toml` and installed by the installer through
  `ya pkg install`. `ya pkg add/upgrade/delete` edit the tracked file through
  the Stow link.
- Custom keys: `l`/Enter smart-enter, `T` maximize preview, `c m` chmod,
  `g .` to `~/.dotfiles`, `g _` to `~/_dev`, `Alt+z` Zen, `[` / `]` switch tabs.
- Look: `user@host` in the header, `owner:group` in the status bar, the
  `size_mtime` linemode (size plus date, or the time for today's files) and
  icons coloured from the palette. The template's icon block is generated by
  `themes/yazi-icons.py`; rerun it against the new preset
  (`themes/yazi-icons.py <theme-dark.toml>`) when Yazi updates.
- Dev: githead in the header and relative line numbers. Digits 1-9 start
  motions (`3j`), so tab switching moved from the digits to `[` / `]`.
- Rich previews: Markdown through piper and glow; CSV, TSV, Parquet and DB
  files through duckdb (`Alt+h` / `Alt+l` scroll columns); audio and video
  through mediainfo; archives through ouch. mediainfo is deprecated upstream
  and supports Yazi up to 26.9.1; `yazi.toml` notes the fallback.
- `Alt+z` toggles Zen: no parent column, status bar or frame, and a wider
  preview. `zen.yazi` is a tracked local plugin; `ya pkg` plugins stay ignored.
- The `y` shell wrapper (`scripts/.config/shell/aliases.sh`) changes to Yazi's
  last directory on exit.
- The preview pane is half the window and image sizes are tuned for Ghostty.
  tmux sets `allow-passthrough` and `update-environment TERM TERM_PROGRAM`, so
  images work inside tmux.
- Preview dependencies (`7zip`, `zoxide`, `resvg`, `chafa`, `poppler`,
  `imagemagick`, `glow`, `duckdb`, `mediainfo`, `ouch`) are in `packages.list`.
- `themectl` renders the colours to `~/.config/yazi/theme.toml`; see
  [themes/README.md](themes/README.md).

To take this live on an existing machine:

```bash
sudo pacman -S --needed yazi 7zip zoxide resvg chafa poppler imagemagick glow duckdb mediainfo ouch
cd ~/.dotfiles
stow --no-folding -d ~/.dotfiles -t ~ yazi
stow --no-folding -R -d ~/.dotfiles -t ~ scripts
themectl apply
ya pkg install
tmux source-file ~/.tmux.conf
```

Then restart awesome (or log out and back in) so the resident Ghostty starts and
`TERMINAL` is exported.

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
- `themectl` selects an AwesomeWM desktop layout independently from a color
  palette rendered to supported application configs. For example,
  `themectl set mono --colors nord` selects the Mono layout with the Nord
  palette; `themectl set --colors nord` changes only the palette. See
  [themes/README.md](themes/README.md) for commands and supported targets.
- Optional widgets and bindings are managed separately by `pluginctl`; see
  [plugins/README.md](plugins/README.md).
- Wallpapers: `backgrounds/` (linked to `~/.backgrounds`)
- Monitors: `display-detect` lays out whatever is connected (ultrawide
  first, 16:9 to its right, a laptop panel alone or below) and picks each
  output's wallpaper from `backgrounds/sets/`, under both Awesome and
  Hyprland, so the desktop and laptop share one config. Plugging or
  unplugging a monitor re-applies it (Hyprland's monitor events; under
  Awesome, `display-detect watch` following udev), and `Super+P` does it by
  hand. See `backgrounds/sets/README.md`.

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
    # zsh: zsh/.config/zsh/aliases.zsh
    # bash: bash/.config/bash/aliases.sh
    ```

5. **Pass issues**: If passwords don't insert:
    ```bash
    gpg --list-keys  # Ensure GPG key exists
    pass  # Test basic functionality
    ```

6. **Theme not applying**: Check `themectl current --colors` and `themectl current`, then run `themectl apply`. See [themes/README.md](themes/README.md) for theme troubleshooting.

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

#!/bin/bash
# Main installation script for dotfiles

set -euo pipefail

# Get script directory
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source helper functions
source "$DOTFILES_DIR/lib/logging.sh"
source "$DOTFILES_DIR/lib/validation.sh"
source "$DOTFILES_DIR/lib/cleanup.sh"
source "$DOTFILES_DIR/lib/args.sh"
source "$DOTFILES_DIR/lib/components.sh"

# Set up cleanup trap
setup_cleanup_trap

# Parse command-line arguments
parse_args "$@"

# Print header
log_header "Dotfiles Installation Script"
log_info "Dotfiles directory: $DOTFILES_DIR"

# Show dry-run notice
if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  DRY RUN MODE - No changes will be made                 ║${NC}"
    echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
fi

# Validate prerequisites
log_step "Checking prerequisites..."
require_arch
require_command git "git is required but not installed"
require_command curl "curl is required but not installed"
validate_directory "$DOTFILES_DIR"

# Interactive component selection
select_components

# Show summary and confirm
show_summary
confirm_installation

# Shell selection (if shell component is selected)
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "shell" ]]; then
        select_shell
        break
    fi
done

# Count selected components for progress
progress_init ${#SELECTED_COMPONENTS[@]}

# ═══════════════════════════════════════════════════════════════
# INSTALLATION STEPS
# ═══════════════════════════════════════════════════════════════

# Install yay if selected and not present
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "yay" ]]; then
        if ! command_exists yay; then
            progress_step "Installing yay AUR helper"
            if validate_file "$DOTFILES_DIR/install-yay.sh"; then
                execute bash "$DOTFILES_DIR/install-yay.sh" || {
                    progress_complete "failed"
                    log_warn "Failed to install yay"
                }
                progress_complete "done"
            else
                progress_complete "failed"
                die "install-yay.sh not found"
            fi
        else
            progress_step "yay already installed"
            progress_complete "skipped"
        fi
        break
    fi
done

# Install packages if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "packages" ]]; then
        progress_step "Installing system packages"
        
        packages_file="$DOTFILES_DIR/packages.list"
        validate_file "$packages_file" || die "packages.list not found"
        validate_packages_file "$packages_file" || die "Invalid packages in packages.list"
        
        all_packages=$(grep -v '^#' "$packages_file" | grep -v '^$' || true)
        if [[ -n "$all_packages" ]]; then
            echo "$all_packages" | while IFS= read -r pkg; do
                [[ -z "$pkg" ]] && continue
                log_info "Installing: $pkg"
                execute yay -S --needed --noconfirm "$pkg" || log_warn "Failed to install: $pkg"
            done
        fi
        
        progress_complete "done"
        break
    fi
done

# Install Node.js version manager if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "node" ]]; then
        progress_step "Installing Node.js version manager"
        if validate_file "$DOTFILES_DIR/install-node-manager.sh" false; then
            execute bash "$DOTFILES_DIR/install-node-manager.sh" || log_warn "Node.js version manager installation failed"
            progress_complete "done"
        else
            progress_complete "skipped"
            log_warn "install-node-manager.sh not found"
        fi
        break
    fi
done

# Install YubiKey tools if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "yubikey" ]]; then
        progress_step "Installing YubiKey tools"
        execute yay -S --needed --noconfirm yubikey-manager yubico-authenticator-bin pcsclite ccid || {
            log_warn "Failed to install some YubiKey packages"
        }
        execute systemctl enable pcscd.service || log_warn "Failed to enable pcscd service"
        progress_complete "done"
        break
    fi
done

# Initialize git submodules
progress_step "Initializing git submodules"
execute git submodule update --init --recursive || log_warn "Failed to update git submodules"
progress_complete "done"

# Setup symlinks with GNU Stow
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "stow" ]]; then
        progress_step "Setting up symlinks with GNU Stow"
        require_command stow "stow is required but not installed"
        
        # Base packages (without shell - added dynamically based on selection)
        stow_packages=("awesome" "ssh" "alacritty" "btop" "nvim" "picom" "pcmanfm" "scripts" "ghossty" "gnupg")
        
        # Add selected shell if shell component was selected
        if [[ -n "$SELECTED_SHELL" ]]; then
            stow_packages+=("$SELECTED_SHELL")
            
            # Handle shell switching - unstow old shell if different
            current_shell=$(detect_current_shell)
            if [[ -n "$current_shell" ]] && [[ "$current_shell" != "$SELECTED_SHELL" ]]; then
                log_info "Switching from $current_shell to $SELECTED_SHELL..."
                if [[ -d "$DOTFILES_DIR/$current_shell" ]]; then
                    execute stow -d "$DOTFILES_DIR" -t "$HOME" -D "$current_shell" 2>/dev/null || true
                fi
            fi
        else
            # No shell selected, default to zsh for backward compatibility
            stow_packages+=("zsh")
        fi
        
        # Handle root-level dotfiles (.bashrc, .zshrc) that aren't symlinks
        for shell_file in .bashrc .zshrc; do
            target="$HOME/$shell_file"
            if [[ -f "$target" ]] && [[ ! -L "$target" ]]; then
                log_info "Backing up existing $shell_file (not a symlink)"
                backup_item "$target" || log_warn "Failed to backup $target"
                execute rm -f "$target" || log_warn "Failed to remove $target"
            fi
        done
        
        # Clean up existing symlinks and backup real configs
        for package in "${stow_packages[@]}"; do
            if [[ -d "$DOTFILES_DIR/$package/.config" ]]; then
                config_dir="$HOME/.config/$package"
                if [[ -L "$config_dir" ]]; then
                    # It's a symlink (created by stow) - just remove it, no backup needed
                    execute rm -f "$config_dir" || log_warn "Failed to remove symlink $config_dir"
                elif [[ -d "$config_dir" ]]; then
                    # It's a real directory - backup before removing
                    backup_item "$config_dir" || log_warn "Failed to backup $config_dir"
                    execute rm -rf "$config_dir" || log_warn "Failed to remove $config_dir"
                fi
            fi
        done
        
        # Setup new symlinks (stow handles re-stowing gracefully)
        for package in "${stow_packages[@]}"; do
            if [[ -d "$DOTFILES_DIR/$package" ]]; then
                log_info "Stowing $package..."
                execute stow -d "$DOTFILES_DIR" -t "$HOME" "$package" || log_warn "Failed to stow $package"
            else
                log_warn "$package directory not found, skipping..."
            fi
        done
        
        # Make scripts executable
        scripts_dir="$HOME/scripts/.local/bin"
        if [[ -d "$scripts_dir" ]]; then
            execute find "$scripts_dir" -type f -exec chmod +x {} + || log_warn "Failed to make some scripts executable"
        fi
        
        progress_complete "done"
        break
    fi
done

# Update terminal shell defaults (if shell was selected)
if [[ -n "$SELECTED_SHELL" ]]; then
    progress_step "Updating terminal shell defaults to $SELECTED_SHELL"
    
    # Update Alacritty shell
    alacritty_conf="$HOME/.config/alacritty/alacritty.toml"
    if [[ -f "$alacritty_conf" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[dry-run] Would update $alacritty_conf to use $SELECTED_SHELL"
        else
            sed -i "s|shell = \"/bin/.*\"|shell = \"/bin/$SELECTED_SHELL\"|" "$alacritty_conf" || log_warn "Failed to update Alacritty shell"
            log_info "Updated Alacritty to use $SELECTED_SHELL"
        fi
    fi
    
    # Update tmux default-shell
    tmux_conf="$HOME/.config/tmux/tmux.conf"
    if [[ -f "$tmux_conf" ]]; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[dry-run] Would update $tmux_conf to use $SELECTED_SHELL"
        else
            sed -i "s|default-shell \"/usr/bin/.*\"|default-shell \"/usr/bin/$SELECTED_SHELL\"|" "$tmux_conf" || log_warn "Failed to update tmux default-shell"
            log_info "Updated tmux to use $SELECTED_SHELL"
        fi
    fi
    
    progress_complete "done"
fi

# Setup theme if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "theme" ]]; then
        progress_step "Setting up Alacritty theme"
        theme_script="$DOTFILES_DIR/themes/theme.sh"
        
        if validate_file "$theme_script" false; then
            source "$theme_script" || die "Failed to source theme.sh"
            validate_theme_variables || die "Invalid theme configuration"
            
            mkdir -p "$HOME/.config/alacritty"
            cat > "$HOME/.config/alacritty/theme.toml" <<EOF
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
            progress_complete "done"
        else
            progress_complete "skipped"
            log_warn "Theme setup script not found"
        fi
        break
    fi
done

# Setup backgrounds if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "backgrounds" ]]; then
        progress_step "Setting up desktop backgrounds"
        if [[ -d "$DOTFILES_DIR/backgrounds" ]]; then
            safe_symlink "$DOTFILES_DIR/backgrounds" "$HOME/.backgrounds" || log_warn "Failed to link backgrounds"
            progress_complete "done"
        else
            progress_complete "skipped"
            log_warn "Backgrounds directory not found"
        fi
        break
    fi
done

# Setup tmux if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "tmux" ]]; then
        progress_step "Setting up Tmux configuration"
        mkdir -p "$HOME/.config/tmux"
        
        tmux_conf="$DOTFILES_DIR/config/tmux/tmux.conf"
        if validate_file "$tmux_conf" false; then
            safe_symlink "$tmux_conf" "$HOME/.config/tmux/tmux.conf" || log_warn "Failed to symlink tmux.conf"
        fi
        
        cat > "$HOME/.config/tmux/theme.conf" <<'EOF'
# Tmux theme colors
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
        
        safe_symlink "$HOME/.config/tmux/tmux.conf" "$HOME/.tmux.conf" || log_warn "Failed to symlink tmux config"
        progress_complete "done"
        break
    fi
done

# Install LazyVim if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "lazyvim" ]]; then
        progress_step "Installing LazyVim Neovim distribution"
        if [[ -d "$DOTFILES_DIR/nvim" ]] && command_exists nvim; then
            if validate_file "$DOTFILES_DIR/install-lazyvim.sh" false; then
                execute bash "$DOTFILES_DIR/install-lazyvim.sh" || log_warn "LazyVim installation failed"
                progress_complete "done"
            else
                progress_complete "skipped"
            fi
        else
            progress_complete "skipped"
            log_warn "Neovim not installed or nvim directory not found"
        fi
        break
    fi
done

# Print final summary
progress_summary

# Show post-installation instructions
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              Post-Installation Instructions             ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${YELLOW}1. Restart your terminal or run:${NC}"
if [[ "$SELECTED_SHELL" == "bash" ]]; then
    echo -e "     ${GREEN}source ~/.bashrc${NC}"
    echo -e "     ${YELLOW}  (Starship prompt will be active after reload)${NC}"
else
    echo -e "     ${GREEN}source ~/.zshrc${NC}"
fi
echo ""
echo -e "  ${YELLOW}2. You may need to log out and back in for some changes${NC}"
echo -e "     ${YELLOW}to take effect.${NC}"
echo ""
echo -e "  ${YELLOW}3. Run ${GREEN}nvim${NC}${YELLOW} to start using LazyVim.${NC}"
echo ""
echo -e "  ${YELLOW}4. Backups of replaced configs are stored in:${NC}"
echo -e "     ${GREEN}~/.dotfiles-backups/${NC}"
echo ""
if [[ "$SELECTED_SHELL" == "bash" ]]; then
    echo -e "  ${YELLOW}5. Customize your Starship prompt:${NC}"
    echo -e "     ${GREEN}starship preset catppuccin-mocha -o ~/.config/starship.toml${NC}"
    echo -e "     ${YELLOW}  Or edit ~/.config/starship.toml directly.${NC}"
    echo ""
fi
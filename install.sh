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

require_non_root

# The installer currently writes fixed Home-relative configuration paths.
# Reject alternate XDG locations before any installation work rather than
# silently mixing two configuration roots.
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ "$XDG_CONFIG_HOME" != "$HOME/.config" ]]; then
    die "Non-default XDG_CONFIG_HOME is not supported by this installer: $XDG_CONFIG_HOME"
fi
export XDG_CONFIG_HOME

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
ui_initialize

# Interactive component selection
select_components
validate_component_dependencies || exit 1
if [[ ${#SELECTED_COMPONENTS[@]} -eq 0 ]]; then
    log_info "No components selected; nothing to install."
    exit 0
fi

select_window_manager || exit 1

# Select the shell before the summary so the confirmation reflects the full plan.
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    if [[ "$name" == "shell" ]]; then
        select_shell || exit 1
        break
    fi
done

# Show summary and confirm
show_summary
confirm_installation

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
                yay_args=()
                [[ "$NON_INTERACTIVE" != "true" ]] || yay_args+=(--non-interactive)
                execute bash "$DOTFILES_DIR/install-yay.sh" "${yay_args[@]}" || die "Failed to install yay"
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
        
        package_files=("$DOTFILES_DIR/packages.list")
        case "$WINDOW_MANAGER" in
            awesome) package_files+=("$DOTFILES_DIR/packages-awesome.list") ;;
            both) package_files+=("$DOTFILES_DIR/packages-awesome.list" "$DOTFILES_DIR/packages-hyprland.list") ;;
            hyprland) package_files+=("$DOTFILES_DIR/packages-hyprland.list") ;;
            *) die "Invalid window manager: $WINDOW_MANAGER" ;;
        esac

        for packages_file in "${package_files[@]}"; do
            validate_file "$packages_file" || die "Package manifest not found: $packages_file"
            validate_packages_file "$packages_file" || die "Invalid packages in $packages_file"

            while IFS= read -r pkg || [[ -n "$pkg" ]]; do
                [[ -z "$pkg" || "$pkg" == \#* ]] && continue
                log_info "Installing: $pkg"
                execute yay -S --needed --noconfirm -- "$pkg" || die "Failed to install: $pkg"
            done < "$packages_file"
        done
        
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
            node_args=()
            if [[ "$NON_INTERACTIVE" == "true" ]]; then
                node_args+=("--non-interactive")
            fi
            if [[ "$DRY_RUN" == "true" ]]; then
                node_args+=("--dry-run")
            fi
            execute bash "$DOTFILES_DIR/install-node-manager.sh" "${node_args[@]}" || die "Node.js version manager installation failed"
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
        execute yay -S --needed --noconfirm yubikey-manager yubico-authenticator-bin pcsclite ccid || die "Failed to install YubiKey packages"
        execute sudo systemctl enable pcscd.service || die "Failed to enable pcscd service"
        progress_complete "done"
        break
    fi
done

# Do not rewrite terminal configuration for a shell that is unavailable.
if [[ -n "$SELECTED_SHELL" && "$DRY_RUN" != "true" ]]; then
    require_command "$SELECTED_SHELL" "Selected shell is not installed: $SELECTED_SHELL"
    if [[ "$SELECTED_SHELL" == "zsh" ]]; then
        [[ -r /usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme ]] ||
            die "Powerlevel10k is required by the selected Zsh configuration"
    else
        require_command starship "Starship is required by the selected Bash configuration"
    fi
fi

# Setup symlinks with GNU Stow
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "stow" ]]; then
        progress_step "Setting up symlinks with GNU Stow"
        if [[ "$DRY_RUN" != "true" ]]; then
            require_command stow "stow is required but not installed"
        fi
        execute git -C "$DOTFILES_DIR" submodule update --init --recursive || die "Failed to update git submodules"
        
        # Select exactly the requested window-manager package(s); shared
        # configuration is stowed for every mode.
        stow_packages=()
        case "$WINDOW_MANAGER" in
            awesome) stow_packages+=("awesome" "picom") ;;
            both) stow_packages+=("awesome" "hyprland" "picom") ;;
            hyprland) stow_packages+=("hyprland") ;;
            *) die "Invalid window manager: $WINDOW_MANAGER" ;;
        esac
        stow_packages+=("ssh" "alacritty" "btop" "nvim" "pcmanfm" "scripts" "ghossty" "gnupg" "xsession")
        
        # Add selected shell if shell component was selected
        if [[ -n "$SELECTED_SHELL" ]]; then
            stow_packages+=("$SELECTED_SHELL")
        fi
        
        # Let Stow merge directories and reject conflicts without deleting user configs.
        for package in "${stow_packages[@]}"; do
            if [[ -d "$DOTFILES_DIR/$package" ]]; then
                log_info "Stowing $package..."
                shell_backup=""
                if [[ "$package" == "$SELECTED_SHELL" ]]; then
                    target="$HOME/.${SELECTED_SHELL}rc"
                    if [[ -f "$target" && ! -L "$target" ]]; then
                        backup_item "$target" || die "Could not back up $target"
                        if [[ "$DRY_RUN" != true ]]; then
                            shell_backup="${BACKUPS[-1]}"
                        fi
                        execute rm -f -- "$target" || die "Could not remove $target"
                    fi
                fi
                if ! execute stow -d "$DOTFILES_DIR" -t "$HOME" "$package"; then
                    if [[ -n "$shell_backup" ]]; then
                        restore_backup "$shell_backup" "$target" || log_error "Restore failed; original config is at $shell_backup"
                    fi
                    die "Failed to stow $package; reconcile the reported conflicts and rerun"
                fi
            else
                die "$package directory not found"
            fi
        done

        # pluginctl regenerates the waybar template and hypr plugins module
        # that themectl/hyprland.lua expect to already exist.
        execute "$DOTFILES_DIR/plugins/pluginctl" refresh || log_warn "pluginctl refresh failed; run it manually"

        # Generated theme files are symlinks into themes/out, which is not
        # tracked; render them so the stowed configs do not dangle.
        execute "$DOTFILES_DIR/themes/themectl" apply || log_warn "themectl apply failed; run it manually"
        
        progress_complete "done"
        break
    fi
done

# Setup theme if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")

    if [[ "$name" == "theme" ]]; then
        progress_step "Applying system theme"
        # themectl renders every app's colors from one palette; see themes/README.md.
        execute "$DOTFILES_DIR/themes/themectl" set "${DOTFILES_THEME:-mocha-peach}" || die "Failed to apply theme"
        progress_complete "done"
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
            safe_symlink "$DOTFILES_DIR/backgrounds" "$HOME/.backgrounds" || die "Failed to link backgrounds"
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
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[dry-run] Would link tmux config and theme into ~/.config/tmux and ~/.tmux.conf"
            progress_complete "done"
            break
        fi

        mkdir -p "$XDG_CONFIG_HOME/tmux"

        tpm_dir="$HOME/.tmux/plugins/tpm"
        if [[ ! -x "$tpm_dir/tpm" ]]; then
            execute git clone --depth 1 -- https://github.com/tmux-plugins/tpm "$tpm_dir" || die "Failed to install TPM"
        fi
        if [[ "$DRY_RUN" != "true" && ! -x "$tpm_dir/tpm" ]]; then
            die "TPM installation did not produce an executable plugin manager"
        fi

        tmux_conf="$DOTFILES_DIR/config/tmux/tmux.conf"
        if validate_file "$tmux_conf" false; then
            safe_symlink "$tmux_conf" "$XDG_CONFIG_HOME/tmux/tmux.conf" || die "Failed to symlink tmux.conf"
        else
            die "Tmux configuration not found"
        fi

        theme_target=$(readlink -f -- "$XDG_CONFIG_HOME/tmux/theme.conf")
        backup_item "$theme_target" || die "Failed to back up tmux theme"
        cat > "$XDG_CONFIG_HOME/tmux/theme.conf" <<'EOF'
# Tmux theme colors
set -g status-style bg=black,fg=white
set -g status-left-style bg=black,fg=brightblue
set -g status-right-style bg=black,fg=brightblue
set -g pane-border-style fg=black
set -g pane-active-border-style fg=blue
set -g window-status-current-style bg=blue,fg=black
set -g window-status-style bg=black,fg=white
set -g message-style bg=brightyellow,fg=black
EOF

        safe_symlink "$XDG_CONFIG_HOME/tmux/tmux.conf" "$HOME/.tmux.conf" || die "Failed to symlink tmux config"
        if [[ -x "$tpm_dir/bin/install_plugins" ]]; then
            "$tpm_dir/bin/install_plugins" || die "Failed to install tmux plugins"
        fi
        progress_complete "done"
        break
    fi
done

# Edit resolved targets so GNU sed does not replace Stow symlinks.
if [[ -n "$SELECTED_SHELL" ]]; then
    for terminal_config in "$XDG_CONFIG_HOME/alacritty/alacritty.toml" "$XDG_CONFIG_HOME/tmux/tmux.conf"; do
        if [[ -f "$terminal_config" ]]; then
            target=$(readlink -f -- "$terminal_config")
            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[dry-run] Would update $terminal_config to use $SELECTED_SHELL"
            else
                backup_item "$target" || die "Failed to back up $terminal_config"
                if [[ "$terminal_config" == *.toml ]]; then
                    sed -i "s|shell = \"/bin/[^\"]*\"|shell = \"/bin/$SELECTED_SHELL\"|" "$target"
                else
                    sed -i -E "s|default-shell \"[^\"]*\"|default-shell \"/usr/bin/$SELECTED_SHELL\"|" "$target"
                fi
            fi
        fi
    done

    set_login_shell "$SELECTED_SHELL" || die "Failed to set the login shell to $SELECTED_SHELL"
fi

# Install LazyVim if selected
for component in "${SELECTED_COMPONENTS[@]}"; do
    name=$(get_component_name "$component")
    step=$(get_component_step "$component")
    
    if [[ "$name" == "lazyvim" ]]; then
        progress_step "Installing LazyVim Neovim distribution"
        if [[ -d "$DOTFILES_DIR/nvim" ]] && command_exists nvim; then
            if validate_file "$DOTFILES_DIR/install-lazyvim.sh" false; then
                lazyvim_args=()
                if [[ "$NON_INTERACTIVE" == "true" ]]; then
                    lazyvim_args+=("--non-interactive")
                fi
                if [[ "$DRY_RUN" == "true" ]]; then
                    lazyvim_args+=("--dry-run")
                fi
                execute bash "$DOTFILES_DIR/install-lazyvim.sh" "${lazyvim_args[@]}" || die "LazyVim installation failed"
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

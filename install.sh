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
validate_component_privileges || exit 1

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

        packages=()
        declare -A seen_packages=()
        for packages_file in "${package_files[@]}"; do
            validate_file "$packages_file" || die "Package manifest not found: $packages_file"
            validate_packages_file "$packages_file" || die "Invalid packages in $packages_file"

            # Validate all manifests before installing the listed packages.
            while IFS= read -r pkg || [[ -n "$pkg" ]]; do
                [[ -z "$pkg" || "$pkg" == \#* ]] && continue
                if [[ -z "${seen_packages[$pkg]+x}" ]]; then
                    seen_packages[$pkg]=1
                    packages+=("$pkg")
                fi
            done < "$packages_file"
        done

        if [[ ${#packages[@]} -gt 0 ]]; then
            for pkg in "${packages[@]}"; do
                log_info "Installing: $pkg"
            done
            execute yay -S --needed --noconfirm -- "${packages[@]}" || die "Failed to install packages"
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
        # No indexed gitlinks exist in this repository, so no update is needed.
        
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
                # --no-folding links files, never whole directories: a folded
                # ~/.local once sent every app's data into scripts/.local.
                if ! execute stow --no-folding -d "$DOTFILES_DIR" -t "$HOME" "$package"; then
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

        # PCManFM's side pane and GTK file dialogs list Documents, Downloads,
        # ... only as bookmarks; add the XDG folders, keeping existing ones.
        execute "$DOTFILES_DIR/scripts/.local/bin/gtk-bookmarks" || log_warn "gtk-bookmarks failed; run it manually"

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
        # DOTFILES_THEME names that palette (layouts are selected separately).
        execute "$DOTFILES_DIR/themes/themectl" set --colors "${DOTFILES_THEME:-mocha-peach}" || die "Failed to apply theme"
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

        # Link the tracked icon theme rather than replacing it with a minimal
        # generated file. safe_symlink backs up a previous theme or symlink.
        safe_symlink "$DOTFILES_DIR/config/tmux/theme.conf" "$XDG_CONFIG_HOME/tmux/theme.conf" || die "Failed to link tmux theme"

        # Persistence is also needed when the separate scripts component is not
        # selected: save deliberate closures before tmux's last session exits.
        mkdir -p "$HOME/.local/bin"
        # Relative links remain compatible with the scripts Stow package.
        tmux_helper=$(realpath --relative-to="$HOME/.local/bin" "$DOTFILES_DIR/scripts/.local/bin/tmux-save-workspace") || die "Failed to locate tmux persistence helper"
        safe_symlink "$tmux_helper" "$HOME/.local/bin/tmux-save-workspace" || die "Failed to link tmux persistence helper"

        safe_symlink "$XDG_CONFIG_HOME/tmux/tmux.conf" "$HOME/.tmux.conf" || die "Failed to symlink tmux config"
        if [[ -x "$tpm_dir/bin/install_plugins" ]]; then
            "$tpm_dir/bin/install_plugins" || die "Failed to install tmux plugins"
        fi

        # Claude Code, Codex and OpenCode report their state to the agent
        # plugin through hooks; without them the status bar falls back to
        # guessing. TPM puts plugins under XDG_CONFIG_HOME when tmux.conf
        # lives there, else under ~/.tmux/plugins.
        agent_bin=""
        for agent_dir in "$XDG_CONFIG_HOME/tmux/plugins" "$HOME/.tmux/plugins"; do
            if [[ -x "$agent_dir/tmux-agentic-plugin/bin/tmux-agent" ]]; then
                agent_bin="$agent_dir/tmux-agentic-plugin/bin/tmux-agent"
                break
            fi
        done
        if [[ -z "$agent_bin" ]]; then
            [[ "$DRY_RUN" == "true" ]] || log_warn "tmux-agentic-plugin not installed; run prefix + I in tmux, then its bin/tmux-agent install-hooks"
        elif command_exists jq; then
            execute "$agent_bin" install-hooks || log_warn "Failed to install tmux-agent hooks"
        fi
        progress_complete "done"
        break
    fi
done

# Edit resolved targets so GNU sed does not replace Stow symlinks.
if [[ -n "$SELECTED_SHELL" ]]; then
    selected_shell_path=""
    if selected_shell_path=$(command -v "$SELECTED_SHELL" 2>/dev/null); then
        selected_shell_path=$(readlink -f -- "$selected_shell_path") || die "Could not resolve selected shell: $SELECTED_SHELL"
    elif [[ "$DRY_RUN" == "true" ]]; then
        # Planning only: a dry run must not require the selected shell to exist.
        selected_shell_path="/usr/bin/$SELECTED_SHELL"
    else
        die "Selected shell is not installed: $SELECTED_SHELL"
    fi

    # Escape sed replacement metacharacters (using | as the delimiter).
    escaped_shell_path=${selected_shell_path//\\/\\\\}
    escaped_shell_path=${escaped_shell_path//&/\\&}
    escaped_shell_path=${escaped_shell_path//|/\\|}
    for terminal_config in "$XDG_CONFIG_HOME/alacritty/alacritty.toml" "$XDG_CONFIG_HOME/tmux/tmux.conf"; do
        if [[ -f "$terminal_config" ]]; then
            target=$(readlink -f -- "$terminal_config") || die "Could not resolve $terminal_config"
            if [[ "$terminal_config" == *.toml ]]; then
                setting_pattern='^[[:space:]]*shell[[:space:]]*=[[:space:]]*"[^"]*"'
                current_settings=$(sed -nE 's/^[[:space:]]*shell[[:space:]]*=[[:space:]]*"([^"]*)".*/x\1/p' "$target")
                replacement="shell = \"$escaped_shell_path\""
            else
                setting_pattern='^([[:space:]]*set(-option)?[[:space:]]+-[gs]+([[:space:]]+-[gs]+)*[[:space:]]+default-shell[[:space:]]+")([^"]*)(".*)$'
                current_settings=$(sed -nE "s|$setting_pattern|x\\4|p" "$target")
                replacement="\\1$escaped_shell_path\\5"
            fi
            [[ -n "$current_settings" ]] || continue
            has_shell_change=false
            while IFS= read -r current_setting; do
                current_setting=${current_setting#x}
                if [[ "$current_setting" != "$selected_shell_path" ]]; then
                    has_shell_change=true
                    break
                fi
            done <<< "$current_settings"
            [[ "$has_shell_change" == "true" ]] || continue
            if [[ "$DRY_RUN" == "true" ]]; then
                log_info "[dry-run] Would update $terminal_config to use $SELECTED_SHELL"
            else
                backup_item "$target" || die "Failed to back up $terminal_config"
                sed -i -E "s|$setting_pattern|$replacement|" "$target"
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

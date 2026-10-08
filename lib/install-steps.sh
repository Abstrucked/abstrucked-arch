#!/bin/bash
# Installer phase implementations. Sourcing this file defines policy and
# functions only; no installation work is performed until a function is called.
if [[ -n "${_INSTALL_STEPS_SH_LOADED:-}" ]]; then
    return 0
fi
_INSTALL_STEPS_SH_LOADED=1

source "$(dirname "${BASH_SOURCE[0]}")/component-registry.sh"
source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"
source "$(dirname "${BASH_SOURCE[0]}")/validation.sh"
source "$(dirname "${BASH_SOURCE[0]}")/cleanup.sh"
source "$(dirname "${BASH_SOURCE[0]}")/args.sh"
source "$(dirname "${BASH_SOURCE[0]}")/components.sh"
declare -agr COMMON_STOW_PACKAGES=(ssh alacritty btop nvim pcmanfm scripts ghostty gnupg xsession)
declare -gr P10K_THEME_PATH=/usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme
declare -gr DRY_RUN_SHELL_PATH_PREFIX=/usr/bin

component_selected() {
    local wanted=${1:-} component
    for component in "${SELECTED_COMPONENTS[@]}"; do
        [[ "${component##*|}" == "$wanted" ]] && return 0
    done
    return 1
}

install_yay() {
    if ! command_exists yay; then
        progress_step "Installing yay AUR helper"
        if validate_file "$DOTFILES_DIR/install-yay.sh"; then
            local -a yay_args=()
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
}

install_packages() {
    progress_step "Installing system packages"
    local -a package_files=("$DOTFILES_DIR/packages.list") packages=()
    local packages_file pkg
    case "$WINDOW_MANAGER" in
        awesome) package_files+=("$DOTFILES_DIR/packages-awesome.list") ;;
        both) package_files+=("$DOTFILES_DIR/packages-awesome.list" "$DOTFILES_DIR/packages-hyprland.list") ;;
        hyprland) package_files+=("$DOTFILES_DIR/packages-hyprland.list") ;;
        *) die "Invalid window manager: $WINDOW_MANAGER" ;;
    esac
    local -A seen_packages=()
    # Validate all manifests before submitting one deduplicated transaction.
    for packages_file in "${package_files[@]}"; do
        validate_file "$packages_file" || die "Package manifest not found: $packages_file"
        validate_packages_file "$packages_file" || die "Invalid packages in $packages_file"
        while IFS= read -r pkg || [[ -n "$pkg" ]]; do
            [[ -z "$pkg" || "$pkg" == \#* ]] && continue
            if [[ -z "${seen_packages[$pkg]+x}" ]]; then
                seen_packages[$pkg]=1
                packages+=("$pkg")
            fi
        done < "$packages_file"
    done
    if [[ ${#packages[@]} -gt 0 ]]; then
        for pkg in "${packages[@]}"; do log_info "Installing: $pkg"; done
        # Set by install.sh before any step execution.
        # shellcheck disable=SC2154
        execute yay "${yay_install_args[@]}" -- "${packages[@]}" || die "Failed to install packages"
    fi
    progress_complete "done"
}

install_node() {
    progress_step "Installing Node.js version manager"
    if validate_file "$DOTFILES_DIR/install-node-manager.sh" false; then
        local -a node_args=()
        [[ "$NON_INTERACTIVE" != "true" ]] || node_args+=(--non-interactive)
        [[ "$DRY_RUN" != "true" ]] || node_args+=(--dry-run)
        execute bash "$DOTFILES_DIR/install-node-manager.sh" "${node_args[@]}" || die "Node.js version manager installation failed"
        progress_complete "done"
    else
        progress_complete "skipped"
        log_warn "install-node-manager.sh not found"
    fi
}

install_yubikey() {
    progress_step "Installing YubiKey tools"
    execute yay "${yay_install_args[@]}" -- yubikey-manager yubico-authenticator-bin pcsclite ccid || die "Failed to install YubiKey packages"
    # Set by install.sh before any step execution.
    # shellcheck disable=SC2154
    execute sudo "${sudo_args[@]}" systemctl enable pcscd.service || die "Failed to enable pcscd service"
    progress_complete "done"
}

validate_selected_shell_ready() {
    [[ -n "$SELECTED_SHELL" && "$DRY_RUN" != "true" ]] || return 0
    require_command "$SELECTED_SHELL" "Selected shell is not installed: $SELECTED_SHELL"
    if [[ "$SELECTED_SHELL" == zsh ]]; then
        [[ -r "$P10K_THEME_PATH" ]] || die "Powerlevel10k is required by the selected Zsh configuration"
    else
        require_command starship "Starship is required by the selected Bash configuration"
    fi
}

# Recognize only links whose lexical destination names the old package. The
# no-symlink-resolution mode matters because ghossty is now an alias to ghostty.
ghostty_legacy_link_matches() {
    local link=$1 expected=$2 target normalized
    [[ -L "$link" ]] || return 1
    target=$(readlink -- "$link") || return 1
    # GNU Stow does not own absolute links, even when they name this checkout.
    # Leave those intact for manual reconciliation instead of treating them as
    # a legacy package installation we can automatically unstow.
    [[ "$target" != /* ]] || return 1
    target="$(dirname -- "$link")/$target"
    normalized=$(realpath -ms -- "$target") || return 1
    [[ "$normalized" == "$DOTFILES_DIR/ghossty/$expected" ]]
}

ghostty_legacy_links_exist() {
    ghostty_legacy_link_matches "$HOME/.config" .config ||
        ghostty_legacy_link_matches "$HOME/.config/ghostty" .config/ghostty ||
        ghostty_legacy_link_matches "$HOME/.config/ghostty/config" .config/ghostty/config ||
        ghostty_legacy_link_matches "$HOME/.config/ghostty/theme" .config/ghostty/theme
}

stow_config_package() {
    local package=$1
    if [[ "$package" == ghostty ]] && ghostty_legacy_links_exist; then
        # One Stow invocation plans both actions and checks all conflicts before
        # executing either. Separate invocations could strand the old links.
        log_info "Migrating Stow-owned legacy ghossty links to ghostty..."
        execute stow --no-folding -d "$DOTFILES_DIR" -t "$HOME" -D ghossty -S ghostty
    else
        execute stow --no-folding -d "$DOTFILES_DIR" -t "$HOME" "$package"
    fi
}

install_stow() {
    progress_step "Setting up symlinks with GNU Stow"
    if [[ "$DRY_RUN" != true ]]; then require_command stow "stow is required but not installed"; fi
    local -a stow_packages=()
    local package shell_backup target
    case "$WINDOW_MANAGER" in
        awesome) stow_packages+=(awesome picom) ;;
        both) stow_packages+=(awesome hyprland picom) ;;
        hyprland) stow_packages+=(hyprland) ;;
        *) die "Invalid window manager: $WINDOW_MANAGER" ;;
    esac
    stow_packages+=("${COMMON_STOW_PACKAGES[@]}")
    [[ -z "$SELECTED_SHELL" ]] || stow_packages+=("$SELECTED_SHELL")
    # Stow merges directories and rejects conflicts without deleting user data.
    for package in "${stow_packages[@]}"; do
        if [[ -d "$DOTFILES_DIR/$package" ]]; then
            log_info "Stowing $package..."
            shell_backup=""
            if [[ "$package" == "$SELECTED_SHELL" ]]; then
                target="$HOME/.${SELECTED_SHELL}rc"
                if [[ -f "$target" && ! -L "$target" ]]; then
                    backup_item "$target" || die "Could not back up $target"
                    if [[ "$DRY_RUN" != true ]]; then shell_backup="${BACKUPS[-1]}"; fi
                    execute rm -f -- "$target" || die "Could not remove $target"
                fi
            fi
            # Never fold ~/.local into the checkout: apps write state there.
            if ! stow_config_package "$package"; then
                if [[ -n "$shell_backup" ]]; then
                    restore_backup "$shell_backup" "$target" || log_error "Restore failed; original config is at $shell_backup"
                fi
                die "Failed to stow $package; reconcile the reported conflicts and rerun"
            fi
        else
            die "$package directory not found"
        fi
    done
    # Generate plugin wiring first, then render colors so Stow links are usable.
    execute "$DOTFILES_DIR/plugins/pluginctl" refresh || log_warn "pluginctl refresh failed; run it manually"
    execute "$DOTFILES_DIR/themes/themectl" apply || log_warn "themectl apply failed; run it manually"
    execute "$DOTFILES_DIR/scripts/.local/bin/gtk-bookmarks" || log_warn "gtk-bookmarks failed; run it manually"
    progress_complete "done"
}

install_theme() {
    progress_step "Applying system theme"
    # Palette and Awesome layout are independent; this step only sets colors.
    execute "$DOTFILES_DIR/themes/themectl" set --colors "${DOTFILES_THEME:-mocha-peach}" || die "Failed to apply theme"
    progress_complete "done"
}

install_backgrounds() {
    progress_step "Setting up desktop backgrounds"
    if [[ -d "$DOTFILES_DIR/backgrounds" ]]; then
        safe_symlink "$DOTFILES_DIR/backgrounds" "$HOME/.backgrounds" || die "Failed to link backgrounds"
        progress_complete "done"
    else
        progress_complete "skipped"
        log_warn "Backgrounds directory not found"
    fi
}

install_tmux() {
    progress_step "Setting up Tmux configuration"
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[dry-run] Would link tmux config and theme into ~/.config/tmux and ~/.tmux.conf"
        progress_complete "done"
        return
    fi
    mkdir -p "$XDG_CONFIG_HOME/tmux"
    local tpm_dir="$HOME/.tmux/plugins/tpm" tmux_conf="$DOTFILES_DIR/config/tmux/tmux.conf"
    local tmux_helper agent_bin="" agent_dir
    if [[ ! -x "$tpm_dir/tpm" ]]; then
        execute git clone --depth 1 -- https://github.com/tmux-plugins/tpm "$tpm_dir" || die "Failed to install TPM"
    fi
    [[ -x "$tpm_dir/tpm" ]] || die "TPM installation did not produce an executable plugin manager"
    if validate_file "$tmux_conf" false; then
        safe_symlink "$tmux_conf" "$XDG_CONFIG_HOME/tmux/tmux.conf" || die "Failed to symlink tmux.conf"
    else
        die "Tmux configuration not found"
    fi
    # Keep the tracked icon theme; safe_symlink backs up prior files or links.
    safe_symlink "$DOTFILES_DIR/config/tmux/theme.conf" "$XDG_CONFIG_HOME/tmux/theme.conf" || die "Failed to link tmux theme"
    mkdir -p "$HOME/.local/bin"
    # Standalone tmux installs also need persistence. Relative links remain
    # compatible with a later installation of the scripts Stow package.
    tmux_helper=$(realpath --relative-to="$HOME/.local/bin" "$DOTFILES_DIR/scripts/.local/bin/tmux-save-workspace") || die "Failed to locate tmux persistence helper"
    safe_symlink "$tmux_helper" "$HOME/.local/bin/tmux-save-workspace" || die "Failed to link tmux persistence helper"
    safe_symlink "$XDG_CONFIG_HOME/tmux/tmux.conf" "$HOME/.tmux.conf" || die "Failed to symlink tmux config"
    if [[ -x "$tpm_dir/bin/install_plugins" ]]; then "$tpm_dir/bin/install_plugins" || die "Failed to install tmux plugins"; fi
    for agent_dir in "$XDG_CONFIG_HOME/tmux/plugins" "$HOME/.tmux/plugins"; do
        if [[ -x "$agent_dir/tmux-agentic-plugin/bin/tmux-agent" ]]; then
            agent_bin="$agent_dir/tmux-agentic-plugin/bin/tmux-agent"; break
        fi
    done
    if [[ -z "$agent_bin" ]]; then
        [[ "$DRY_RUN" == true ]] || log_warn "tmux-agentic-plugin not installed; run prefix + I in tmux, then its bin/tmux-agent install-hooks"
    elif command_exists jq; then
        execute "$agent_bin" install-hooks || log_warn "Failed to install tmux-agent hooks"
    fi
    progress_complete "done"
}

install_shell() {
    [[ -n "$SELECTED_SHELL" ]] || return 0
    local selected_shell_path="" escaped_shell_path terminal_config target setting_pattern current_settings replacement current_setting has_shell_change
    if selected_shell_path=$(command -v "$SELECTED_SHELL" 2>/dev/null); then
        selected_shell_path=$(readlink -f -- "$selected_shell_path") || die "Could not resolve selected shell: $SELECTED_SHELL"
    elif [[ "$DRY_RUN" == true ]]; then
        selected_shell_path="$DRY_RUN_SHELL_PATH_PREFIX/$SELECTED_SHELL"
    else
        die "Selected shell is not installed: $SELECTED_SHELL"
    fi
    escaped_shell_path=${selected_shell_path//\\/\\\\}
    escaped_shell_path=${escaped_shell_path//&/\\&}
    escaped_shell_path=${escaped_shell_path//|/\\|}
    # Edit resolved targets rather than replacing Stow links; skip unchanged
    # settings so reruns do not accumulate unnecessary backups.
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
                if [[ "$current_setting" != "$selected_shell_path" ]]; then has_shell_change=true; break; fi
            done <<< "$current_settings"
            [[ "$has_shell_change" == true ]] || continue
            if [[ "$DRY_RUN" == true ]]; then
                log_info "[dry-run] Would update $terminal_config to use $SELECTED_SHELL"
            else
                backup_item "$target" || die "Failed to back up $terminal_config"
                sed -i -E "s|$setting_pattern|$replacement|" "$target"
            fi
        fi
    done
    set_login_shell "$SELECTED_SHELL" || die "Failed to set the login shell to $SELECTED_SHELL"
}

install_lazyvim() {
    progress_step "Installing LazyVim Neovim distribution"
    if [[ -d "$DOTFILES_DIR/nvim" ]] && command_exists nvim; then
        if validate_file "$DOTFILES_DIR/install-lazyvim.sh" false; then
            local -a lazyvim_args=()
            [[ "$NON_INTERACTIVE" != "true" ]] || lazyvim_args+=(--non-interactive)
            [[ "$DRY_RUN" != "true" ]] || lazyvim_args+=(--dry-run)
            execute bash "$DOTFILES_DIR/install-lazyvim.sh" "${lazyvim_args[@]}" || die "LazyVim installation failed"
            progress_complete "done"
        else
            progress_complete "skipped"
        fi
    else
        progress_complete "skipped"
        log_warn "Neovim not installed or nvim directory not found"
    fi
}

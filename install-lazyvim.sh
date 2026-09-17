#!/bin/bash
# Preserve managed Neovim configuration; stage replacements before backing up.
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOTFILES_DIR
source "$DOTFILES_DIR/lib/logging.sh"
source "$DOTFILES_DIR/lib/cleanup.sh"

DRY_RUN=false
NON_INTERACTIVE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --non-interactive|-y) NON_INTERACTIVE=true ;;
        --help|-h)
            printf 'Usage: %s [--dry-run] [--non-interactive]\n' "$0"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
    shift
done

export NVIM_APPNAME="${NVIM_APPNAME:-nvim}"
[[ "$NVIM_APPNAME" != */* && "$NVIM_APPNAME" != . && "$NVIM_APPNAME" != .. ]] || die "NVIM_APPNAME must be a single directory name"
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
[[ "$XDG_CONFIG_HOME" == /* ]] || die "XDG_CONFIG_HOME must be an absolute path"
NVIM_CONFIG_DIR="$XDG_CONFIG_HOME/$NVIM_APPNAME"
managed=false
if [[ -d "$NVIM_CONFIG_DIR" && ( "$NVIM_CONFIG_DIR" -ef "$DOTFILES_DIR/nvim/.config/nvim" ||
    ( "$NVIM_CONFIG_DIR/init.lua" -ef "$DOTFILES_DIR/nvim/.config/nvim/init.lua" &&
      "$NVIM_CONFIG_DIR/lua" -ef "$DOTFILES_DIR/nvim/.config/nvim/lua" ) ) ]]; then
    managed=true
fi

if [[ "$managed" == true ]]; then
    log_info "Preserving repository-managed configuration at $NVIM_CONFIG_DIR; syncing plugins only."
elif [[ -e "$NVIM_CONFIG_DIR" || -L "$NVIM_CONFIG_DIR" ]]; then
    # Never sever a Stow or other user-managed link to install the starter.
    if [[ -L "$NVIM_CONFIG_DIR" || "$NON_INTERACTIVE" == true || "$DRY_RUN" == true || ! -t 0 ]]; then
        log_info "Keeping existing configuration at $NVIM_CONFIG_DIR; skipping LazyVim installation."
        exit 0
    fi
    response=""
    read -r -p "Replace $NVIM_CONFIG_DIR with LazyVim starter after backing it up? [y/N] " response || response=n
    if [[ "$response" != y && "$response" != Y ]]; then
        log_info "Keeping existing configuration; skipping LazyVim installation."
        exit 0
    fi
fi

if [[ "$DRY_RUN" == true ]]; then
    if [[ "$managed" != true ]]; then
        log_info "[dry-run] Would stage LazyVim starter and install at $NVIM_CONFIG_DIR."
    fi
    log_info "[dry-run] Would run nvim --headless '+Lazy! sync' +qa (NVIM_APPNAME=$NVIM_APPNAME)."
    exit 0
fi
require_command nvim "Neovim is required. Install it before running this helper."
require_command git

backup_dir=""
replacement_pending=false
finish_install() {
    local status=$?
    if [[ "$replacement_pending" == true ]]; then
        log_warn "LazyVim installation failed; restoring the previous configuration."
        if rm -rf -- "$NVIM_CONFIG_DIR" && mv -- "$backup_dir/config" "$NVIM_CONFIG_DIR"; then
            log_info "Previous configuration restored."
        else
            log_error "Rollback failed. Your original configuration is at $backup_dir/config"
        fi
        status=1
    fi
    cleanup_temp_dirs
    exit "$status"
}
trap finish_install EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ "$managed" != true ]]; then
    create_temp_dir lazyvim-install temp_dir || die "Failed to create LazyVim staging directory"
    git clone --depth 1 -- https://github.com/LazyVim/starter "$temp_dir/starter" || die "Failed to clone LazyVim starter; existing configuration untouched"
    [[ -f "$temp_dir/starter/init.lua" ]] || die "Staged LazyVim starter has no init.lua"
    rm -rf -- "$temp_dir/starter/.git" || die "Failed to clean staged repository"
    mkdir -p -- "$XDG_CONFIG_HOME" || die "Failed to create configuration parent"
    if [[ -e "$NVIM_CONFIG_DIR" || -L "$NVIM_CONFIG_DIR" ]]; then
        backup_dir=$(mktemp -d "$NVIM_CONFIG_DIR.backup.XXXXXXXX") || die "Failed to create mandatory backup directory"
        mv -- "$NVIM_CONFIG_DIR" "$backup_dir/config" || die "Failed to back up configuration; replacement aborted"
        replacement_pending=true
        log_info "Original configuration backed up to $backup_dir/config"
    fi
    mv -T -- "$temp_dir/starter" "$NVIM_CONFIG_DIR" || die "Failed to install staged LazyVim configuration"
fi

nvim --headless '+Lazy! sync' +qa || die "LazyVim plugin synchronization failed"
replacement_pending=false
log_success "LazyVim plugins synchronized at $NVIM_CONFIG_DIR"

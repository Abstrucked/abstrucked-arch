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
NVIM_SOURCE_DIR="$DOTFILES_DIR/nvim/.config/nvim"
NVIM_CONFIG_DIR="$XDG_CONFIG_HOME/$NVIM_APPNAME"

# Do not let a symlinked parent redirect a staged replacement into an
# unexpected tree. The target itself may still be a symlink; it is preserved
# or skipped below rather than followed for replacement.
path_has_symlink_component() {
    local path=$1
    local current=/ component
    local -a components=()

    IFS=/ read -r -a components <<< "${path#/}"
    for component in "${components[@]}"; do
        [[ -z "$component" || "$component" == . ]] && continue
        if [[ "$component" == .. ]]; then
            current=$(dirname -- "$current")
        else
            current="$current/$component"
        fi
        [[ -L "$current" ]] && return 0
        [[ -e "$current" && ! -d "$current" ]] && return 0
    done
    return 1
}

path_has_symlink_component "$XDG_CONFIG_HOME" &&
    die "Refusing to use XDG_CONFIG_HOME with a symlinked or non-directory parent: $XDG_CONFIG_HOME"

# Stow can represent one package as a directory link, or as real directories
# containing a link for every file. Compare the complete tree so both forms
# are recognized without mistaking a partially managed config for ownership.
tree_is_managed() {
    local source=$1 target=$2
    local source_child target_child name
    local -a source_children=() target_children=()

    [[ -e "$target" || -L "$target" ]] || return 1
    [[ "$target" -ef "$source" ]] && return 0
    [[ -d "$source" && -d "$target" ]] || return 1

    shopt -s nullglob dotglob
    source_children=("$source"/*)
    target_children=("$target"/*)
    shopt -u nullglob dotglob

    ((${#source_children[@]} == ${#target_children[@]})) || return 1
    for source_child in "${source_children[@]}"; do
        name=${source_child##*/}
        target_child="$target/$name"
        [[ -e "$target_child" || -L "$target_child" ]] || return 1
        tree_is_managed "$source_child" "$target_child" || return 1
    done
}

managed=false
if tree_is_managed "$NVIM_SOURCE_DIR" "$NVIM_CONFIG_DIR"; then
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
    log_info "[dry-run] Would run nvim headless Lazy.sync and verify plugin tasks (NVIM_APPNAME=$NVIM_APPNAME)."
    exit 0
fi
require_command nvim "Neovim is required. Install it before running this helper."
require_command git

backup_dir=""
replacement_pending=false
fresh_install_pending=false

# Keep rollback material away from the repository and its package tree even
# when TMPDIR was configured inside the checkout.
create_external_temp_dir() {
    local prefix=$1 output=$2 root root_real repo_real
    local -a roots=()

    [[ -n "${TMPDIR:-}" ]] && roots+=("$TMPDIR")
    roots+=("/tmp")
    [[ -n "${XDG_CACHE_HOME:-}" ]] && roots+=("$XDG_CACHE_HOME")
    roots+=("$HOME")
    repo_real=$(realpath -e -- "$DOTFILES_DIR") || return 1

    for root in "${roots[@]}"; do
        [[ -d "$root" ]] || continue
        root_real=$(realpath -e -- "$root") || continue
        [[ "$root_real" == "$repo_real" || "$root_real" == "$repo_real/"* ]] && continue
        local created
        created=$(mktemp -d "$root_real/$prefix.XXXXXXXX") || continue
        printf -v "$output" '%s' "$created"
        return 0
    done
    return 1
}

quarantine_failed_install() {
    local quarantine_dir
    if [[ ! -e "$NVIM_CONFIG_DIR" && ! -L "$NVIM_CONFIG_DIR" ]]; then
        log_warn "Failed LazyVim installation left no configuration to quarantine; retry is safe."
        return 0
    fi
    if ! create_external_temp_dir lazyvim-failed quarantine_dir; then
        log_error "Could not create an external quarantine directory; leaving failed configuration at $NVIM_CONFIG_DIR"
        return 1
    fi
    if mv -T -- "$NVIM_CONFIG_DIR" "$quarantine_dir/config"; then
        log_warn "Failed LazyVim installation quarantined at $quarantine_dir/config; retry is safe."
        return 0
    fi
    log_error "Could not quarantine failed configuration; leaving it at $NVIM_CONFIG_DIR"
    return 1
}

restore_previous_config() {
    local quarantine_dir
    if [[ ! -e "$NVIM_CONFIG_DIR" && ! -L "$NVIM_CONFIG_DIR" ]]; then
        mv -T -- "$backup_dir/config" "$NVIM_CONFIG_DIR" && return 0
        return 1
    fi
    if ! create_external_temp_dir lazyvim-failed quarantine_dir; then
        log_error "Could not create an external quarantine directory; original configuration remains at $backup_dir/config"
        return 1
    fi
    if ! mv -T -- "$NVIM_CONFIG_DIR" "$quarantine_dir/replacement"; then
        log_error "Could not move failed replacement aside; original configuration remains at $backup_dir/config"
        return 1
    fi
    if mv -T -- "$backup_dir/config" "$NVIM_CONFIG_DIR"; then
        log_info "Previous configuration restored; failed replacement is at $quarantine_dir/replacement"
        return 0
    fi
    log_error "Rollback failed. Original configuration is at $backup_dir/config and failed replacement is at $quarantine_dir/replacement"
    return 1
}

finish_install() {
    local status=$?
    if [[ "$status" -ne 0 && "$replacement_pending" == true ]]; then
        log_warn "LazyVim installation failed; restoring the previous configuration."
        if restore_previous_config; then
            log_info "Previous configuration restored."
        fi
        status=1
    elif [[ "$status" -ne 0 && "$fresh_install_pending" == true ]]; then
        log_warn "LazyVim installation failed; quarantining the fresh configuration so a retry is safe."
        quarantine_failed_install || true
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
    path_has_symlink_component "$XDG_CONFIG_HOME" &&
        die "Configuration parent changed to a symlink during installation; replacement aborted"
    if [[ -e "$NVIM_CONFIG_DIR" || -L "$NVIM_CONFIG_DIR" ]]; then
        create_external_temp_dir lazyvim-backup backup_dir ||
            die "Failed to create an external backup directory"
        mv -- "$NVIM_CONFIG_DIR" "$backup_dir/config" || die "Failed to back up configuration; replacement aborted"
        replacement_pending=true
        log_info "Original configuration backed up to $backup_dir/config"
    fi
    mv -T -- "$temp_dir/starter" "$NVIM_CONFIG_DIR" || die "Failed to install staged LazyVim configuration"
    fresh_install_pending=true
fi

if ! nvim --headless "+lua local function fail(message) vim.api.nvim_err_writeln(message); vim.cmd('cquit 1') end; local ok, lazy_or_error = pcall(require, 'lazy'); if not ok then fail('Could not load lazy.nvim: ' .. tostring(lazy_or_error)); return end; local synced, sync_error = xpcall(function() lazy_or_error.sync({ wait = true, show = false }) end, debug.traceback); if not synced then fail('Lazy.nvim sync failed: ' .. tostring(sync_error)); return end; local config = require('lazy.core.config'); local plugin = require('lazy.core.plugin'); local failures = {}; if config.spec and config.spec.notifs then for _, notification in ipairs(config.spec.notifs) do if notification.level >= vim.log.levels.ERROR then table.insert(failures, 'plugin spec: ' .. notification.msg) end end end; for name, item in pairs(config.plugins or {}) do if plugin.has_errors(item) then table.insert(failures, 'plugin task: ' .. name) end end; if #failures > 0 then for _, message in ipairs(failures) do vim.api.nvim_err_writeln(message) end; vim.cmd('cquit 1') end" +qa; then
    die "LazyVim plugin synchronization failed"
fi
replacement_pending=false
fresh_install_pending=false
log_success "LazyVim plugins synchronized at $NVIM_CONFIG_DIR"

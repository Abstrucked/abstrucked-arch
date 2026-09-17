#!/bin/bash
# Cleanup and backup helper functions

# Prevent multiple sourcing
if [[ -n "${_CLEANUP_SH_LOADED:-}" ]]; then
    return 0
fi
_CLEANUP_SH_LOADED=1

# Source logging functions
source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

# Array to track created temp directories
TEMP_DIRS=()

# Array to track backups
BACKUPS=()

# Call in the current shell: create_temp_dir PREFIX OUTPUT_VAR (not $(...)).
create_temp_dir() {
    local _temp_prefix=${1:-dotfiles}
    local _temp_output=${2:-}
    local _temp_path
    if [[ ! "$_temp_output" =~ ^[a-zA-Z_][a-zA-Z0-9_]*$ || "$_temp_output" == _temp_* || "$_temp_output" == TEMP_DIRS ]]; then
        log_error "create_temp_dir requires a writable output variable name"
        return 1
    fi
    if [[ "$_temp_prefix" == */* ]]; then
        log_error "Temp directory prefix must not contain /"
        return 1
    fi
    printf -v "$_temp_output" '%s' '' || return 1
    if [[ "${DRY_RUN:-false}" == true ]]; then
        log_info "[dry-run] Would create temporary directory ($_temp_prefix)"
        return 0
    fi
    _temp_path=$(mktemp -d "${TMPDIR:-/tmp}/${_temp_prefix}.XXXXXXXX") || {
        log_error "Failed to create temp directory"
        return 1
    }
    
    TEMP_DIRS+=("$_temp_path")
    printf -v "$_temp_output" '%s' "$_temp_path"
}

# Clean up all tracked temp directories
cleanup_temp_dirs() {
    local dirs_cleaned=0
    local dir
    if [[ "${DRY_RUN:-false}" == true ]]; then
        log_info "[dry-run] Would clean up tracked temporary directories"
        return 0
    fi

    for dir in "${TEMP_DIRS[@]+"${TEMP_DIRS[@]}"}"; do
        if [[ -d "$dir" ]]; then
            rm -rf -- "$dir" || {
                log_error "Failed to remove temporary directory: $dir"
                return 1
            }
            dirs_cleaned=$((dirs_cleaned + 1))
        fi
    done

    TEMP_DIRS=()

    if [[ $dirs_cleaned -gt 0 ]]; then
        log_debug "Cleaned up $dirs_cleaned temp director$([ $dirs_cleaned -eq 1 ] && echo 'y' || echo 'ies')"
    fi
}

# Backup a file or directory before modification
backup_item() {
    local item=$1
    local backup_dir=${2:-"$HOME/.dotfiles-backups"}

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "[dry-run] Would back up $item"
        return 0
    fi

    if [[ ! -e "$item" ]] && [[ ! -L "$item" ]]; then
        log_debug "Nothing to backup: $item"
        return 0
    fi

    mkdir -p -- "$backup_dir" || {
        log_error "Failed to create backup directory: $backup_dir"
        return 1
    }

    # Normalize dot segments without following symlinks, preserving the source name.
    local lexical_path backup_root backup_path
    lexical_path=$(realpath -ms -- "$item") || return 1
    backup_root=$(mktemp -d "$backup_dir/backup.XXXXXXXX") || {
        log_error "Failed to create unique backup directory: $backup_dir"
        return 1
    }
    backup_path="$backup_root$lexical_path"
    local backup_parent
    backup_parent=$(dirname -- "$backup_path") || return 1
    mkdir -p -- "$backup_parent" || {
        log_error "Failed to create backup parent: $backup_parent"
        return 1
    }

    cp -a -- "$item" "$backup_path" || {
        log_error "Failed to backup: $item"
        return 1
    }

    BACKUPS+=("$backup_path")
    log_debug "Backed up: $item"
    return 0
}

# Restore a backup
restore_backup() {
    local backup_path=$1
    local restore_path=$2
    
    if [[ ! -e "$backup_path" && ! -L "$backup_path" ]]; then
        log_error "Backup not found: $backup_path"
        return 1
    fi
    
    if [[ "${DRY_RUN:-false}" == true ]]; then
        log_info "[dry-run] Would restore $backup_path to $restore_path"
        return 0
    fi
    local parent_dir
    parent_dir=$(dirname -- "$restore_path") || return 1
    mkdir -p -- "$parent_dir" || {
        log_error "Failed to create restore parent: $parent_dir"
        return 1
    }
    # Preserve the current item before replacing it, including dangling symlinks.
    if [[ -e "$restore_path" || -L "$restore_path" ]]; then
        backup_item "$restore_path" || return 1
        rm -rf -- "$restore_path" || {
            log_error "Failed to remove restore destination: $restore_path"
            return 1
        }
    fi
    
    # Restore from backup
    cp -a -- "$backup_path" "$restore_path" || {
        log_error "Failed to restore: $restore_path"
        return 1
    }
    
    log_info "Restored: $restore_path"
    return 0
}

# List all backups
list_backups() {
    if [[ ${#BACKUPS[@]} -eq 0 ]]; then
        log_info "No backups in current session"
        return 0
    fi
    
    log_info "Backups created in this session:"
    for backup in "${BACKUPS[@]}"; do
        echo "  $backup"
    done
}

# Cleanup on script exit
cleanup_on_exit() {
    local exit_code=$?
    if [[ $SPINNER_PID -ne 0 ]]; then
        spinner_stop
    fi
    cleanup_temp_dirs || log_error "Temporary directory cleanup failed"
    
    if [[ $exit_code -ne 0 ]] && [[ ${#BACKUPS[@]} -gt 0 ]]; then
        log_warn "Script exited with errors. Backups available in:"
        list_backups
    fi
    
    return $exit_code
}

# Set up trap for cleanup on exit
setup_cleanup_trap() {
    trap cleanup_on_exit EXIT
}

# Safely remove a directory with backup
safe_remove_dir() {
    local dir=$1
    local backup=${2:-true}

    if [[ ! -d "$dir" && ! -L "$dir" ]]; then
        return 0
    fi

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "[dry-run] Would remove directory $dir"
        return 0
    fi

    if [[ "$backup" == "true" ]]; then
        backup_item "$dir" || return 1
    fi

    rm -rf -- "$dir" || {
        log_error "Failed to remove directory: $dir"
        return 1
    }

    log_debug "Removed directory: $dir"
    return 0
}

# Safely remove a file with backup
safe_remove_file() {
    local file=$1
    local backup=${2:-true}

    if [[ ! -f "$file" ]] && [[ ! -L "$file" ]]; then
        return 0
    fi

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "[dry-run] Would remove file $file"
        return 0
    fi

    if [[ "$backup" == "true" ]]; then
        backup_item "$file" || return 1
    fi

    rm -f -- "$file" || {
        log_error "Failed to remove file: $file"
        return 1
    }

    log_debug "Removed file: $file"
    return 0
}

# Safely create a symlink
safe_symlink() {
    local target=$1
    local link_name=$2
    local backup=${3:-true}
    local parent_dir target_path
    parent_dir=$(dirname -- "$link_name") || return 1
    target_path=$target
    [[ "$target" == /* ]] || target_path="$parent_dir/$target"

    if [[ -L "$link_name" && "$(readlink -- "$link_name")" == "$target" ]]; then
        return 0
    fi

    if [[ ! -e "$target_path" ]] && [[ ! -L "$target_path" ]]; then
        log_error "Symlink target does not exist: $target"
        return 1
    fi

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "[dry-run] Would link $link_name -> $target"
        return 0
    fi

    mkdir -p -- "$parent_dir" || {
        log_error "Failed to create symlink parent: $parent_dir"
        return 1
    }
    # Backup existing symlink or file
    if [[ -L "$link_name" ]] || [[ -e "$link_name" ]]; then
        if [[ "$backup" == "true" ]]; then
            backup_item "$link_name" || return 1
        fi
        rm -rf -- "$link_name" || {
            log_error "Failed to remove symlink destination: $link_name"
            return 1
        }
    fi

    # Create symlink
    ln -s -- "$target" "$link_name" || {
        log_error "Failed to create symlink: $link_name -> $target"
        return 1
    }

    log_debug "Created symlink: $link_name -> $target"
    return 0
}

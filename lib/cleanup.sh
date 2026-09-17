#!/bin/bash
# Cleanup and backup helper functions

# Prevent multiple sourcing
if [[ -n "${_CLEANUP_SH_LOADED:-}" ]]; then
    return 0
fi
_CLEANUP_SH_LOADED=1

# Source logging functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"

# Array to track created temp directories
TEMP_DIRS=()

# Array to track backups
BACKUPS=()

# Create a temp directory and track it for cleanup
create_temp_dir() {
    local prefix=${1:-dotfiles}
    local temp_dir
    
    temp_dir=$(mktemp -d "${TMPDIR:-/tmp}/${prefix}.XXXXXXXX") || {
        log_error "Failed to create temp directory"
        return 1
    }
    
    TEMP_DIRS+=("$temp_dir")
    echo "$temp_dir"
}

# Clean up all tracked temp directories
cleanup_temp_dirs() {
    local dirs_cleaned=0
    
    for dir in "${TEMP_DIRS[@]}"; do
        if [[ -d "$dir" ]]; then
            rm -rf "$dir"
            ((dirs_cleaned++))
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
    local backup_dir=${2:-"$HOME/.dotfiles-backups/$(date +%Y%m%d_%H%M%S)"}
    
    if [[ ! -e "$item" ]]; then
        log_debug "Nothing to backup: $item"
        return 0
    fi
    
    # Create backup directory if it doesn't exist
    mkdir -p "$backup_dir" || {
        log_error "Failed to create backup directory: $backup_dir"
        return 1
    }
    
    # Create backup with relative path preserved
    local backup_path="$backup_dir$(readlink -f "$item")"
    local backup_parent
    backup_parent=$(dirname "$backup_path")
    mkdir -p "$backup_parent"
    
    cp -a "$item" "$backup_path" || {
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
    
    if [[ ! -e "$backup_path" ]]; then
        log_error "Backup not found: $backup_path"
        return 1
    fi
    
    # Remove current item if it exists
    if [[ -e "$restore_path" ]]; then
        rm -rf "$restore_path"
    fi
    
    # Restore from backup
    cp -a "$backup_path" "$restore_path" || {
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
    
    cleanup_temp_dirs
    
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
    
    if [[ ! -d "$dir" ]]; then
        return 0
    fi
    
    if [[ "$backup" == "true" ]]; then
        backup_item "$dir" || return 1
    fi
    
    rm -rf "$dir" || {
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
    
    if [[ ! -f "$file" ]]; then
        return 0
    fi
    
    if [[ "$backup" == "true" ]]; then
        backup_item "$file" || return 1
    fi
    
    rm -f "$file" || {
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
    
    # Check target exists
    if [[ ! -e "$target" ]]; then
        log_error "Symlink target does not exist: $target"
        return 1
    fi
    
    # Backup existing symlink or file
    if [[ -L "$link_name" ]] || [[ -e "$link_name" ]]; then
        if [[ "$backup" == "true" ]]; then
            backup_item "$link_name" || return 1
        fi
        rm -rf "$link_name"
    fi
    
    # Create parent directory if needed
    local parent_dir
    parent_dir=$(dirname "$link_name")
    mkdir -p "$parent_dir"
    
    # Create symlink
    ln -sf "$target" "$link_name" || {
        log_error "Failed to create symlink: $link_name -> $target"
        return 1
    }
    
    log_debug "Created symlink: $link_name -> $target"
    return 0
}
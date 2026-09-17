#!/bin/bash
# Validation and prerequisite checking functions

# Prevent multiple sourcing
if [[ -n "${_VALIDATION_SH_LOADED:-}" ]]; then
    return 0
fi
_VALIDATION_SH_LOADED=1

# Source logging functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"

# Validate that we're on Arch Linux
require_arch() {
    if ! command_exists pacman; then
        die "This script is designed for Arch Linux systems"
    fi
}

# Validate that running as non-root (or allow root with flag)
require_non_root() {
    if [[ $EUID -eq 0 ]] && [[ "${ALLOW_ROOT:-}" != "true" ]]; then
        die "Do not run this script as root. Set ALLOW_ROOT=true to override."
    fi
}

# Validate a package name (alphanumeric, hyphens, underscores, dots)
validate_package_name() {
    local pkg=$1
    
    if [[ -z "$pkg" ]]; then
        log_error "Package name cannot be empty"
        return 1
    fi
    
    if [[ ! "$pkg" =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ ]]; then
        log_error "Invalid package name: $pkg"
        return 1
    fi
    
    return 0
}

# Validate a list of packages from a file
validate_packages_file() {
    local file=$1
    
    if [[ ! -f "$file" ]]; then
        die "Packages file not found: $file"
    fi
    
    local invalid_packages=()
    while IFS= read -r line; do
        # Skip empty lines and comments
        [[ -z "$line" || "$line" =~ ^# ]] && continue
        
        if ! validate_package_name "$line"; then
            invalid_packages+=("$line")
        fi
    done < "$file"
    
    if [[ ${#invalid_packages[@]} -gt 0 ]]; then
        log_error "Invalid package names found:"
        printf '  %s\n' "${invalid_packages[@]}"
        return 1
    fi
    
    return 0
}

# Validate that required tools are installed
validate_prerequisites() {
    local tools=("$@")
    local missing=()
    
    for tool in "${tools[@]}"; do
        if ! command_exists "$tool"; then
            missing+=("$tool")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing required tools:"
        printf '  %s\n' "${missing[@]}"
        return 1
    fi
    
    return 0
}

# Validate a directory exists and is writable
validate_directory() {
    local dir=$1
    local create=${2:-false}
    
    if [[ ! -d "$dir" ]]; then
        if [[ "$create" == "true" ]]; then
            mkdir -p "$dir" || {
                log_error "Failed to create directory: $dir"
                return 1
            }
        else
            log_error "Directory does not exist: $dir"
            return 1
        fi
    fi
    
    if [[ ! -w "$dir" ]]; then
        log_error "Directory is not writable: $dir"
        return 1
    fi
    
    return 0
}

# Validate a file exists and is readable
validate_file() {
    local file=$1
    local required=${2:-true}
    
    if [[ ! -f "$file" ]]; then
        if [[ "$required" == "true" ]]; then
            log_error "Required file not found: $file"
            return 1
        else
            log_warn "Optional file not found: $file"
            return 1
        fi
    fi
    
    if [[ ! -r "$file" ]]; then
        log_error "File is not readable: $file"
        return 1
    fi
    
    return 0
}

# Validate a URL format
validate_url() {
    local url=$1
    
    if [[ ! "$url" =~ ^https?:// ]]; then
        log_error "Invalid URL format: $url"
        return 1
    fi
    
    return 0
}

# Validate that a variable is set
validate_variable() {
    local var_name=$1
    local var_value=$2
    
    if [[ -z "$var_value" ]]; then
        log_error "Required variable not set: $var_name"
        return 1
    fi
    
    return 0
}

# Validate theme variables are set
validate_theme_variables() {
    local missing=()
    local theme_vars=(
        "PRIMARY_BACKGROUND" "PRIMARY_FOREGROUND" "PRIMARY_DIM_FOREGROUND" "PRIMARY_BRIGHT_FOREGROUND"
        "CURSOR_TEXT" "CURSOR_CURSOR"
        "VI_MODE_CURSOR_TEXT" "VI_MODE_CURSOR_CURSOR"
        "SEARCH_MATCHES_FOREGROUND" "SEARCH_MATCHES_BACKGROUND"
        "SEARCH_FOCUSED_MATCH_FOREGROUND" "SEARCH_FOCUSED_MATCH_BACKGROUND"
        "FOOTER_BAR_FOREGROUND" "FOOTER_BAR_BACKGROUND"
        "HINTS_START_FOREGROUND" "HINTS_START_BACKGROUND"
        "HINTS_END_FOREGROUND" "HINTS_END_BACKGROUND"
        "SELECTION_TEXT" "SELECTION_BACKGROUND"
        "NORMAL_BLACK" "NORMAL_RED" "NORMAL_GREEN" "NORMAL_YELLOW"
        "NORMAL_BLUE" "NORMAL_MAGENTA" "NORMAL_CYAN" "NORMAL_WHITE"
        "BRIGHT_BLACK" "BRIGHT_RED" "BRIGHT_GREEN" "BRIGHT_YELLOW"
        "BRIGHT_BLUE" "BRIGHT_MAGENTA" "BRIGHT_CYAN" "BRIGHT_WHITE"
        "INDEXED_16" "INDEXED_17"
    )
    
    for var in "${theme_vars[@]}"; do
        if [[ -z "${!var:-}" ]]; then
            missing+=("$var")
        fi
    done
    
    if [[ ${#missing[@]} -gt 0 ]]; then
        log_error "Missing theme variables:"
        printf '  %s\n' "${missing[@]}"
        return 1
    fi
    
    return 0
}
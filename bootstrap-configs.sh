#!/bin/bash
# Bootstrap script to copy existing configurations from ~/.config to dotfiles structure
# This is a run-once script to help set up the dotfiles folder with existing configs

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration mappings
declare -A CONFIG_MAPPINGS=(
    ["alacritty"]="alacritty/.config/alacritty"
    ["awesome"]="awesome/.config/awesome"
    ["btop"]="btop/.config/btop"
    ["nvim"]="nvim/.config/nvim"
    ["picom"]="picom/.config/picom"
    ["pcmanfm"]="pcmanfm/.config/pcmanfm"
    ["brave"]="brave/.config/BraveSoftware/Brave-Browser"
    ["discord"]="discord/.config/discord"
    ["obs-studio"]="obs-studio/.config/obs-studio"
    ["qbittorrent"]="qbittorrent/.config/qBittorrent"
    ["vlc"]="vlc/.config/vlc"
)

# Home directory dotfiles
declare -A HOME_MAPPINGS=(
    [".zshrc"]="zsh/.zshrc"
    [".p10k.zsh"]="zsh/.p10k.zsh"
    [".tmux.conf"]="tmux/.tmux.conf"
    ["load-api-keys.sh"]="scripts/load-api-keys.sh"
)

# SSH config
SSH_CONFIG_SOURCE="$HOME/.ssh/config"
SSH_CONFIG_DEST="ssh/.ssh/config"

# Script variables
DRY_RUN=false
AUTO_YES=false
FORCE_SENSITIVE=false
COPIED_COUNT=0
SKIPPED_COUNT=0
SKIPPED_SENSITIVE_COUNT=0

# Functions
print_header() {
    echo -e "${BLUE}🔧 Dotfiles Bootstrap Script${NC}"
    echo -e "${BLUE}===============================${NC}"
    echo -e "${CYAN}This script helps copy your existing configurations to the dotfiles structure.${NC}"
    echo ""
}

print_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --dry-run           Show what would be copied without making changes"
    echo "  --yes               Automatically answer 'yes' to all prompts (dangerous!)"
    echo "  --force-sensitive   Copy configs even if they contain sensitive files (dangerous!)"
    echo "  --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                      # Interactive mode (recommended)"
    echo "  $0 --dry-run            # Preview what would be copied"
    echo "  $0 --yes                 # Non-interactive mode"
    echo "  $0 --force-sensitive     # Copy everything including sensitive files"
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --yes)
                AUTO_YES=true
                shift
                ;;
            --force-sensitive)
                FORCE_SENSITIVE=true
                shift
                ;;
            --help)
                print_usage
                exit 0
                ;;
            *)
                echo -e "${RED}Unknown option: $1${NC}"
                print_usage
                exit 1
                ;;
        esac
    done
}

check_requirements() {
    echo -e "${YELLOW}🔍 Checking requirements...${NC}"

    # Check if we're in the dotfiles directory
    if [[ ! -f "packages.list" ]] || [[ ! -f "install.sh" ]]; then
        echo -e "${RED}Error: This script must be run from the dotfiles directory.${NC}"
        exit 1
    fi

    # Check if ~/.config exists
    if [[ ! -d "$HOME/.config" ]]; then
        echo -e "${YELLOW}Warning: ~/.config directory not found. No configurations to copy.${NC}"
    fi

    echo -e "${GREEN}✓ Requirements check passed${NC}"
    echo ""
}

scan_configs() {
    echo -e "${YELLOW}🔍 Scanning for existing configurations...${NC}" >&2

    local found_configs=()

    # Scan ~/.config directory
    if [[ -d "$HOME/.config" ]]; then
        for config in "${!CONFIG_MAPPINGS[@]}"; do
            if [[ -d "$HOME/.config/$config" ]]; then
                echo -e "${CYAN}📁 Found: $config (~/.config/$config/)${NC}" >&2
                found_configs+=("$config:config")
            fi
        done
    fi

    # Check home directory dotfiles
    for dotfile in "${!HOME_MAPPINGS[@]}"; do
        if [[ -f "$HOME/$dotfile" ]]; then
            echo -e "${CYAN}📄 Found: ${dotfile#.} (~/$dotfile)${NC}" >&2
            found_configs+=("${dotfile}:home")
        fi
    done

    # Check SSH config
    if [[ -f "$SSH_CONFIG_SOURCE" ]]; then
        echo -e "${CYAN}🔐 Found: SSH config (~/.ssh/config)${NC}" >&2
        found_configs+=("ssh:ssh")
    fi

    # Check ~/.local/bin for specific scripts
    local specific_scripts=("tmux-sessionizer" "screenshot" "screenshot_1" "screenshot_2" "nvim-launcher" "cursor-launcher" "zed-launcher" "opencode-launcher" "claude-code-launcher" "code-launcher" "ide-chooser" "setup-api-keys")
    for script in "${specific_scripts[@]}"; do
        if [[ -f "$HOME/.local/bin/$script" ]]; then
            echo -e "${CYAN}📄 Found: $script (~/.local/bin/$script)${NC}" >&2
            found_configs+=("$script:bin")
        fi
    done

    if [[ ${#found_configs[@]} -eq 0 ]]; then
        echo -e "${YELLOW}No existing configurations found to copy.${NC}" >&2
        echo -e "${YELLOW}You can still manually create configurations in the dotfiles directories.${NC}" >&2
        exit 0
    fi

    echo -e "${GREEN}Found ${#found_configs[@]} configuration(s) to potentially copy.${NC}" >&2
    echo "" >&2

    # Return found configs (to stdout)
    echo "${found_configs[@]}"
}

backup_existing() {
    local dest_dir="$1"
    if [[ -d "$dest_dir" ]] && [[ ! -L "$dest_dir" ]]; then
        local backup_dir="${dest_dir}.backup.$(date +%Y%m%d_%H%M%S)"
        echo -e "${YELLOW}📦 Backing up existing $dest_dir to $backup_dir${NC}"
        if [[ "$DRY_RUN" != "true" ]]; then
            mv "$dest_dir" "$backup_dir"
        fi
    fi
}

copy_config() {
    local source="$1"
    local dest="$2"
    local config_name="$3"

    # Create destination directory
    local dest_dir
    dest_dir="$(dirname "$dest")"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${BLUE}[DRY RUN] Would copy $source → $dest${NC}"
        return 0
    fi

    # Backup existing destination if it exists
    if [[ -d "$dest_dir" ]]; then
        backup_existing "$dest_dir"
    fi

    echo -e "${BLUE}Copying $config_name...${NC}"

    # Create destination directory
    mkdir -p "$dest_dir"

    # Copy the configuration
    if [[ -d "$source" ]]; then
        cp -r "$source" "$dest"
        echo -e "${GREEN}✓ Copied directory: $source → $dest${NC}"
    elif [[ -f "$source" ]]; then
        cp "$source" "$dest"
        echo -e "${GREEN}✓ Copied file: $source → $dest${NC}"
    else
        echo -e "${RED}✗ Source not found: $source${NC}"
        return 1
    fi

    return 0
}

check_sensitive_content() {
    local source="$1"
    local config_name="$2"

    # Check for potentially sensitive files
    local sensitive_patterns=(
        "id_rsa"
        "id_ed25519"
        "*.key"
        "*secret*"
        "*password*"
        "*token*"
        "*api_key*"
        "*api_secret*"
        "*access_token*"
        "*auth_token*"
        "auth.json"
        "credentials"
        ".env"
        ".env.local"
        ".env.production"
        "*.gpg"
        "secring.gpg"
        "*.ovpn"
        "cookies.sqlite"
        "places.sqlite"
        "keyring"
        "keyrings"
    )

    if [[ -d "$source" ]]; then
        for pattern in "${sensitive_patterns[@]}"; do
            for sensitive_file in $(find "$source" -name "$pattern" -type f 2>/dev/null); do
                # Check if the file contains safe export patterns
                if grep -qE 'export [A-Z_]+_API_KEY=\$\(pass .*\)' "$sensitive_file"; then
                    # Whitelist: Safe export pattern, skip flagging
                    continue
                fi
                # Found sensitive content
                return 0
            done
        done
    fi

    return 1  # No sensitive content found
}

get_sensitive_files() {
    local source="$1"

    local sensitive_patterns=(
        "id_rsa"
        "id_ed25519"
        "*.key"
        "*secret*"
        "*password*"
        "*token*"
        "*api*"
        "auth.json"
        "credentials"
        "*.gpg"
        "secring.gpg"
        "*.ovpn"
        "cookies.sqlite"
        "places.sqlite"
    )

    local found_files=()

    if [[ -d "$source" ]]; then
        for pattern in "${sensitive_patterns[@]}"; do
            while IFS= read -r -d '' file; do
                # Check if the file contains safe export patterns
                if grep -qE 'export [A-Z_]+_API_KEY=\$\(pass .*\)' "$file"; then
                    # Whitelist: Safe export pattern, skip
                    continue
                fi
                found_files+=("$(basename "$file")")
            done < <(find "$source" -name "$pattern" -type f -print0 2>/dev/null)
        done
    fi

    echo "${found_files[*]}"
}

prompt_user() {
    local source="$1"
    local dest="$2"
    local config_name="$3"

    # Check for sensitive content first
    if check_sensitive_content "$source" "$config_name"; then
        if [[ "$FORCE_SENSITIVE" != "true" ]]; then
            local sensitive_files
            sensitive_files=$(get_sensitive_files "$source")
            echo -e "${RED}❌ Skipped: $config_name (contains sensitive files: ${sensitive_files[*]})${NC}"
            echo -e "${CYAN}💡 Suggestion: Handle sensitive files separately with encryption or exclude from dotfiles${NC}"
            SKIPPED_SENSITIVE_COUNT=$((SKIPPED_SENSITIVE_COUNT + 1))
            return 2  # Special return code for sensitive skip
        else
            echo -e "${YELLOW}⚠️  FORCE: $config_name contains sensitive files but proceeding due to --force-sensitive${NC}"
        fi
    fi

    # In dry-run mode, just proceed
    if [[ "$DRY_RUN" == "true" ]]; then
        return 0
    fi

    if [[ "$AUTO_YES" == "true" ]]; then
        return 0
    fi

    echo ""
    echo -e "${PURPLE}Copy $source to $dest?${NC}"
    echo -n "[Y/n/s(q)uit]? "

    local response
    read -r response

    case "${response,,}" in
        "" | "y" | "yes")
            return 0
            ;;
        "n" | "no")
            return 1
            ;;
        "s" | "q" | "quit")
            echo -e "${YELLOW}Operation cancelled by user.${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid response. Skipping.${NC}"
            return 1
            ;;
    esac
}

process_configs() {
    local found_configs=("$@")

    echo -e "${YELLOW}🚀 Starting copy process...${NC}"
    echo ""

    for ((i=0; i<${#found_configs[@]}; i++)); do
        config_entry="${found_configs[i]}"
        IFS=':' read -r config_name config_type <<< "$config_entry"

        case "$config_type" in
            "config")
                local source="$HOME/.config/$config_name"
                local dest="${CONFIG_MAPPINGS[$config_name]}"
                ;;
            "home")
                local source="$HOME/$config_name"
                local dest="${HOME_MAPPINGS[$config_name]}"
                ;;
            "ssh")
                local source="$SSH_CONFIG_SOURCE"
                local dest="$SSH_CONFIG_DEST"
                ;;
            "bin")
                local source="$HOME/.local/bin/$config_name"
                local dest="scripts/.local/bin/$config_name"
                ;;
            *)
                echo -e "${RED}Unknown config type: $config_type${NC}"
                continue
                ;;
        esac

        # Check if source exists
        if [[ ! -e "$source" ]]; then
            echo -e "${RED}✗ Source not found: $source${NC}"
            continue
        fi

        # Prompt user
        local prompt_result
        prompt_result=$(prompt_user "$source" "$dest" "$config_name")
        local exit_code=$?

        if [[ $exit_code -eq 0 ]]; then
        if copy_config "$source" "$dest" "$config_name"; then
            COPIED_COUNT=$((COPIED_COUNT + 1))
        else
            SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        fi
    elif [[ $exit_code -eq 2 ]]; then
        # Already handled sensitive skip in prompt_user
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    else
            echo -e "${YELLOW}⏭️  Skipped $config_name${NC}"
            SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        fi
    done
}

print_summary() {
    echo ""
    echo -e "${BLUE}📊 Bootstrap Summary${NC}"
    echo -e "${BLUE}===================${NC}"
    echo -e "${GREEN}✓ Copied: $COPIED_COUNT configuration(s)${NC}"

    if [[ $SKIPPED_COUNT -gt 0 ]]; then
        echo -e "${YELLOW}⏭️  Skipped: $SKIPPED_COUNT configuration(s)${NC}"
        if [[ $SKIPPED_SENSITIVE_COUNT -gt 0 ]]; then
            echo -e "${RED}   └─ $SKIPPED_SENSITIVE_COUNT skipped due to sensitive content${NC}"
        fi
    fi

    if [[ "$DRY_RUN" != "true" ]] && [[ $COPIED_COUNT -gt 0 ]]; then
        echo ""
        echo -e "${CYAN}💡 Next steps:${NC}"
        echo -e "${CYAN}   • Run 'git add .' to stage changes${NC}"
        echo -e "${CYAN}   • Test with './install.sh' to verify symlinks work${NC}"
        echo -e "${CYAN}   • Commit your dotfiles: 'git commit -m \"Add initial configurations\"'${NC}"
    fi

    if [[ $SKIPPED_SENSITIVE_COUNT -gt 0 ]]; then
        echo ""
        echo -e "${YELLOW}🔐 Security Note:${NC}"
        echo -e "${YELLOW}   $SKIPPED_SENSITIVE_COUNT configuration(s) were skipped due to sensitive content.${NC}"
        echo -e "${YELLOW}   Consider using encrypted storage (git-crypt) or separate management for:${NC}"
        echo -e "${YELLOW}   • SSH private keys • API tokens • Passwords • VPN configs${NC}"
    fi
}

main() {
    print_header

    if [[ $# -gt 0 ]]; then
        parse_args "$@"
    fi

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be modified${NC}"
        echo ""
    fi

    if [[ "$AUTO_YES" == "true" ]]; then
        echo -e "${RED}⚠️  AUTO-YES MODE - All prompts will be answered 'yes'${NC}"
        echo -e "${RED}   This could overwrite existing configurations!${NC}"
        echo ""
    fi

    if [[ "$FORCE_SENSITIVE" == "true" ]]; then
        echo -e "${RED}⚠️  FORCE-SENSITIVE MODE - Will copy configs containing sensitive files${NC}"
        echo -e "${RED}   This may include private keys, passwords, and API tokens!${NC}"
        echo -e "${RED}   ENSURE THESE FILES ARE ENCRYPTED OR EXCLUDED FROM GIT!${NC}"
        echo ""
    fi

    check_requirements

    local found_configs_string
    found_configs_string=$(scan_configs)

    if [[ -z "$found_configs_string" ]]; then
        exit 0
    fi

    # Convert string to array
    IFS=' ' read -r -a found_configs <<< "$found_configs_string"

    if [[ ${#found_configs[@]} -eq 0 ]]; then
        exit 0
    fi

    process_configs "${found_configs[@]}"

    print_summary
}

# Run main function
main "$@"
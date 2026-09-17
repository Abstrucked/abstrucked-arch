#!/bin/bash
# Command-line argument parsing

# Prevent multiple sourcing
if [[ -n "${_ARGS_SH_LOADED:-}" ]]; then
    return 0
fi
_ARGS_SH_LOADED=1

# Source logging functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"

# Global flags (defaults)
DRY_RUN=false
VERBOSE=false
QUIET=false
NON_INTERACTIVE=false
SHOW_HELP=false

# Array of steps to run (empty = all)
RUN_STEPS=()
SKIP_STEPS=()

# Show usage information
show_help() {
    local script_name
    script_name=$(basename "$0")
    
    echo -e "${CYAN}Usage:${NC} $script_name [OPTIONS]"
    echo ""
    echo -e "${CYAN}Dotfiles Installation Script${NC}"
    echo ""
    echo -e "${YELLOW}Options:${NC}"
    echo -e "  ${GREEN}--dry-run${NC}           Show what would be done without making changes"
    echo -e "  ${GREEN}--verbose, -v${NC}       Enable debug output"
    echo -e "  ${GREEN}--quiet, -q${NC}         Suppress non-error output"
    echo -e "  ${GREEN}--non-interactive, -y${NC}  Skip all prompts (use defaults)"
    echo -e "  ${GREEN}--help, -h${NC}          Show this help message"
    echo ""
    echo -e "${YELLOW}Selective Installation:${NC}"
    echo -e "  ${GREEN}--only STEP${NC}         Only run specific step(s) (can be repeated)"
    echo -e "  ${GREEN}--skip STEP${NC}         Skip specific step(s) (can be repeated)"
    echo ""
    echo -e "${YELLOW}Available Steps:${NC}"
    echo -e "  packages      Install system packages"
    echo -e "  yay           Install yay AUR helper"
    echo -e "  node          Install Node.js version manager"
    echo -e "  yubikey       Install YubiKey tools"
    echo -e "  stow          Setup symlinks with GNU Stow"
    echo -e "  theme         Setup Alacritty theme"
    echo -e "  backgrounds   Setup desktop backgrounds"
    echo -e "  tmux          Setup Tmux configuration"
    echo -e "  lazyvim       Install LazyVim Neovim distribution"
    echo ""
    echo -e "${YELLOW}Examples:${NC}"
    echo -e "  $script_name                      # Interactive installation"
    echo -e "  $script_name --dry-run            # Preview changes only"
    echo -e "  $script_name --only packages stow # Only install packages and stow"
    echo -e "  $script_name --skip yubikey       # Skip YubiKey installation"
    echo -e "  $script_name -y                   # Non-interactive (defaults)"
    echo -e "  $script_name -v                   # Verbose output"
    exit 0
}

# Parse command-line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --verbose|-v)
                VERBOSE=true
                LOG_LEVEL=$LOG_DEBUG
                shift
                ;;
            --quiet|-q)
                QUIET=true
                LOG_LEVEL=$LOG_ERROR
                shift
                ;;
            --non-interactive|-y)
                NON_INTERACTIVE=true
                shift
                ;;
            --help|-h)
                show_help
                ;;
            --only)
                if [[ -z "${2:-}" ]]; then
                    die "--only requires a step name"
                fi
                RUN_STEPS+=("$2")
                shift 2
                ;;
            --skip)
                if [[ -z "${2:-}" ]]; then
                    die "--skip requires a step name"
                fi
                SKIP_STEPS+=("$2")
                shift 2
                ;;
            -*)
                die "Unknown option: $1"
                ;;
            *)
                die "Unexpected argument: $1"
                ;;
        esac
    done
}

# Check if a step should be run
should_run_step() {
    local step=$1
    
    # If specific steps were requested, only run those
    if [[ ${#RUN_STEPS[@]} -gt 0 ]]; then
        for requested in "${RUN_STEPS[@]}"; do
            if [[ "$requested" == "$step" ]]; then
                return 0
            fi
        done
        return 1
    fi
    
    # If steps were skipped, don't run those
    for skipped in "${SKIP_STEPS[@]}"; do
        if [[ "$skipped" == "$step" ]]; then
            return 1
        fi
    done
    
    return 0
}

# Execute a command (or print it in dry-run mode)
execute() {
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] $*"
        return 0
    fi
    
    "$@"
}

# Prompt user for confirmation
confirm() {
    local message=$1
    local default=${2:-"n"}
    
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "$message (auto: $default)"
        [[ "$default" == "y" ]]
        return $?
    fi
    
    local prompt
    if [[ "$default" == "y" ]]; then
        prompt="$message [Y/n]: "
    else
        prompt="$message [y/N]: "
    fi
    
    read -r -p "$prompt" response
    
    case "${response,,}" in
        y|yes) return 0 ;;
        n|no) return 1 ;;
        "") [[ "$default" == "y" ]]; return $? ;;
        *) [[ "$default" == "y" ]]; return $? ;;
    esac
}
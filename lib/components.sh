#!/bin/bash
# Component definitions and selection

# Prevent multiple sourcing
if [[ -n "${_COMPONENTS_SH_LOADED:-}" ]]; then
    return 0
fi
_COMPONENTS_SH_LOADED=1

# Source logging functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/logging.sh"

# Component definitions
# Format: "name|description|default_enabled|step_name"
declare -a COMPONENTS=(
    "yay|AUR helper (yay)|true|yay"
    "packages|System packages|true|packages"
    "node|Node.js version manager|true|node"
    "stow|Symlink management (GNU Stow)|true|stow"
    "shell|Default shell (zsh or bash)|true|shell"
    "theme|Alacritty color theme|true|theme"
    "backgrounds|Desktop backgrounds|true|backgrounds"
    "tmux|Tmux configuration|true|tmux"
    "lazyvim|LazyVim Neovim distribution|true|lazyvim"
    "yubikey|YubiKey tools (optional)|false|yubikey"
)

# Global shell selection
SELECTED_SHELL=""

# Get component name
get_component_name() {
    local component=$1
    echo "${component%%|*}"
}

# Get component description
get_component_desc() {
    local component=$1
    local temp="${component#*|}"
    echo "${temp%%|*}"
}

# Get component default
get_component_default() {
    local component=$1
    local temp="${component#*|*|}"
    echo "${temp%%|*}"
}

# Get component step name
get_component_step() {
    local component=$1
    echo "${component##*|}"
}

# Check if component should be installed
component_enabled() {
    local component=$1
    local name
    name=$(get_component_name "$component")
    local default
    default=$(get_component_default "$component")
    local step
    step=$(get_component_step "$component")
    
    # Check --only flag
    if [[ ${#RUN_STEPS[@]} -gt 0 ]]; then
        for requested in "${RUN_STEPS[@]}"; do
            if [[ "$requested" == "$step" ]]; then
                return 0
            fi
        done
        return 1
    fi
    
    # Check --skip flag
    for skipped in "${SKIP_STEPS[@]}"; do
        if [[ "$skipped" == "$step" ]]; then
            return 1
        fi
    done
    
    # Return default
    [[ "$default" == "true" ]]
    return $?
}

# Interactive shell selection
select_shell() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                 Default Shell Selection                ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Select your default shell:"
    echo ""
    echo -e "  ${GREEN}1${NC}) ${GREEN}zsh${NC}   - Powerlevel10k prompt, zsh-autocomplete"
    echo -e "  ${GREEN}2${NC}) ${GREEN}bash${NC}  - Starship prompt, bash-completion"
    echo ""

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        echo -e "${BLUE}  (Non-interactive: defaulting to zsh)${NC}"
        SELECTED_SHELL="zsh"
        return 0
    fi

    read -r -p "  Selection [1-2]: " shell_choice

    case "$shell_choice" in
        1)
            SELECTED_SHELL="zsh"
            ;;
        2)
            SELECTED_SHELL="bash"
            ;;
        *)
            echo -e "${YELLOW}  Invalid selection, defaulting to zsh${NC}"
            SELECTED_SHELL="zsh"
            ;;
    esac

    echo ""
    echo -e "  ${GREEN}Selected shell: $SELECTED_SHELL${NC}"
    echo ""
}

# Detect currently stowed shell
detect_current_shell() {
    if [[ -L "$HOME/.zshrc" ]] && [[ "$(readlink "$HOME/.zshrc")" == *"dotfiles/zsh"* ]]; then
        echo "zsh"
    elif [[ -L "$HOME/.bashrc" ]] && [[ "$(readlink "$HOME/.bashrc")" == *"dotfiles/bash"* ]]; then
        echo "bash"
    else
        echo ""
    fi
}

# Interactive component selection
select_components() {
    local selected=()
    
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              Component Selection Menu                   ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Select which components to install:"
    echo -e "  Enter numbers separated by commas (e.g., 1,3,5)"
    echo ""
    
    for i in "${!COMPONENTS[@]}"; do
        local component="${COMPONENTS[$i]}"
        local name
        name=$(get_component_name "$component")
        local desc
        desc=$(get_component_desc "$component")
        local default
        default=$(get_component_default "$component")
        
        local indicator="○"
        if [[ "$default" == "true" ]]; then
            indicator="●"
            echo -e "  ${GREEN}$((i+1))${NC}) ${indicator} ${GREEN}${name}${NC} - ${desc}"
        else
            echo -e "  ${GREEN}$((i+1))${NC}) ${indicator} ${name} - ${desc}"
        fi
    done
    
    echo ""
    echo -e "  ${YELLOW}a${NC}) Install all"
    echo -e "  ${YELLOW}d${NC}) Install defaults only"
    echo -e "  ${YELLOW}n${NC}) Install none"
    echo ""
    
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        echo -e "${BLUE}  (Non-interactive: using defaults)${NC}"
        # Use defaults
        for component in "${COMPONENTS[@]}"; do
            if component_enabled "$component"; then
                selected+=("$component")
            fi
        done
    else
        read -r -p "  Selection: " selection
        
        case "${selection,,}" in
            a|all)
                selected=("${COMPONENTS[@]}")
                ;;
            d|default)
                for component in "${COMPONENTS[@]}"; do
                    if component_enabled "$component"; then
                        selected+=("$component")
                    fi
                done
                ;;
            n|none)
                selected=()
                ;;
            *)
                IFS=',' read -ra indices <<< "$selection"
                for idx in "${indices[@]}"; do
                    idx=$((idx-1))
                    if [[ $idx -ge 0 ]] && [[ $idx -lt ${#COMPONENTS[@]} ]]; then
                        selected+=("${COMPONENTS[$idx]}")
                    fi
                done
                ;;
        esac
    fi
    
    # Store selected components globally
    SELECTED_COMPONENTS=("${selected[@]}")
}

# Display installation summary
show_summary() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                 Installation Summary                    ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
    
    if [[ ${#SELECTED_COMPONENTS[@]} -eq 0 ]]; then
        echo -e "  ${YELLOW}No components selected for installation.${NC}"
        return 1
    fi
    
    echo -e "  ${GREEN}Will install:${NC}"
    for component in "${SELECTED_COMPONENTS[@]}"; do
        local desc
        desc=$(get_component_desc "$component")
        if [[ "$desc" == *"shell"* ]] && [[ -n "$SELECTED_SHELL" ]]; then
            echo -e "    ${GREEN}✓${NC} Default shell: ${GREEN}$SELECTED_SHELL${NC}"
        else
            echo -e "    ${GREEN}✓${NC} $desc"
        fi
    done
    
    # Show skipped components
    local skipped=()
    for component in "${COMPONENTS[@]}"; do
        local found=false
        for selected in "${SELECTED_COMPONENTS[@]}"; do
            if [[ "$component" == "$selected" ]]; then
                found=true
                break
            fi
        done
        if [[ "$found" == "false" ]]; then
            skipped+=("$component")
        fi
    done
    
    if [[ ${#skipped[@]} -gt 0 ]]; then
        echo ""
        echo -e "  ${YELLOW}Will skip:${NC}"
        for component in "${skipped[@]}"; do
            local desc
            desc=$(get_component_desc "$component")
            echo -e "    ${YELLOW}⊘${NC} $desc"
        done
    fi
    
    echo ""
    
    # Show mode
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "  ${YELLOW}Mode: DRY RUN (no changes will be made)${NC}"
    fi
    
    echo ""
}

# Confirm installation
confirm_installation() {
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "Proceeding with installation (non-interactive)..."
        return 0
    fi
    
    read -r -p "  Proceed with installation? [Y/n] " response
    case "${response,,}" in
        n|no)
            log_info "Installation cancelled."
            exit 0
            ;;
        *)
            log_info "Proceeding with installation..."
            ;;
    esac
}
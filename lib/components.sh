#!/bin/bash
# Component definitions and selection

# Prevent multiple sourcing
if [[ -n "${_COMPONENTS_SH_LOADED:-}" ]]; then
    return 0
fi
_COMPONENTS_SH_LOADED=1

# Source logging functions
source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"
source "$(dirname "${BASH_SOURCE[0]}")/args.sh"
source "$(dirname "${BASH_SOURCE[0]}")/ui.sh"

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

window_manager_description() {
    case "${1:-awesome}" in
        awesome) echo "AwesomeWM" ;;
        both) echo "AwesomeWM + Hyprland" ;;
        hyprland) echo "Hyprland" ;;
        *) echo "Unknown" ;;
    esac
}

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
    local default
    default=$(get_component_default "$component")
    local step
    step=$(get_component_step "$component")
    
    should_run_step "$step" || return 1
    if [[ ${#RUN_STEPS[@]} -gt 0 ]]; then
        return 0
    fi
    
    # Return default
    [[ "$default" == "true" ]]
    return $?
}

# Select the window manager only when packages or Stow are selected.
select_window_manager() {
    local component step needs_window_manager=false selection

    for component in "${SELECTED_COMPONENTS[@]}"; do
        step=$(get_component_step "$component")
        if [[ "$step" == "packages" || "$step" == "stow" ]]; then
            needs_window_manager=true
            break
        fi
    done

    [[ "$needs_window_manager" == true ]] || return 0
    if [[ "$WINDOW_MANAGER_EXPLICIT" == true ]]; then
        log_info "Selected window manager: $(window_manager_description "$WINDOW_MANAGER")"
        return 0
    fi
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        WINDOW_MANAGER=awesome
        log_info "Non-interactive mode: using AwesomeWM."
        return 0
    fi

    if [[ "${UI_MODE:-plain}" == "gum" ]]; then
        if ! selection=$(ui_choose_one "Select window manager" \
            "AwesomeWM" "AwesomeWM + Hyprland" "Hyprland"); then
            log_info "Installation cancelled."
            exit 0
        fi
        case "$selection" in
            AwesomeWM) WINDOW_MANAGER=awesome ;;
            "AwesomeWM + Hyprland") WINDOW_MANAGER=both ;;
            Hyprland) WINDOW_MANAGER=hyprland ;;
            *) log_error "Invalid window-manager selection: $selection"; return 1 ;;
        esac
    else
        echo ""
        echo "Window manager selection:"
        echo "  1) AwesomeWM"
        echo "  2) AwesomeWM + Hyprland"
        echo "  3) Hyprland"
        read -r -p "Selection [1]: " selection || return 1
        case "${selection:-1}" in
            1) WINDOW_MANAGER=awesome ;;
            2) WINDOW_MANAGER=both ;;
            3) WINDOW_MANAGER=hyprland ;;
            *) log_error "Invalid window-manager selection: $selection"; return 1 ;;
        esac
    fi

    log_info "Selected window manager: $(window_manager_description "$WINDOW_MANAGER")"
}

# Point the account's login shell at the selected shell. Stow only installs the
# rc file, so without this the shell selection never reaches /etc/passwd.
set_login_shell() {
    local shell_name=${1:-${SELECTED_SHELL:-}} shell_path current_path user

    [[ -n "$shell_name" ]] || return 0

    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "[dry-run] Would set the login shell to $shell_name"
        return 0
    fi

    if ! shell_path=$(command -v "$shell_name" 2>/dev/null); then
        log_error "Selected shell is not installed: $shell_name"
        return 1
    fi
    # chsh and /etc/shells both expect a real path, not a symlink such as /bin/zsh.
    shell_path=$(readlink -f -- "$shell_path")

    if [[ -n "${SHELL:-}" ]]; then
        current_path=$(readlink -f -- "$SHELL" 2>/dev/null) || current_path="$SHELL"
        if [[ "$current_path" == "$shell_path" ]]; then
            log_info "Login shell is already $shell_path"
            return 0
        fi
    fi

    if [[ -r /etc/shells ]] && ! grep -qxF -- "$shell_path" /etc/shells; then
        log_warn "$shell_path is not listed in /etc/shells; chsh may refuse it."
    fi

    user=${USER:-$(id -un)}
    log_info "Setting login shell to $shell_path"
    # sudo avoids a password prompt that would hang a non-interactive run.
    execute sudo chsh -s "$shell_path" "$user"
}

# Interactive shell selection.
select_shell() {
    local shell_choice

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        echo -e "${BLUE}  (Non-interactive: defaulting to zsh)${NC}"
        SELECTED_SHELL="zsh"
        return 0
    fi

    if [[ "${UI_MODE:-plain}" == "gum" ]]; then
        if ! shell_choice=$(ui_choose_one "Select your default shell" \
            "zsh - Powerlevel10k prompt, zsh-autocomplete" \
            "bash - Starship prompt, bash-completion"); then
            log_info "Installation cancelled."
            exit 0
        fi
        case "$shell_choice" in
            zsh\ -\ *) SELECTED_SHELL="zsh" ;;
            bash\ -\ *) SELECTED_SHELL="bash" ;;
            *) log_error "Invalid shell selection: $shell_choice"; return 1 ;;
        esac
        log_info "Selected shell: $SELECTED_SHELL"
        return 0
    fi

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
    local i component name desc default indicator selection idx
    local indices=()
    local component_count=${#COMPONENTS[@]}
    SELECTED_COMPONENTS=()
    SELECTED_SHELL=""
    
    if [[ "${UI_MODE:-plain}" == "gum" ]]; then
        local -a options=() selected_labels=() gum_command
        local label selected_index

        for i in "${!COMPONENTS[@]}"; do
            component="${COMPONENTS[$i]}"
            name=$(get_component_name "$component")
            desc=$(get_component_desc "$component")
            label="$((i + 1)). $name - $desc"
            options+=("$label")
            if [[ "$(get_component_default "$component")" == "true" ]]; then
                selected_labels+=("$label")
            fi
        done

        gum_command=(gum choose --no-limit --header "Select components (space toggles, enter continues)")
        for label in "${selected_labels[@]}"; do
            gum_command+=(--selected "$label")
        done
        gum_command+=("${options[@]}")

        if ! selection=$("${gum_command[@]}"); then
            log_info "Installation cancelled."
            exit 0
        fi
        while IFS= read -r label; do
            [[ -n "$label" ]] || continue
            selected_index=${label%%.*}
            if [[ "$selected_index" =~ ^[0-9]+$ ]] &&
                ((selected_index >= 1 && selected_index <= component_count)); then
                selected+=("${COMPONENTS[$((selected_index - 1))]}")
            fi
        done <<< "$selection"
    else
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
        read -r -p "  Selection: " selection || return 1
        
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
                if [[ ! "$selection" =~ ^[[:space:]]*[0-9]+[[:space:]]*(,[[:space:]]*[0-9]+[[:space:]]*)*$ ]]; then
                    log_error "Invalid component selection: $selection"
                    return 1
                fi
                IFS=',' read -ra indices <<< "$selection"
                for idx in "${indices[@]}"; do
                    idx=${idx//[[:space:]]/}
                    while [[ ${#idx} -gt 1 && "$idx" == 0* ]]; do idx=${idx#0}; done
                    if [[ ${#idx} -gt ${#component_count} ]] || (( 10#$idx < 1 || 10#$idx > component_count )); then
                        log_error "Component number out of range: $idx"
                        return 1
                    fi
                    selected+=("${COMPONENTS[$((10#$idx - 1))]}")
                done
                ;;
        esac
        fi
    fi
    
    # Store selected components globally
    # Apply CLI restrictions to every selection mode and deduplicate in install order.
    for component in "${COMPONENTS[@]}"; do
        should_run_step "$(get_component_step "$component")" || continue
        for name in "${selected[@]}"; do
            if [[ "$component" == "$name" ]]; then
                SELECTED_COMPONENTS+=("$component")
                break
            fi
        done
    done
    return 0
}

# Called by the installer after selection, before any installation work.
validate_component_dependencies() {
    local component step
    local yay=false packages=false stow=false shell=false needs_yay=false
    for component in "${SELECTED_COMPONENTS[@]}"; do
        step=$(get_component_step "$component")
        case "$step" in
            yay) yay=true ;;
            packages) packages=true; needs_yay=true ;;
            yubikey) needs_yay=true ;;
            stow) stow=true ;;
            shell) shell=true ;;
        esac
    done
    if [[ "$needs_yay" == true && "$yay" != true ]] && ! command_exists yay; then
        log_error "packages and yubikey require yay installed or selected"
        return 1
    fi
    if [[ "$stow" == true && "$packages" != true ]] && ! command_exists stow; then
        log_error "stow requires stow installed or packages selected"
        return 1
    fi
    if [[ "$shell" == true && "$stow" != true ]]; then
        log_error "shell requires stow selected"
        return 1
    fi
    return 0
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
        return 0
    fi
    
    echo -e "  ${GREEN}Will install:${NC}"
    local has_window_manager_component=false
    for component in "${SELECTED_COMPONENTS[@]}"; do
        if [[ "$(get_component_step "$component")" == "packages" ||
            "$(get_component_step "$component")" == "stow" ]]; then
            has_window_manager_component=true
        fi
        local desc
        desc=$(get_component_desc "$component")
        if [[ "$desc" == *"shell"* ]] && [[ -n "$SELECTED_SHELL" ]]; then
            echo -e "    ${GREEN}✓${NC} Default shell: ${GREEN}$SELECTED_SHELL${NC}"
        else
            echo -e "    ${GREEN}✓${NC} $desc"
        fi
    done
    if [[ "$has_window_manager_component" == true ]]; then
        echo -e "    ${GREEN}✓${NC} Window manager: ${GREEN}$(window_manager_description "$WINDOW_MANAGER")${NC}"
    fi
    
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
    [[ ${#SELECTED_COMPONENTS[@]} -gt 0 ]] || return 0
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        log_info "Proceeding with installation (non-interactive)..."
        return 0
    fi

    if [[ "${UI_MODE:-plain}" == "gum" ]]; then
        if ui_confirm "Proceed with installation?"; then
            log_info "Proceeding with installation..."
        else
            log_info "Installation cancelled."
            exit 0
        fi
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

#!/bin/bash
# Install Node.js version manager (n or nvm)

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source helper functions
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/validation.sh"
source "$SCRIPT_DIR/lib/cleanup.sh"

# Set up cleanup trap
setup_cleanup_trap

# Script variables
INSTALL_CHOICE=""

print_header() {
    log_header "Node.js Version Manager Installer"
    log_info "Choose between n (simpler) or nvm (more features)"
}

print_info() {
    echo -e "${YELLOW}Available options:${NC}"
    echo -e "${GREEN}n${NC}     - Simple, fast Node.js version manager"
    echo -e "${GREEN}      - Pros: Lightweight, fast switching, simple commands${NC}"
    echo -e "${GREEN}      - Cons: Bash-only, no .nvmrc auto-switching${NC}"
    echo ""
    echo -e "${GREEN}nvm${NC}   - Advanced Node.js version manager"
    echo -e "${GREEN}      - Pros: Supports .nvmrc, works with any shell, more features${NC}"
    echo -e "${GREEN}      - Cons: Slower, more complex, requires bash initialization${NC}"
    echo ""
}

get_user_choice() {
    while true; do
        echo -e "${PURPLE}Which Node.js version manager would you like to install?${NC}"
        echo -n "[n/nvm/skip]? "
        
        local response
        read -r response
        
        case "${response,,}" in
            "n")
                INSTALL_CHOICE="n"
                break
                ;;
            "nvm")
                INSTALL_CHOICE="nvm"
                break
                ;;
            "skip" | "s")
                log_info "Skipping Node.js version manager installation."
                exit 0
                ;;
            *)
                log_error "Invalid choice. Please enter 'n', 'nvm', or 'skip'."
                ;;
        esac
    done
}

# Download a script safely and verify it
download_script() {
    local url=$1
    local output_file=$2
    
    log_step "Downloading from: $url"
    
    # Download with error checking
    if ! curl -fsSL -o "$output_file" "$url"; then
        log_error "Failed to download from: $url"
        return 1
    fi
    
    # Verify the script is not empty
    if [[ ! -s "$output_file" ]]; then
        log_error "Downloaded script is empty"
        return 1
    fi
    
    # Basic sanity check - should be a shell script
    if ! head -1 "$output_file" | grep -q '^#!/'; then
        log_warn "Downloaded script does not appear to be a shell script"
    fi
    
    return 0
}

install_n() {
    log_step "Installing n (Node.js version manager)..."
    
    # Check if n is already installed
    if command_exists n; then
        log_success "n is already installed!"
        return 0
    fi
    
    # Check prerequisites
    require_command curl "curl is required for installation"
    
    # Create temp directory
    local temp_dir
    temp_dir=$(create_temp_dir "n-install") || return 1
    
    # Download n installer
    local installer="$temp_dir/n-install.sh"
    download_script "https://git.io/n-install" "$installer" || {
        log_error "Failed to download n installer"
        return 1
    }
    
    # Make executable and run
    chmod +x "$installer"
    
    log_step "Running n installer..."
    if ! bash "$installer"; then
        log_error "n installation failed"
        return 1
    fi
    
    # Source the updated profile to get n in PATH
    for profile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [[ -f "$profile" ]]; then
            # shellcheck disable=SC1090
            source "$profile" 2>/dev/null || true
        fi
    done
    
    # Verify installation
    if command_exists n; then
        log_success "n installed successfully!"
        echo ""
        echo -e "${CYAN}Usage examples:${NC}"
        echo -e "${CYAN}  n latest          # Install latest Node.js${NC}"
        echo -e "${CYAN}  n lts             # Install LTS version${NC}"
        echo -e "${CYAN}  n 18              # Install Node.js 18${NC}"
        echo -e "${CYAN}  n                 # List installed versions${NC}"
    else
        log_error "Failed to verify n installation"
        return 1
    fi
}

install_nvm() {
    log_step "Installing nvm (Node Version Manager)..."
    
    # Check if nvm is already installed
    if [[ -d "$HOME/.nvm" ]] || command_exists nvm; then
        log_success "nvm is already installed!"
        return 0
    fi
    
    # Check prerequisites
    require_command curl "curl is required for installation"
    
    # Create temp directory
    local temp_dir
    temp_dir=$(create_temp_dir "nvm-install") || return 1
    
    # Download nvm installer
    local installer="$temp_dir/nvm-install.sh"
    download_script "https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh" "$installer" || {
        log_error "Failed to download nvm installer"
        return 1
    }
    
    # Make executable and run
    chmod +x "$installer"
    
    log_step "Running nvm installer..."
    if ! bash "$installer"; then
        log_error "nvm installation failed"
        return 1
    fi
    
    # Source nvm
    export NVM_DIR="$HOME/.nvm"
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        # shellcheck disable=SC1091
        \. "$NVM_DIR/nvm.sh"
    fi
    
    # Add nvm to shell profiles if not already there
    local shell_profiles=("$HOME/.bashrc" "$HOME/.zshrc")
    
    for profile in "${shell_profiles[@]}"; do
        if [[ -f "$profile" ]]; then
            if ! grep -q "NVM_DIR" "$profile"; then
                log_info "Adding nvm configuration to $profile"
                cat >> "$profile" <<'EOF'

# NVM (Node Version Manager)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
EOF
            fi
        fi
    done
    
    # Verify installation
    if [[ -d "$HOME/.nvm" ]]; then
        log_success "nvm installed successfully!"
        echo ""
        echo -e "${CYAN}Usage examples:${NC}"
        echo -e "${CYAN}  nvm install node     # Install latest Node.js${NC}"
        echo -e "${CYAN}  nvm install --lts    # Install LTS version${NC}"
        echo -e "${CYAN}  nvm install 18       # Install Node.js 18${NC}"
        echo -e "${CYAN}  nvm list             # List installed versions${NC}"
        echo -e "${CYAN}  nvm use 18           # Switch to Node.js 18${NC}"
        echo ""
        log_warn "Restart your terminal or run 'source ~/.bashrc' to use nvm"
    else
        log_error "Failed to verify nvm installation"
        return 1
    fi
}

main() {
    print_header
    print_info
    get_user_choice
    
    case "$INSTALL_CHOICE" in
        "n")
            install_n
            ;;
        "nvm")
            install_nvm
            ;;
    esac
    
    echo ""
    log_success "Node.js version manager installation complete!"
    log_info "You can now install Node.js versions using your chosen manager."
}

# Run main function
main "$@"
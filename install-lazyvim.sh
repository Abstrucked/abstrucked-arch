#!/bin/bash
# Install LazyVim Neovim distribution

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source helper functions
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/validation.sh"
source "$SCRIPT_DIR/lib/cleanup.sh"

# Set up cleanup trap
setup_cleanup_trap

log_header "Installing LazyVim"

# Check prerequisites
log_step "Checking prerequisites..."
require_command nvim "Neovim is not installed. Please run install.sh first."
require_command git "git is required but not installed."

# Set config directory
NVIM_CONFIG_DIR="$HOME/.config/nvim"

# Check if LazyVim is already installed
if [[ -d "$NVIM_CONFIG_DIR" ]]; then
    log_warn "LazyVim config directory already exists at $NVIM_CONFIG_DIR"
    read -r -p "Do you want to reinstall? (y/N) " response
    if [[ ! "$response" =~ ^[Yy]$ ]]; then
        log_info "Skipping LazyVim installation."
        exit 0
    fi
    
    # Backup existing config
    log_step "Backing up existing configuration..."
    backup_item "$NVIM_CONFIG_DIR" || log_warn "Failed to backup existing config"
    
    # Remove existing config
    rm -rf "$NVIM_CONFIG_DIR"
fi

# Create config directory
log_step "Creating config directory..."
mkdir -p "$HOME/.config" || {
    log_error "Failed to create config directory"
    exit 1
}

# Clone LazyVim starter
log_step "Cloning LazyVim starter configuration..."
if ! git clone https://github.com/LazyVim/starter "$NVIM_CONFIG_DIR"; then
    log_error "Failed to clone LazyVim starter"
    exit 1
fi

# Remove .git directory to avoid confusion
log_step "Cleaning up git repository..."
rm -rf "$NVIM_CONFIG_DIR/.git"

# Install LazyVim
log_step "Installing LazyVim plugins..."
cd "$NVIM_CONFIG_DIR" || {
    log_error "Failed to change to config directory"
    exit 1
}

if command_exists nvim; then
    # Run Neovim to install plugins (headless mode)
    log_info "Running Neovim to install plugins (this may take a while)..."
    if nvim --headless "+Lazy! sync" +qa 2>/dev/null; then
        log_success "LazyVim plugins installed successfully"
    else
        log_warn "LazyVim plugin installation may have completed with warnings"
        echo -e "${YELLOW}Please run 'nvim' manually to verify plugin installation${NC}"
    fi
else
    log_warn "Could not run Neovim to install plugins automatically."
    log_info "Please run 'nvim' manually after installation to complete plugin setup."
fi

log_header "LazyVim Installation Complete!"
log_info "Your LazyVim configuration is ready at $NVIM_CONFIG_DIR"
log_info "Run 'nvim' to start using LazyVim"
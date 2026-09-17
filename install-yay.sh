#!/bin/bash
# Install yay AUR helper

set -euo pipefail

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source helper functions
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/validation.sh"
source "$SCRIPT_DIR/lib/cleanup.sh"

# Set up cleanup trap
setup_cleanup_trap

log_header "Installing yay AUR helper"

# Check if yay is already installed
if command_exists yay; then
    log_success "yay is already installed!"
    exit 0
fi

# Check prerequisites
log_step "Checking prerequisites..."
require_command git "git is required but not installed"
require_command makepkg "makepkg is required but not installed"

# Create temp directory for building
log_step "Creating temporary build directory..."
temp_dir=$(create_temp_dir "yay-build") || die "Failed to create temp directory"
log_debug "Build directory: $temp_dir"

# Clone yay from AUR
log_step "Cloning yay from AUR..."
cd "$temp_dir"
git clone https://aur.archlinux.org/yay.git || {
    log_error "Failed to clone yay repository"
    exit 1
}

# Build and install yay
log_step "Building and installing yay..."
cd yay
makepkg -si --noconfirm || {
    log_error "Failed to build/install yay"
    log_info "You may need to install dependencies manually"
    exit 1
}

log_success "yay installed successfully!"
#!/bin/bash
# Main installation script for dotfiles

set -euo pipefail

# Get script directory
DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source helper functions
source "$DOTFILES_DIR/lib/logging.sh"
source "$DOTFILES_DIR/lib/validation.sh"
source "$DOTFILES_DIR/lib/cleanup.sh"
source "$DOTFILES_DIR/lib/args.sh"
source "$DOTFILES_DIR/lib/components.sh"
source "$DOTFILES_DIR/lib/install-steps.sh"

require_non_root

# The installer currently writes fixed Home-relative configuration paths.
# Reject alternate XDG locations before any installation work rather than
# silently mixing two configuration roots.
XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
if [[ "$XDG_CONFIG_HOME" != "$HOME/.config" ]]; then
    die "Non-default XDG_CONFIG_HOME is not supported by this installer: $XDG_CONFIG_HOME"
fi
export XDG_CONFIG_HOME

# Set up cleanup trap
setup_cleanup_trap

# Parse command-line arguments
parse_args "$@"

# Reject unsafe backup destinations before UI setup or installation can mutate
# anything. Child helpers use the same canonical root; validation creates no dirs.
DOTFILES_BACKUP_ROOT=$(dotfiles_resolve_backup_root) || die "Invalid backup root"
export DOTFILES_BACKUP_ROOT

# Print header
log_header "Dotfiles Installation Script"
log_info "Dotfiles directory: $DOTFILES_DIR"

# Show dry-run notice
if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${YELLOW}║  DRY RUN MODE - No changes will be made                 ║${NC}"
    echo -e "${YELLOW}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
fi

# Validate prerequisites
log_step "Checking prerequisites..."
require_arch
require_command git "git is required but not installed"
require_command curl "curl is required but not installed"
validate_directory "$DOTFILES_DIR"
ui_initialize

# Interactive component selection
select_components
validate_component_dependencies || exit 1
if [[ ${#SELECTED_COMPONENTS[@]} -eq 0 ]]; then
    log_info "No components selected; nothing to install."
    exit 0
fi

select_window_manager || exit 1

# Select the shell before the summary so the confirmation reflects the full plan.
if component_selected shell; then select_shell || exit 1; fi

# Show summary and confirm
show_summary
confirm_installation
validate_component_privileges || exit 1

# Keep package-manager confirmations and sudo prompts aligned with the
# installer's mode. yay forwards sudoflags to all of its sudo invocations.
yay_install_args=(-S --needed)
sudo_args=()
if [[ "$NON_INTERACTIVE" == "true" ]]; then
    yay_install_args+=(--noconfirm --sudoflags=-n)
    sudo_args+=(-n)
fi

# Count selected components for progress
progress_init "${#SELECTED_COMPONENTS[@]}"

# ═══════════════════════════════════════════════════════════════
# INSTALLATION STEPS
# ═══════════════════════════════════════════════════════════════

# Run every selected component in the explicit policy order, independent of
# the order in which --only options were supplied.
for step in "${INSTALL_STEP_ORDER[@]}"; do
    component_selected "$step" || continue
    case "$step" in
        yay) install_yay ;;
        packages) install_packages ;;
        node) install_node ;;
        yubikey) install_yubikey ;;
        stow)
            # Preserve package -> shell prerequisites -> Stow ordering, even if
            # the shell component itself is not selected.
            validate_selected_shell_ready
            install_stow
            ;;
        theme) install_theme ;;
        backgrounds) install_backgrounds ;;
        tmux) install_tmux ;;
        shell) install_shell ;;
        lazyvim) install_lazyvim ;;
        *) die "Unknown install step in policy: $step" ;;
    esac
done

# Print final summary
progress_summary

# Show post-installation instructions
echo -e "${CYAN}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              Post-Installation Instructions             ║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${YELLOW}1. Restart your terminal or run:${NC}"
if [[ "$SELECTED_SHELL" == "bash" ]]; then
    echo -e "     ${GREEN}source ~/.bashrc${NC}"
    echo -e "     ${YELLOW}  (Starship prompt will be active after reload)${NC}"
else
    echo -e "     ${GREEN}source ~/.zshrc${NC}"
fi
echo ""
echo -e "  ${YELLOW}2. You may need to log out and back in for some changes${NC}"
echo -e "     ${YELLOW}to take effect.${NC}"
echo ""
echo -e "  ${YELLOW}3. Run ${GREEN}nvim${NC}${YELLOW} to start using LazyVim.${NC}"
echo ""
echo -e "  ${YELLOW}4. Backups of replaced configs are stored in:${NC}"
echo -e "     ${GREEN}${DOTFILES_BACKUP_ROOT:-$HOME/.dotfiles-backups}${NC}"
echo ""
if [[ "$SELECTED_SHELL" == "bash" ]]; then
    echo -e "  ${YELLOW}5. Customize your Starship prompt:${NC}"
    echo -e "     ${GREEN}starship preset catppuccin-mocha -o ~/.config/starship.toml${NC}"
    echo -e "     ${YELLOW}  Or edit ~/.config/starship.toml directly.${NC}"
    echo ""
fi

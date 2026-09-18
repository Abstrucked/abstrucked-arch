#!/bin/bash
# Build yay as a regular user; makepkg handles privileged package installation.
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOTFILES_DIR
source "$DOTFILES_DIR/lib/logging.sh"
source "$DOTFILES_DIR/lib/cleanup.sh"

DRY_RUN=false
NON_INTERACTIVE=false
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        --non-interactive|-y) NON_INTERACTIVE=true ;;
        --help|-h)
            printf 'Usage: %s [--dry-run] [--non-interactive]\n' "$0"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
    shift
done

if command_exists yay; then
    log_info "yay is already installed; skipping."
    exit 0
fi
if [[ "$DRY_RUN" == true ]]; then
    log_info "[dry-run] Would check non-root user and base-devel, clone yay, then build/install with makepkg -si."
    exit 0
fi
[[ "$EUID" -ne 0 ]] || die "yay must be built as a regular user, not root. Run this helper without sudo."
require_command pacman "yay requires Arch Linux and pacman"
require_command git "Install prerequisites first: sudo pacman -S --needed base-devel git"
require_command makepkg "Install prerequisites first: sudo pacman -S --needed base-devel git"
pacman -Q base-devel >/dev/null 2>&1 || die "Missing base-devel. Run: sudo pacman -S --needed base-devel git"

setup_cleanup_trap
create_temp_dir yay-build temp_dir || die "Failed to create yay build directory"
git clone -- https://aur.archlinux.org/yay.git "$temp_dir/yay" || die "Failed to clone yay repository"
makepkg_args=(-si)
if [[ "$NON_INTERACTIVE" == true ]]; then
    makepkg_args+=(--noconfirm)
    require_command sudo "sudo is required for unattended makepkg package installation"
    sudo -n -v || die "Unattended installation requires cached sudo credentials; run sudo -v first."
    sudo_path=$(command -v sudo) || die "Could not resolve sudo executable"
    pacman_auth_wrapper="$temp_dir/pacman-auth"
    printf '#!/bin/bash\nexec %q -n "$@"\n' "$sudo_path" > "$pacman_auth_wrapper" || die "Failed to create pacman authentication wrapper"
    chmod 700 -- "$pacman_auth_wrapper" || die "Failed to secure pacman authentication wrapper"

    # PACMAN_AUTH is a makepkg array, so pass it through a temporary config.
    makepkg_config="$temp_dir/makepkg.conf"
    makepkg_conf="${MAKEPKG_CONF:-/etc/makepkg.conf}"
    printf -v makepkg_conf_q '%q' "$makepkg_conf"
    printf -v pacman_auth_wrapper_q '%q' "$pacman_auth_wrapper"
    {
        printf 'source %s\n' "$makepkg_conf_q"
        if [[ "$makepkg_conf" == /etc/makepkg.conf ]]; then
            printf '%s\n' \
                'if [[ -r "${XDG_CONFIG_HOME:-$HOME/.config}/pacman/makepkg.conf" ]]; then' \
                '    source "${XDG_CONFIG_HOME:-$HOME/.config}/pacman/makepkg.conf"' \
                'elif [[ -r "$HOME/.makepkg.conf" ]]; then' \
                '    source "$HOME/.makepkg.conf"' \
                'fi'
        fi
        printf 'PACMAN_AUTH=(%s)\n' "$pacman_auth_wrapper_q"
    } > "$makepkg_config" || die "Failed to create makepkg configuration"
    makepkg_args+=(--config "$makepkg_config")
fi
(
    cd "$temp_dir/yay" || exit 1
    makepkg "${makepkg_args[@]}"
) || die "Failed to build/install yay. Check base-devel and the makepkg output above."
command_exists yay || die "yay installation failed: executable not found in PATH"
yay --version || die "yay verification failed"
log_success "yay installed successfully."

#!/bin/bash
# Install a Node.js version manager without executing or rewriting shell profiles.
set -euo pipefail

DOTFILES_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly DOTFILES_DIR
source "$DOTFILES_DIR/lib/logging.sh"
source "$DOTFILES_DIR/lib/cleanup.sh"

DRY_RUN=false
NON_INTERACTIVE=false
NODE_MANAGER=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --non-interactive|-y) NON_INTERACTIVE=true; shift ;;
        --manager)
            [[ $# -ge 2 ]] || die "--manager requires n, nvm, or skip"
            NODE_MANAGER="$2"; shift 2 ;;
        --help|-h)
            printf 'Usage: %s [--dry-run] [--non-interactive] [--manager n|nvm|skip]\n' "$0"
            exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done
case "$NODE_MANAGER" in
    n|nvm|skip|"") ;;
    *) die "Invalid manager: $NODE_MANAGER (expected n, nvm, or skip)" ;;
esac

if [[ -z "$NODE_MANAGER" ]]; then
    if [[ "$DRY_RUN" == true || "$NON_INTERACTIVE" == true || ! -t 0 ]]; then
        log_info "Skipping Node.js manager: no explicit --manager n or --manager nvm selected."
        exit 0
    fi
    read -r -p "Node.js manager [n/nvm/skip] (default: skip): " NODE_MANAGER || NODE_MANAGER=skip
    NODE_MANAGER="${NODE_MANAGER:-skip}"
fi
case "$NODE_MANAGER" in
    skip) log_info "Skipping Node.js manager installation."; exit 0 ;;
    n|nvm) ;;
    *) die "Invalid manager: $NODE_MANAGER (expected n, nvm, or skip)" ;;
esac

export N_PREFIX="${N_PREFIX:-$HOME/n}"
export NVM_DIR="${NVM_DIR:-${XDG_CONFIG_HOME:+$XDG_CONFIG_HOME/nvm}}"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ "$NODE_MANAGER" == n ]]; then
    [[ "$N_PREFIX" == /* ]] || die "N_PREFIX must be an absolute path"
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[dry-run] Would install/verify n at $N_PREFIX/bin/n without changing profiles."
        exit 0
    fi
    if [[ ! -f "$N_PREFIX/bin/n" || ! -x "$N_PREFIX/bin/n" ]]; then
        require_command curl
        require_command git
        require_command make "GNU make is required to install n"
        setup_cleanup_trap
        create_temp_dir n-install temp_dir || die "Failed to create n staging directory"
        installer="$temp_dir/n-install.sh"
        curl --proto '=https' --proto-redir '=https' -fsSL -o "$installer" \
            https://raw.githubusercontent.com/mklement0/n-install/stable/bin/n-install || die "Failed to download n installer"
        [[ -f "$installer" && -s "$installer" ]] || die "Empty or missing n installer"
        bash -n "$installer" || die "Invalid n installer syntax"
        # Upstream -y is unattended, -n skips profiles, and '-' installs only the manager.
        bash "$installer" -y -n - || die "n installation failed"
    fi
    [[ -f "$N_PREFIX/bin/n" && -x "$N_PREFIX/bin/n" ]] || die "n installation failed: prefix binary missing"
    export PATH="$N_PREFIX/bin:$PATH"
    "$N_PREFIX/bin/n" --version || die "n verification failed"
    log_success "n is ready at $N_PREFIX/bin/n"
    log_info "For future Bash/Zsh sessions, use these exports in your shell configuration:"
    printf 'export N_PREFIX=%q\nexport PATH="$N_PREFIX/bin:$PATH"\n' "$N_PREFIX"
else
    [[ "$NVM_DIR" == /* ]] || die "NVM_DIR must be an absolute path"
    if [[ "$DRY_RUN" == true ]]; then
        log_info "[dry-run] Would install/verify $NVM_DIR/nvm.sh without changing profiles."
        exit 0
    fi
    if [[ ! -f "$NVM_DIR/nvm.sh" || ! -s "$NVM_DIR/nvm.sh" ]]; then
        require_command curl
        require_command git
        setup_cleanup_trap
        create_temp_dir nvm-install temp_dir || die "Failed to create nvm staging directory"
        installer="$temp_dir/nvm-install.sh"
        curl --proto '=https' --proto-redir '=https' -fsSL -o "$installer" \
            https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh || die "Failed to download nvm installer"
        [[ -f "$installer" && -s "$installer" ]] || die "Empty or missing nvm installer"
        bash -n "$installer" || die "Invalid nvm installer syntax"
        mkdir -p -- "$NVM_DIR" || die "Failed to create $NVM_DIR"
        PROFILE=/dev/null METHOD=git bash "$installer" || die "nvm installation failed"
    fi
    [[ -f "$NVM_DIR/nvm.sh" && -s "$NVM_DIR/nvm.sh" ]] || die "nvm installation failed: nvm.sh missing"
    # Load only the manager in a clean child shell, not the user's shell startup files.
    bash --noprofile --norc -c '. "$NVM_DIR/nvm.sh" --no-use && command -v nvm && nvm --version' || die "nvm verification failed"
    log_success "nvm is ready at $NVM_DIR"
    log_info "For future Bash/Zsh sessions, use these lines in your shell configuration:"
    printf 'export NVM_DIR=%q\n. "$NVM_DIR/nvm.sh"\n' "$NVM_DIR"
fi

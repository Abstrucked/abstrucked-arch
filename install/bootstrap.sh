#!/bin/bash
# Standalone entry point for curl -fsSL <url> | bash.
set -euo pipefail

bootstrap_main() {
    local destination="$HOME/.dotfiles"
    local repository='https://github.com/Abstrucked/abstrucked-arch.git'

    if [[ $# -ne 0 ]]; then
        printf 'Usage: curl -fsSL <bootstrap-url> | bash\n' >&2
        return 1
    fi
    if [[ "$EUID" -eq 0 ]]; then
        printf 'Run as your regular user with sudo access, not as root.\n' >&2
        return 1
    fi
    if ! command -v pacman >/dev/null || ! command -v sudo >/dev/null; then
        printf 'This installer requires Arch Linux and sudo.\n' >&2
        return 1
    fi
    if [[ -e "$destination" || -L "$destination" ]]; then
        printf '%s already exists. To install an existing checkout, run:\n' "$destination" >&2
        printf '  cd "%s" && ./install.sh\n' "$destination" >&2
        return 1
    fi

    # The pipe contains this script; prompts must read from the terminal instead.
    if ! { exec 3</dev/tty; } 2>/dev/null; then
        printf 'Run this command from an interactive terminal.\n' >&2
        return 1
    fi
    exec 0<&3 3<&-

    printf 'Installing prerequisites, then cloning main into %s.\n' "$destination"
    sudo pacman -Syu --needed base-devel git curl
    git clone --branch main -- "$repository" "$destination"
    cd -- "$destination"
    exec bash ./install.sh
}

# Keep execution last so Bash reads the complete function before starting work.
bootstrap_main "$@"

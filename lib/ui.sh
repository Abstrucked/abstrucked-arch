#!/bin/bash
# Optional Gum UI with a plain-text fallback.

if [[ -n "${_UI_SH_LOADED:-}" ]]; then
    return 0
fi
_UI_SH_LOADED=1

source "$(dirname "${BASH_SOURCE[0]}")/logging.sh"

UI_MODE="${UI_MODE:-plain}"

ui_initialize() {
    UI_MODE=plain

    # Automation, dry runs, and redirected input must never trigger an
    # interactive package install or a terminal UI.
    if [[ "${DRY_RUN:-false}" == "true" ]]; then
        log_info "Dry run: Gum installation is disabled; using the plain-text menus."
        return 0
    fi
    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        return 0
    fi
    if [[ ! -t 0 || ! -t 1 ]]; then
        return 0
    fi

    if command_exists gum; then
        UI_MODE=gum
        return 0
    fi

    echo "Gum is not installed. It provides keyboard-driven installer menus."
    read -r -p "Install Gum from the Arch repositories now? [y/N] " response || response=n
    case "${response,,}" in
        y|yes)
            if command_exists sudo; then
                if sudo pacman -S --needed gum && command_exists gum; then
                    UI_MODE=gum
                    return 0
                fi
            elif [[ "$EUID" -eq 0 ]] && pacman -S --needed gum && command_exists gum; then
                UI_MODE=gum
                return 0
            else
                log_warn "Cannot install Gum because sudo is not available."
            fi
            log_warn "Gum installation failed; using the plain-text installer menus."
            ;;
        *)
            log_info "Using the plain-text installer menus."
            ;;
    esac
}

ui_choose_one() {
    local header=$1
    shift
    gum choose --header "$header" "$@"
}

ui_confirm() {
    gum confirm "$1"
}

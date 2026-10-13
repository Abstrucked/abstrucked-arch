#!/bin/bash
# Component metadata and the installer's explicit execution policy.

if [[ -n "${_COMPONENT_REGISTRY_SH_LOADED:-}" ]]; then
    return 0
fi
_COMPONENT_REGISTRY_SH_LOADED=1

# Format: "name|description|default_enabled|step_name". Keep MENU order.
declare -ag COMPONENTS=(
    "yay|AUR helper (yay)|true|yay"
    "packages|System packages|true|packages"
    "node|Node.js version manager|true|node"
    "stow|Symlink management (GNU Stow)|true|stow"
    "shell|Default shell (zsh or bash; requires stow)|true|shell"
    "theme|Desktop color palette|true|theme"
    "backgrounds|Desktop backgrounds|true|backgrounds"
    "tmux|Tmux configuration|true|tmux"
    "lazyvim|LazyVim Neovim distribution|true|lazyvim"
    "yubikey|YubiKey tools (optional)|false|yubikey"
)

# Execution ordering is policy, intentionally independent of menu order.
# shellcheck disable=SC2034 # consumed by install.sh's explicit dispatcher
declare -ag INSTALL_STEP_ORDER=(yay packages node yubikey stow theme backgrounds tmux shell lazyvim)

get_component_name() {
    local component=$1
    printf '%s\n' "${component%%|*}"
}

get_component_desc() {
    local component=$1 temp
    temp="${component#*|}"
    printf '%s\n' "${temp%%|*}"
}

get_component_default() {
    local component=$1 temp
    temp="${component#*|*|}"
    printf '%s\n' "${temp%%|*}"
}

get_component_step() {
    local component=$1
    printf '%s\n' "${component##*|}"
}

component_step_known() {
    local step=${1:-} component
    [[ -n "$step" ]] || return 1
    for component in "${COMPONENTS[@]}"; do
        [[ "${component##*|}" == "$step" ]] && return 0
    done
    return 1
}

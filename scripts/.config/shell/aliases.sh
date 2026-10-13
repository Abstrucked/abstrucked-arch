#!/bin/sh
# Shared aliases used by Bash and Zsh.
# shellcheck shell=sh

alias yrs='yarn run serve'
alias graph='npx graph'
alias vue='npx vue'
alias balena='"${BALENA_ETCHER:-balenaEtcher.appImage}"'
alias dev='cd -- "${DOTFILES_DEV_DIR:-$HOME/_dev}"'
alias scrot1="\"\$HOME/.local/bin/screenshot_1\""
alias scrot2="\"\$HOME/.local/bin/screenshot_2\""
alias sesh="\"\$HOME/.local/bin/tmux-sessionizer\""
alias nvim-ai="\"\$HOME/.local/bin/nvim-launcher\""
alias opencode-ai="\"\$HOME/.local/bin/opencode-launcher\""
alias create-app="\"\$HOME/.local/bin/create-app-launcher\""
alias pass-insert="\"\$HOME/.local/bin/pass-insert-utility\""

alias batt="\"\$HOME/.local/bin/batt-save-mode.sh\""
alias balanced="\"\$HOME/.local/bin/balanced-mode.sh\""
alias perf="\"\$HOME/.local/bin/perf-mode.sh\""
alias checkmode='sensors | grep -E "Tctl|Tdie|Package" && grep MHz /proc/cpuinfo | head -1'

alias _omen="\"\$HOME/.local/bin/tailscale-ssh\""

# Yazi wrapper: cd to the directory Yazi was in when it exits (q; Q skips this).
y() {
    y_cwd_file=$(mktemp -t yazi-cwd.XXXXXX) || return 1
    yazi "$@" --cwd-file="$y_cwd_file"
    y_status=$?
    if y_cwd=$(cat -- "$y_cwd_file") && [ -n "$y_cwd" ] && [ "$y_cwd" != "$PWD" ]; then
        cd -- "$y_cwd" || y_status=1
    fi
    rm -f -- "$y_cwd_file"
    unset y_cwd_file y_cwd
    return "$y_status"
}

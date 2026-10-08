#!/bin/sh
# Source from the bar or TUI wrapper. Keep the decrypted key in the child
# process environment only; GPG's agent owns the passphrase cache.
# pass treats PASSWORD_STORE_GPG_OPTS as whitespace-separated arguments, not
# shell syntax. Match that contract without eval or pathname expansion.
ai_usage_gpg_options() (
    ai_usage_mode=$1
    ai_usage_options=''
    set -f
    # shellcheck disable=SC2086 # pass intentionally accepts a whitespace word list
    set -- ${PASSWORD_STORE_GPG_OPTS:-}
    while [ "$#" -gt 0 ]; do
        case "$1" in
        --pinentry-mode)
            shift
            if [ "$#" -gt 0 ]; then
                case "$1" in -*) ;; *) shift ;; esac
            fi
            ;;
        --pinentry-mode=*) shift ;;
        *)
            ai_usage_options="${ai_usage_options:+$ai_usage_options }$1"
            shift
            ;;
        esac
    done
    printf '%s\n' "${ai_usage_options:+$ai_usage_options }--pinentry-mode $ai_usage_mode"
)

# Status: 0 configured, 1 locked/unavailable, 2 missing, 64 invalid mode.
ai_usage_load_openrouter_key() {
    case "${1:-background}" in interactive|background) ;; *) return 64 ;; esac
    [ -n "${OPENROUTER_API_KEY:-}" ] && return 0

    # Respect keys configured directly in upstream, including custom env names.
    if ai-usagebar settings show 2>/dev/null | jq -e '.keys[] | select(.id == "openrouter") | .configured' >/dev/null 2>&1; then
        return 0
    fi

    command -v pass >/dev/null 2>&1 || return 2
    [ -f "${PASSWORD_STORE_DIR:-$HOME/.password-store}/ai/openrouter_api_key.gpg" ] || return 2

    case "${1:-background}" in
    interactive)
        # pinentry-curses needs the new dashboard terminal, not the bar's TTY.
        GPG_TTY="$(tty)" || return 1
        export GPG_TTY
        ai_usage_gpg_mode=ask
        ;;
    background)
        # Never show pinentry from a timer or hover refresh.
        ai_usage_gpg_mode=error
        ;;
    esac

    if ai_usage_key="$(PASSWORD_STORE_GPG_OPTS="$(ai_usage_gpg_options "$ai_usage_gpg_mode")" pass show ai/openrouter_api_key 2>/dev/null)" && [ -n "$ai_usage_key" ]; then
        export OPENROUTER_API_KEY="$ai_usage_key"
        unset ai_usage_key ai_usage_gpg_mode
        return 0
    fi
    unset ai_usage_key ai_usage_gpg_mode
    return 1
}

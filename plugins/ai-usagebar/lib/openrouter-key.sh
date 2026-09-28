#!/bin/sh
# Source from the bar or TUI wrapper. Keep the decrypted key in the child
# process environment only; GPG's agent owns the passphrase cache.
ai_usage_load_openrouter_key() {
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
    *) return 2 ;;
    esac

    if ai_usage_key="$(PASSWORD_STORE_GPG_OPTS="${PASSWORD_STORE_GPG_OPTS:-} --pinentry-mode $ai_usage_gpg_mode" pass show ai/openrouter_api_key 2>/dev/null)" && [ -n "$ai_usage_key" ]; then
        export OPENROUTER_API_KEY="$ai_usage_key"
        unset ai_usage_key ai_usage_gpg_mode
        return 0
    fi
    unset ai_usage_key ai_usage_gpg_mode
    return 1
}

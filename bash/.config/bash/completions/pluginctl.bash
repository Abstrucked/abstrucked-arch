# Completion for pluginctl (see ~/.dotfiles/plugins).
#
# `enable` only offers plugins that are off and `disable` only those that are
# on, both read from `pluginctl list`, whose lines are "[x] <id> <name>".

_pluginctl_ids() {
    # $1 is the mark to match: "x" for enabled plugins, " " for disabled ones.
    pluginctl list 2>/dev/null | sed -n "s/^\\[$1\\] \\([^ ]*\\).*/\\1/p"
}

_pluginctl() {
    local cur prev
    COMPREPLY=()
    cur=${COMP_WORDS[COMP_CWORD]}
    prev=${COMP_WORDS[COMP_CWORD - 1]}

    if ((COMP_CWORD == 1)); then
        mapfile -t COMPREPLY < <(
            compgen -W "list enable disable refresh help" -- "$cur"
        )
        return
    fi

    # Only enable and disable take an argument, and each takes the plugins the
    # other one left.
    if ((COMP_CWORD == 2)); then
        case $prev in
            enable) mapfile -t COMPREPLY < <(compgen -W "$(_pluginctl_ids ' ')" -- "$cur") ;;
            disable) mapfile -t COMPREPLY < <(compgen -W "$(_pluginctl_ids x)" -- "$cur") ;;
        esac
    fi
}

complete -F _pluginctl pluginctl

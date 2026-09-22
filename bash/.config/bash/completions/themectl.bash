# Completion for themectl (see ~/.dotfiles/themes).
#
# The first word is a subcommand; `set` and `render` take a theme name, which
# themectl itself can list, so the names never have to be remembered.

_themectl() {
    local cur prev
    COMPREPLY=()
    cur=${COMP_WORDS[COMP_CWORD]}
    prev=${COMP_WORDS[COMP_CWORD - 1]}

    if ((COMP_CWORD == 1)); then
        mapfile -t COMPREPLY < <(
            compgen -W "list current set next apply render help" -- "$cur"
        )
        return
    fi

    # Only the theme-taking subcommands have a second argument.
    if ((COMP_CWORD == 2)); then
        case $prev in
            set | render)
                mapfile -t COMPREPLY < <(
                    compgen -W "$(themectl list 2>/dev/null)" -- "$cur"
                )
                ;;
        esac
    fi
}

complete -F _themectl themectl

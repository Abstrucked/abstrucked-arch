# Completion for themectl (see ~/.dotfiles/themes).
#
# Layouts (themes) and palettes are independent: after `set`, plain words
# complete layout names (read-only `themectl list`) while the value of
# --colors completes palette names (read-only `themectl list --colors`).
# `render` previews palettes only, and list/current/next take --colors as a
# bare mode flag with no value. Nothing here mutates state.
#
# COMP_WORDBREAKS splits --colors=VALUE into "--colors", "=" and VALUE, so
# both spellings are normalized here without needing bash-completion.

_themectl() {
    local cur prev cmd word next
    local colors_count=0 operands=0 i
    COMPREPLY=()
    cur=${COMP_WORDS[COMP_CWORD]}

    if ((COMP_CWORD == 1)); then
        mapfile -t COMPREPLY < <(
            compgen -W "list current set next apply render help" -- "$cur"
        )
        return
    fi
    cmd=${COMP_WORDS[1]}
    prev=${COMP_WORDS[COMP_CWORD - 1]}

    # Count the words already typed as logical tokens: "--colors" "=" VALUE,
    # "--colors" VALUE and "--colors=VALUE" are all one flag with a palette
    # value, never extra operands.
    for ((i = 2; i < COMP_CWORD; i++)); do
        word=${COMP_WORDS[i]}
        case $word in
            --colors)
                colors_count=$((colors_count + 1))
                next=$((i + 1))
                if [[ $cmd == set || $cmd == render ]] && ((next < COMP_CWORD)); then
                    if [[ ${COMP_WORDS[next]} == "=" ]]; then
                        ((i += 1)) # the '=' of --colors=VALUE
                        next=$((i + 1))
                        ((next < COMP_CWORD)) && [[ ${COMP_WORDS[next]} != "=" ]] && ((i += 1))
                    else
                        ((i += 1)) # the separate value of --colors VALUE
                    fi
                fi
                ;;
            --colors=*) colors_count=$((colors_count + 1)) ;;
            =) ;; # Always consumed together with its --colors.
            -*) ;; # Unknown flags get no candidates.
            *) operands=$((operands + 1)) ;;
        esac
    done

    # --colors=VALUE as a single word (callers with '=' unbroken).
    if [[ $cur == --colors=* ]]; then
        if [[ $cmd == set || $cmd == render ]] && ((colors_count == 0)); then
            local value=${cur#--colors=}
            mapfile -t COMPREPLY < <(compgen -W "$(themectl list --colors 2>/dev/null)" -- "$value")
            COMPREPLY=("${COMPREPLY[@]/#/--colors=}")
        fi
        return
    fi

    # The palette value of --colors: split ("--colors" "=" VALUE, or cur is
    # the '=' just typed) or separate ("--colors" VALUE). Candidates are the
    # plain palette names - readline replaces only the value fragment after
    # the '=', so no '--colors=' prefix is duplicated onto it.
    local value_slot=0 value=""
    if [[ $cmd == set || $cmd == render ]]; then
        if [[ ${COMP_WORDS[COMP_CWORD - 2]:-} == --colors && $prev == "=" ]]; then
            value_slot=1
            value=$cur
        elif [[ $prev == --colors ]]; then
            value_slot=1
            [[ $cur == "=" ]] || value=$cur
        fi
    fi
    if ((value_slot)); then
        # Only the first --colors takes a value; a duplicate gets nothing.
        if ((colors_count == 1)); then
            mapfile -t COMPREPLY < <(compgen -W "$(themectl list --colors 2>/dev/null)" -- "$value")
        fi
        return
    fi

    local -a names
    case $cmd in
        set)
            # One theme and one --colors at most; the other slot stays open.
            if ((colors_count == 0)); then
                mapfile -t COMPREPLY < <(compgen -W "--colors" -- "$cur")
            fi
            if ((operands == 0)); then
                mapfile -t names < <(compgen -W "$(themectl list 2>/dev/null)" -- "$cur")
                COMPREPLY+=("${names[@]}")
            fi
            ;;
        render | list | current | next)
            # --colors is the only thing left: a palette for render, a bare
            # mode flag for list/current/next. Never layout names.
            if ((colors_count == 0)); then
                mapfile -t COMPREPLY < <(compgen -W "--colors" -- "$cur")
            fi
            ;;
    esac
}

complete -F _themectl themectl

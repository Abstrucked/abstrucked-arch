#!/bin/sh
# Shared environment defaults for interactive shells and X sessions.

XDG_CONFIG_HOME=${XDG_CONFIG_HOME:-$HOME/.config}
export XDG_CONFIG_HOME

EDITOR=${EDITOR:-nvim}
VISUAL=${VISUAL:-$EDITOR}
N_PREFIX=${N_PREFIX:-$HOME/n}
ASDF_DATA_DIR=${ASDF_DATA_DIR:-$HOME/.asdf}
PNPM_HOME=${PNPM_HOME:-$HOME/.local/share/pnpm}
THEME_BG_DIR=${THEME_BG_DIR:-$HOME/.backgrounds}
export EDITOR VISUAL N_PREFIX ASDF_DATA_DIR PNPM_HOME THEME_BG_DIR

# Assemble the managed prefix in order, suppressing exact duplicates even when
# caller-provided runtime directories overlap.
_shell_defaults_managed=
for _shell_defaults_candidate in "$HOME/.local/bin" "$N_PREFIX/bin" \
    "$ASDF_DATA_DIR/shims" "$PNPM_HOME"; do
    case ":$_shell_defaults_managed:" in
        *:"$_shell_defaults_candidate":*) ;;
        *)
            if [ -n "$_shell_defaults_managed" ]; then
                _shell_defaults_managed=$_shell_defaults_managed:$_shell_defaults_candidate
            else
                _shell_defaults_managed=$_shell_defaults_candidate
            fi
            ;;
    esac
done

# Preserve every non-managed PATH entry (including intentional empty entries).
_shell_defaults_path=$_shell_defaults_managed
_shell_defaults_rest=${PATH-}
_shell_defaults_done=false

while [ "$_shell_defaults_done" = false ]; do
    case $_shell_defaults_rest in
        *:*)
            _shell_defaults_entry=${_shell_defaults_rest%%:*}
            _shell_defaults_rest=${_shell_defaults_rest#*:}
            ;;
        *)
            _shell_defaults_entry=$_shell_defaults_rest
            _shell_defaults_done=true
            ;;
    esac

    case ":$_shell_defaults_managed:" in
        *:"$_shell_defaults_entry":*) ;;
        *) _shell_defaults_path=$_shell_defaults_path:$_shell_defaults_entry ;;
    esac
done

PATH=$_shell_defaults_path
export PATH

unset _shell_defaults_managed _shell_defaults_path _shell_defaults_rest
unset _shell_defaults_done _shell_defaults_entry _shell_defaults_candidate

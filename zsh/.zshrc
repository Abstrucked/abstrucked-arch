#autoload -Uz compinit

#comptinit

# Global theme setting
export THEME=catppuccin-mocha
export THEME_BG_DIR="$HOME/.backgrounds"
# Enable Powerlevel10k instant prompt. Should stay close to the top of ~/.zshrc.
# Initialization code that may require console input (password prompts, [y/n]
# confirmations, etc.) must go above this block; everything else may go below.
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

source /usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme
source ~/zsh-autocomplete/zsh-autocomplete.plugin.zsh
#plugins=(zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)
# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

#zstyle '*:compinit' arguments -D -i -u -C -w
#zstyle ':completion:*' menu select
#zstyle ':completion::complete:*' gain-privileges 1
#bindkey '\t' menu-select "$terminfo[kcbt]" menu-select
#bindkey -M menuselect '\t' menu-complete "$terminfo[kcbt]" reverse-menu-complete

# Home key (go to beginning of line)
bindkey '^[[H' beginning-of-line
bindkey '^[OH' beginning-of-line  # For some terminals

# End key (go to end of line)
bindkey '^[[F' end-of-line
bindkey '^[OF' end-of-line        # For some terminals

# Ctrl + Left (backward-word)
bindkey '^[[1;5D' backward-word
bindkey '^[[5D' backward-word

# Ctrl + Right (forward-word)
bindkey '^[[1;5C' forward-word
bindkey '^[[5C' forward-word


HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt appendhistory

alias yrs='yarn run serve'
alias graph='npx graph'
alias vue='npx vue'
alias balena='/usr/bin/balenaEtcher.appImage'
alias dev='cd ~/_dev/'
alias scrot1="$HOME/.local/bin/screenshot_1"
alias scrot2="$HOME/.local/bin/screenshot_2"
alias sesh="$HOME/.local/bin/tmux-sessionizer"
alias nvim-ai="$HOME/.local/bin/nvim-launcher"
################################################################################





export EDITOR='nvim'
export VISUAL='gedit'

export N_PREFIX="$HOME/n"; [[ :$PATH: == *":$N_PREFIX/bin:"* ]] || PATH+=":$N_PREFIX/bin"  # Added by n-install (see http://git.io/n-install-repo).

export PATH="$HOME/.local/bin:$PATH"

# Set GTK dark theme
export GTK_THEME=Adwaita:dark

# Set Qt to use GTK theme
export QT_QPA_PLATFORMTHEME=gtk2

# Set QT5 configuration tool
export QT_QPA_PLATFORMTHEME=qt5ct

# bun completions
[ -s "/home/abstrucked/.bun/_bun" ] && source "/home/abstrucked/.bun/_bun"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet
###-begin-pm2-completion-###
### credits to npm for the completion file model
#
# Installation: pm2 completion >> ~/.bashrc  (or ~/.zshrc)
#

COMP_WORDBREAKS=${COMP_WORDBREAKS/=/}
COMP_WORDBREAKS=${COMP_WORDBREAKS/@/}
export COMP_WORDBREAKS

if type complete &>/dev/null; then
  _pm2_completion () {
    local si="$IFS"
    IFS=$'\n' COMPREPLY=($(COMP_CWORD="$COMP_CWORD" \
                           COMP_LINE="$COMP_LINE" \
                           COMP_POINT="$COMP_POINT" \
                           pm2 completion -- "${COMP_WORDS[@]}" \
                           2>/dev/null)) || return $?
    IFS="$si"
  }
  complete -o default -F _pm2_completion pm2
elif type compctl &>/dev/null; then
  _pm2_completion () {
    local cword line point words si
    read -Ac words
    read -cn cword
    let cword-=1
    read -l line
    read -ln point
    si="$IFS"
    IFS=$'\n' reply=($(COMP_CWORD="$cword" \
                       COMP_LINE="$line" \
                       COMP_POINT="$point" \
                       pm2 completion -- "${words[@]}" \
                       2>/dev/null)) || return $?
    IFS="$si"
  }
  compctl -K _pm2_completion + -f + pm2
fi
###-end-pm2-completion-###

# Turso
export PATH="$PATH:/home/abstrucked/.turso"

export PATH="${HOME}/.local/bin:$PATH"

export PATH="${ASDF_DATA_DIR:-$HOME/.asdf}/shims:$PATH"
# Alias for running starkup installer
alias starkup="curl --proto '=https' --tlsv1.2 -sSf https://sh.starkup.sh | sh -s --"

# BEGIN SCARB COMPLETIONS
_scarb() {
  if ! scarb completions zsh >/dev/null 2>&1; then
    return 0
  fi
  eval "$(scarb completions zsh)"
  _scarb "$@"
}

autoload -Uz compinit && compinit
compdef _scarb scarb
# END SCARB COMPLETIONS

# BEGIN FOUNDRY COMPLETIONS
_snforge() {
  if ! snforge completions zsh >/dev/null 2>&1; then
    return 0
  fi
  eval "$(snforge completions zsh)"
  _snforge "$@"
}

_sncast() {
  if ! sncast completions zsh >/dev/null 2>&1; then
    return 0
  fi
  eval "$(sncast completions zsh)"
  _sncast "$@"
}

compdef _snforge snforge
compdef _sncast sncast
# END FOUNDRY COMPLETIONS

# dojo
. "/home/abstrucked/.dojo/env"


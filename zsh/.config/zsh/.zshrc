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
source "${XDG_CONFIG_DIR}/zsh/zsh-autocomplete/zsh-autocomplete.plugin.zsh"


# Source custom aliases
source "${XDG_CONFIG_DIR}/zsh/aliases.zsh"

#plugins=(zsh-autosuggestions zsh-syntax-highlighting fast-syntax-highlighting zsh-autocomplete)
# To customize prompt, run `p10k configure` or edit ~/.p10k.zsh.
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

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


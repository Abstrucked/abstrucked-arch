#!/bin/zsh
# ═══════════════════════════════════════════════════════════════
# Powerlevel10k Instant Prompt (must stay at top)
# ═══════════════════════════════════════════════════════════════
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

# ═══════════════════════════════════════════════════════════════
# Environment Variables
# ═══════════════════════════════════════════════════════════════
export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
export THEME=catppuccin-mocha
export THEME_BG_DIR="$HOME/.backgrounds"
export EDITOR='nvim'
export VISUAL='nvim'
export GTK_THEME=Adwaita:dark
export QT_QPA_PLATFORMTHEME=qt5ct

# ═══════════════════════════════════════════════════════════════
# PATH Management (consolidated)
# ═══════════════════════════════════════════════════════════════
export PNPM_HOME="${HOME}/.local/share/pnpm"
export ASDF_DATA_DIR="${HOME}/.asdf"
export N_PREFIX="${HOME}/n"

path=(
  "$HOME/.local/bin"
  "$N_PREFIX"
  "${ASDF_DATA_DIR}/shims"
  "$PNPM_HOME"
  $path
)
typeset -U path

# ═══════════════════════════════════════════════════════════════
# Plugins
# ═══════════════════════════════════════════════════════════════
source /usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme
source "${XDG_CONFIG_HOME}/zsh/zsh-autocomplete/zsh-autocomplete.plugin.zsh"

# Powerlevel10k configuration
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh
typeset -g POWERLEVEL9K_INSTANT_PROMPT=quiet

# ═══════════════════════════════════════════════════════════════
# Key Bindings
# ═══════════════════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════════════════
# History
# ═══════════════════════════════════════════════════════════════
HISTFILE=~/.zsh_history
HISTSIZE=10000
SAVEHIST=10000
setopt appendhistory

# ═══════════════════════════════════════════════════════════════
# Completions
# ═══════════════════════════════════════════════════════════════
fpath=(${ASDF_DATA_DIR}/completions $fpath)
autoload -Uz compinit && compinit

# ═══════════════════════════════════════════════════════════════
# Source Config Files
# ═══════════════════════════════════════════════════════════════
source "${XDG_CONFIG_HOME}/zsh/aliases.zsh"

# ═══════════════════════════════════════════════════════════════
# Dart CLI Completion (if installed)
# ═══════════════════════════════════════════════════════════════
[[ -f "$HOME/.config/.dart-cli-completion/zsh-config.zsh" ]] && \
  source "$HOME/.config/.dart-cli-completion/zsh-config.zsh"

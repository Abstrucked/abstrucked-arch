#!/bin/bash
# Load API keys from pass. This is the canonical loader at ~/load-api-keys.sh;
# pass-insert-utility appends any additional exports to this file.
# To load keys into the current shell: source ~/load-api-keys.sh
load_api_keys() {
  local password_store_dir="${PASSWORD_STORE_DIR:-$HOME/.password-store}"
  local loaded_api_key_count=0 value

  if ! command -v pass &>/dev/null; then
    echo "Error: pass is not installed" >&2
    echo "Install with: sudo pacman -S pass" >&2
    return 1
  fi

  if [[ ! -f "$password_store_dir/.gpg-id" ]]; then
    echo "Error: pass is not initialized" >&2
    echo "Run 'pass init <GPG_KEY_ID>' to initialize" >&2
    return 1
  fi

  # Keep literal export assignments: pass-insert-utility uses them to avoid
  # appending duplicate exports for keys already managed here.
  unset OPENAI_API_KEY OPENROUTER_API_KEY
  if value="$(pass show ai/openai_api_key 2>/dev/null)" && [[ -n "$value" ]]; then
    export OPENAI_API_KEY="$value"
    ((loaded_api_key_count += 1))
  else
    echo "Warning: could not load ai/openai_api_key from pass; OPENAI_API_KEY is unset." >&2
  fi

  if value="$(pass show ai/openrouter_api_key 2>/dev/null)" && [[ -n "$value" ]]; then
    export OPENROUTER_API_KEY="$value"
    ((loaded_api_key_count += 1))
  else
    echo "Warning: could not load ai/openrouter_api_key from pass; OPENROUTER_API_KEY is unset." >&2
  fi

  if ((loaded_api_key_count == 0)); then
    echo "Error: no API keys could be loaded from pass" >&2
    return 1
  fi
}

load_api_keys

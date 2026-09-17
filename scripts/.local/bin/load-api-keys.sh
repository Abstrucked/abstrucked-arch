#!/bin/bash
# Load API keys from pass password manager

# Check if pass is installed
if ! command -v pass &>/dev/null; then
  echo "Error: pass is not installed" >&2
  echo "Install with: sudo pacman -S pass" >&2
  exit 1
fi

# Check if pass is initialized
if [[ ! -f "$HOME/.password-store/.gpg-id" ]]; then
  echo "Error: pass is not initialized" >&2
  echo "Run 'pass init <GPG_KEY_ID>' to initialize" >&2
  exit 1
fi

# Load API keys
export OPENAI_API_KEY=$(pass ai/openai_api_key 2>/dev/null || echo "")
export OPENROUTER_API_KEY=$(pass ai/openrouter_api_key 2>/dev/null || echo "")

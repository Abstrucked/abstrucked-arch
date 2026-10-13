#!/bin/bash
# Compatibility entry point for the balanced power profile.

set -euo pipefail

script_path=$(readlink -f -- "$0")
exec "$(dirname -- "$script_path")/power-mode" balanced "$@"

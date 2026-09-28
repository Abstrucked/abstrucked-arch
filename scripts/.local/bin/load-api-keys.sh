#!/bin/bash
# Keep one API-key loader: this path delegates to the home script so launchers
# also receive exports added there by pass-insert-utility.
# shellcheck disable=SC1090 # Resolved by the installed home symlink.
source "$HOME/load-api-keys.sh"

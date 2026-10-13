#!/bin/bash
# Shared, read-only backup-root validation for installers and config imports.

if [[ -n "${_BACKUP_PATHS_SH_LOADED:-}" ]]; then
    return 0
fi
_BACKUP_PATHS_SH_LOADED=1

# Resolve this once while sourcing; callers may change their working directory.
_DOTFILES_BACKUP_REPOSITORY="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"

# Print one canonical path on success. Diagnostics belong on stderr so callers
# can capture the result without importing logging or changing global flags.
dotfiles_resolve_backup_root() {
    local root=${1:-${DOTFILES_BACKUP_ROOT:-$HOME/.dotfiles-backups}}
    local canonical lexical
    if [[ "$root" != /* ]]; then
        printf '%s\n' 'Error: backup root must be an absolute path (DOTFILES_BACKUP_ROOT)' >&2
        return 1
    fi
    if [[ "$root" == *$'\n'* || "$root" == *$'\r'* ]]; then
        printf '%s\n' 'Error: backup root must not contain a newline or carriage return' >&2
        return 1
    fi
    if ! canonical=$(realpath -m -- "$root") || ! lexical=$(realpath -ms -- "$root"); then
        printf '%s\n' 'Error: cannot resolve backup root' >&2
        return 1
    fi
    # Check both spellings: a checkout-local symlink to an external directory
    # must not turn the checkout itself into a backup entry point either.
    if [[ "$canonical" == "$_DOTFILES_BACKUP_REPOSITORY" ||
        "$canonical/" == "$_DOTFILES_BACKUP_REPOSITORY/"* ||
        "$lexical" == "$_DOTFILES_BACKUP_REPOSITORY" ||
        "$lexical/" == "$_DOTFILES_BACKUP_REPOSITORY/"* ]]; then
        printf '%s\n' 'Error: backup root must be outside the dotfiles repository' >&2
        return 1
    fi
    printf '%s\n' "$canonical"
}

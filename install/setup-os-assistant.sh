#!/bin/bash
# Stow the optional os-assistant package into a target directory.
#
#   install/setup-os-assistant.sh                 preview (the default)
#   install/setup-os-assistant.sh --apply         create the symlinks
#   install/setup-os-assistant.sh --apply --target /some/home
#
# This helper only links the os-assistant package with GNU Stow. It installs no
# packages, downloads nothing, enables no services, and never elevates
# privileges. Preview is the default and changes nothing on disk; links are
# created only with --apply. Directories are never folded into single symlinks
# (--no-folding) so existing dotfile directories keep working.
set -euo pipefail

die() {
    printf 'setup-os-assistant: %s\n' "$*" >&2
    exit 1
}

if ! command -v realpath >/dev/null 2>&1; then
    die "realpath is required"
fi

SCRIPT="$(realpath -- "${BASH_SOURCE[0]}")"
REPO="$(dirname -- "$(dirname -- "$SCRIPT")")"
PACKAGE=os-assistant
TARGET="${HOME:-}"
APPLY=false
DRY_RUN=false
declare -r SCRIPT REPO PACKAGE

usage() {
    cat <<EOF
Usage: install/setup-os-assistant.sh [--apply] [--dry-run] [--target DIR]

Link the optional $PACKAGE package from $REPO with GNU Stow.

  --apply       create the symlinks (the default is a preview that changes nothing)
  --dry-run     preview only; same as the default
  --target DIR  link into DIR (absolute path; default: \$HOME)
  -h, --help    show this help

Preview runs "stow --simulate --verbose --no-folding"; --apply runs
"stow --no-folding". Existing conflicting files make either mode fail, except
an existing personal config.toml, which is kept and not linked.
EOF
}

if [[ "$EUID" -eq 0 ]]; then
    die "run as your regular user, not as root"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
    --apply) APPLY=true ;;
    --dry-run) DRY_RUN=true ;;
    --target)
        shift
        [[ $# -gt 0 ]] || die "--target needs a directory"
        TARGET="$1"
        ;;
    --target=*) TARGET="${1#--target=}" ;;
    -h | --help)
        usage
        exit 0
        ;;
    *)
        usage >&2
        die "unknown argument: $1"
        ;;
    esac
    shift
done

if [[ "$APPLY" == true && "$DRY_RUN" == true ]]; then
    die "--apply and --dry-run are mutually exclusive"
fi

[[ "$TARGET" == /* ]] || die "--target must be an absolute path"
[[ -d "$TARGET" ]] || die "--target is not a directory: $TARGET"
[[ -d "$REPO/$PACKAGE" ]] || die "package not found: $REPO/$PACKAGE"
command -v stow >/dev/null 2>&1 || die "GNU Stow is required"

# A personal regular-file config is kept as-is: stow would otherwise abort on it.
# Existing symlinks and every other conflict are handled by stow as usual.
STOW_ARGS=(--no-folding --dir="$REPO" --target="$TARGET")
USER_CONFIG="$TARGET/.config/os-assistant/config.toml"
if [[ -f "$USER_CONFIG" && ! -L "$USER_CONFIG" ]]; then
    STOW_ARGS+=(--ignore='config\.toml')
    printf 'Keeping your existing ~/.config/os-assistant/config.toml (not linked to the repository copy).\n'
fi

if [[ "$APPLY" == true ]]; then
    printf 'Linking %s into %s.\n' "$PACKAGE" "$TARGET"
    stow "${STOW_ARGS[@]}" "$PACKAGE" ||
        die "stow failed (conflicts with existing files?)"
    printf 'Linked. Run %s/.local/bin/os-assistant --doctor to check it.\n' "$TARGET"
else
    printf 'Preview only; nothing is linked. Re-run with --apply to link %s into %s.\n' \
        "$PACKAGE" "$TARGET"
    stow --simulate --verbose "${STOW_ARGS[@]}" "$PACKAGE" ||
        die "stow failed (conflicts with existing files?)"
fi

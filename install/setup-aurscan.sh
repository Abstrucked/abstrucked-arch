#!/bin/bash
# Install the aurscan AUR pre-build scanner and wire it into yay.
#
#   install/setup-aurscan.sh                 preview (the default)
#   install/setup-aurscan.sh --apply         build, install and link the yay hook
#   install/setup-aurscan.sh --apply --target /some/home
#
# aurscan is built from install/aurscan/PKGBUILD, a local copy pinned to one
# reviewed upstream commit. makepkg runs as your regular user and prompts for
# sudo itself when it installs build dependencies and the package; this helper
# never calls sudo, never edits pacman.conf and never adopts existing files.
# The yay package (init.lua hook) is linked with GNU Stow (--no-folding) and is
# refused if you already have a personal ~/.config/yay/init.lua.
set -euo pipefail

die() {
    printf 'setup-aurscan: %s\n' "$*" >&2
    exit 1
}

if ! command -v realpath >/dev/null 2>&1; then
    die "realpath is required"
fi

SCRIPT="$(realpath -- "${BASH_SOURCE[0]}")"
REPO="$(dirname -- "$(dirname -- "$SCRIPT")")"
PACKAGE=yay
PKGBUILD="$REPO/install/aurscan/PKGBUILD"
TARGET="${HOME:-}"
APPLY=false
DRY_RUN=false
BUILD=true
declare -r SCRIPT REPO PACKAGE PKGBUILD

usage() {
    cat <<EOF
Usage: install/setup-aurscan.sh [--apply] [--dry-run] [--no-build] [--target DIR]

Install aurscan (static-rules AUR pre-build scanner) and link the $PACKAGE stow
package, whose init.lua makes yay scan every AUR package before it is built.

  --apply       build/install aurscan and link the hook (default: preview only)
  --dry-run     preview only; same as the default
  --no-build    skip the aurscan build; only link the $PACKAGE package
  --target DIR  link into DIR (absolute path; default: \$HOME)
  -h, --help    show this help

The build runs "makepkg -sirc --needed" on install/aurscan/PKGBUILD in a fresh
temporary directory, as your user; makepkg asks for sudo itself (-r removes the
Go toolchain again afterwards). The build is skipped if aurscan already reports
the pinned version. Linking runs "stow --no-folding"; an existing regular
~/.config/yay/init.lua is never touched: merge the hook into it by hand.
EOF
}

if [[ "$EUID" -eq 0 ]]; then
    die "run as your regular user, not as root"
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
    --apply) APPLY=true ;;
    --dry-run) DRY_RUN=true ;;
    --no-build) BUILD=false ;;
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
[[ -f "$PKGBUILD" ]] || die "PKGBUILD not found: $PKGBUILD"
command -v stow >/dev/null 2>&1 || die "GNU Stow is required"

INIT_LUA="$TARGET/.config/yay/init.lua"
if [[ -e "$INIT_LUA" && ! -L "$INIT_LUA" ]]; then
    die "$INIT_LUA already exists; not touching it. Merge the aurscan block from $REPO/$PACKAGE/.config/yay/init.lua into it by hand (keep the '>>> aurscan begin' / '<<< aurscan end' markers), then re-run with --no-build if aurscan is already installed."
fi

PKGVER="$(sed -n 's/^pkgver=//p' "$PKGBUILD")"
[[ -n "$PKGVER" ]] || die "cannot read pkgver from $PKGBUILD"

need_build=false
if [[ "$BUILD" == true ]]; then
    if command -v aurscan >/dev/null 2>&1 &&
        aurscan --version 2>/dev/null | grep -qF "v$PKGVER"; then
        printf 'aurscan v%s is already installed; skipping the build.\n' "$PKGVER"
    else
        need_build=true
    fi
fi

if [[ "$need_build" == true ]]; then
    for tool in pacman makepkg git; do
        command -v "$tool" >/dev/null 2>&1 || die "$tool is required to build aurscan"
    done
fi

build_aurscan() {
    local workdir status=0
    workdir="$(mktemp -d)"
    cp -- "$PKGBUILD" "$workdir/PKGBUILD"
    printf 'Building aurscan v%s in %s (makepkg will ask for sudo).\n' "$PKGVER" "$workdir"
    (cd "$workdir" && makepkg -sirc --needed) || status=$?
    rm -rf -- "$workdir"
    [[ "$status" -eq 0 ]] || die "makepkg failed"
}

if [[ "$APPLY" == true ]]; then
    if [[ "$need_build" == true ]]; then
        build_aurscan
    fi
    printf 'Linking %s into %s.\n' "$PACKAGE" "$TARGET"
    stow --no-folding -d "$REPO" -t "$TARGET" "$PACKAGE" ||
        die "stow failed (conflicts with existing files?)"
    printf 'Done. yay now scans AUR packages with aurscan (static rules only) before building.\n'
else
    printf 'Preview only; nothing is built or linked. Re-run with --apply to proceed.\n'
    if [[ "$need_build" == true ]]; then
        printf 'Would build aurscan v%s from %s:\n  makepkg -sirc --needed   (in a fresh temporary directory, as your user)\n' \
            "$PKGVER" "$PKGBUILD"
    fi
    printf 'Would link %s into %s:\n' "$PACKAGE" "$TARGET"
    stow --simulate --verbose --no-folding -d "$REPO" -t "$TARGET" "$PACKAGE" ||
        die "stow failed (conflicts with existing files?)"
fi

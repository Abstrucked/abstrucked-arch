#!/bin/bash
# Bootstrap script to copy existing configurations from ~/.config to dotfiles structure
# This is a run-once script to help set up the dotfiles folder with existing configs

set -euo pipefail

# Resolve the repository from the script location so imports do not depend on
# the caller's working directory.
BOOTSTRAP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOTSTRAP_BACKUP_ROOT="${DOTFILES_BACKUP_ROOT:-$HOME/.dotfiles-backups}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration mappings
declare -A CONFIG_MAPPINGS=(
  ["alacritty"]="alacritty/.config/alacritty"
  ["awesome"]="awesome/.config/awesome"
  ["btop"]="btop/.config/btop"
  ["nvim"]="nvim/.config/nvim"
  ["picom"]="picom/.config/picom"
  ["pcmanfm"]="pcmanfm/.config/pcmanfm"
)

# Home directory dotfiles
declare -A HOME_MAPPINGS=(
  [".zshrc"]="zsh/.zshrc"
  [".p10k.zsh"]="zsh/.p10k.zsh"
  [".tmux.conf"]="config/tmux/tmux.conf"
  ["load-api-keys.sh"]="scripts/load-api-keys.sh"
)

# SSH config
SSH_CONFIG_SOURCE="$HOME/.ssh/config"
SSH_CONFIG_DEST="ssh/.ssh/config"

# Script variables
DRY_RUN=false
AUTO_YES=false
FORCE_SENSITIVE=false
COPIED_COUNT=0
SKIPPED_COUNT=0
SKIPPED_SENSITIVE_COUNT=0
FAILED_COUNT=0

# Functions
print_header() {
  echo -e "${BLUE}🔧 Dotfiles Bootstrap Script${NC}"
  echo -e "${BLUE}===============================${NC}"
  echo -e "${CYAN}This script helps copy your existing configurations to the dotfiles structure.${NC}"
  echo ""
}

print_usage() {
  echo "Usage: $0 [OPTIONS]"
  echo ""
  echo "Options:"
  echo "  --dry-run           Show what would be copied without making changes"
  echo "  --yes               Automatically answer 'yes' to all prompts (dangerous!)"
  echo "  --force-sensitive   Copy configs even if they contain sensitive files (dangerous!)"
  echo "  --help              Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0                      # Interactive mode (recommended)"
  echo "  $0 --dry-run            # Preview what would be copied"
  echo "  $0 --yes                 # Non-interactive mode"
  echo "  $0 --force-sensitive     # Copy everything including sensitive files"
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case $1 in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --yes)
      AUTO_YES=true
      shift
      ;;
    --force-sensitive)
      FORCE_SENSITIVE=true
      shift
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      print_usage
      exit 1
      ;;
    esac
  done
}

check_requirements() {
  echo -e "${YELLOW}🔍 Checking requirements...${NC}"

  # Check that the repository containing this script is complete.
  if [[ ! -f "$BOOTSTRAP_DIR/packages.list" ]] || [[ ! -f "$BOOTSTRAP_DIR/install.sh" ]]; then
    echo -e "${RED}Error: dotfiles repository files are missing.${NC}"
    exit 1
  fi

  validate_backup_root || exit 1

  # Check if ~/.config exists
  if [[ ! -d "$HOME/.config" ]]; then
    echo -e "${YELLOW}Warning: ~/.config directory not found. No configurations to copy.${NC}"
  fi

  echo -e "${GREEN}✓ Requirements check passed${NC}"
  echo ""
}

scan_configs() {
  echo -e "${YELLOW}🔍 Scanning for existing configurations...${NC}" >&2

  local found_configs=()

  # Scan ~/.config directory
  if [[ -d "$HOME/.config" ]]; then
    for config in "${!CONFIG_MAPPINGS[@]}"; do
      if [[ -d "$HOME/.config/$config" ]]; then
        echo -e "${CYAN}📁 Found: $config (~/.config/$config/)${NC}" >&2
        found_configs+=("$config:config")
      fi
    done
  fi

  # Check home directory dotfiles
  for dotfile in "${!HOME_MAPPINGS[@]}"; do
    if [[ -f "$HOME/$dotfile" ]]; then
      echo -e "${CYAN}📄 Found: ${dotfile#.} (~/$dotfile)${NC}" >&2
      found_configs+=("${dotfile}:home")
    fi
  done

  # Check SSH config
  if [[ -f "$SSH_CONFIG_SOURCE" ]]; then
    echo -e "${CYAN}🔐 Found: SSH config (~/.ssh/config)${NC}" >&2
    found_configs+=("ssh:ssh")
  fi

  # Check ~/.local/bin for specific scripts
  local specific_scripts=("tmux-sessionizer" "screenshot" "screenshot_1" "screenshot_2" "nvim-launcher" "cursor-launcher" "zed-launcher" "opencode-launcher" "claude-code-launcher" "code-launcher" "ide-chooser" "setup-api-keys" "add-api-key" "setup-ide-aliases")
  for script in "${specific_scripts[@]}"; do
    if [[ -f "$HOME/.local/bin/$script" ]]; then
      echo -e "${CYAN}📄 Found: $script (~/.local/bin/$script)${NC}" >&2
      found_configs+=("$script:bin")
    fi
  done

  if [[ ${#found_configs[@]} -eq 0 ]]; then
    echo -e "${YELLOW}No existing configurations found to copy.${NC}" >&2
    echo -e "${YELLOW}You can still manually create configurations in the dotfiles directories.${NC}" >&2
    exit 0
  fi

  echo -e "${GREEN}Found ${#found_configs[@]} configuration(s) to potentially copy.${NC}" >&2
  echo "" >&2

  # Return found configs (to stdout)
  echo "${found_configs[@]}"
}

validate_paths() {
  local source="$1" dest="$2" parent source_path dest_path source_entry dest_entry
  if [[ ! -f "$source" && ! -d "$source" ]]; then
    echo "Error: source is not a file or directory: $source" >&2
    return 1
  fi
  reject_directory_symlinks "$source" || return 1
  if ! source_path=$(realpath -e -- "$source") ||
    ! dest_path=$(realpath -m -- "$dest") ||
    ! source_entry=$(realpath -ms -- "$source") ||
    ! dest_entry=$(realpath -ms -- "$dest"); then
    echo "Error: cannot resolve copy paths" >&2
    return 1
  fi
  if [[ "$source_path" == "$dest_path" ]]; then
    echo "Already stowed: $source -> $dest (skipped)"
    return 2
  fi
  # Inspect lexical ancestors before resolving symlinks.
  parent=$(dirname -- "$dest")
  while :; do
    if [[ -L "$parent" ]]; then
      echo "Error: destination ancestor is a symlink: $parent" >&2
      return 1
    fi
    [[ "$parent" == / || "$parent" == . ]] && break
    parent=$(dirname -- "$parent")
  done
  if [[ "$source_path/" == "$dest_path/"* || "$dest_path/" == "$source_path/"* ||
    "$source_entry/" == "$dest_entry/"* || "$dest_entry/" == "$source_entry/"* ||
    "$dest_entry/" == "$source_path/"* || "$source_path/" == "$dest_entry/"* ]]; then
    echo "Error: source and destination overlap: $source -> $dest" >&2
    return 1
  fi
  return 0
}

validate_backup_root() {
  local backup_root repository_root

  if [[ "$BOOTSTRAP_BACKUP_ROOT" != /* ]]; then
    echo "Error: DOTFILES_BACKUP_ROOT must be an absolute path" >&2
    return 1
  fi
  if ! backup_root=$(realpath -m -- "$BOOTSTRAP_BACKUP_ROOT") ||
    ! repository_root=$(realpath -e -- "$BOOTSTRAP_DIR"); then
    echo "Error: cannot resolve backup or repository path" >&2
    return 1
  fi
  if [[ "$backup_root" == "$repository_root" || "$backup_root/" == "$repository_root/"* ]]; then
    echo "Error: backup root must be outside the dotfiles repository: $backup_root" >&2
    return 1
  fi
  BOOTSTRAP_BACKUP_ROOT="$backup_root"
}

reject_directory_symlinks() {
  local source="$1" directory_symlink

  # cp -RL follows directory links. Reject them before either scanning or
  # staging so an imported tree cannot expand into an overlapping tree.
  if ! directory_symlink=$(find -P -- "$source" -type l -exec test -d {} \; -print -quit); then
    echo "Error: cannot inspect symlinks in source: $source" >&2
    return 1
  fi
  if [[ -n "$directory_symlink" ]]; then
    echo "Error: source contains a directory symlink: $directory_symlink" >&2
    return 1
  fi
  return 0
}

copy_config() {
  local source="$1"
  local dest="$2"
  local config_name="$3"

  local dest_dir stage backup='' backup_root='' status
  if validate_paths "$source" "$dest"; then :; else
    status=$?
    return "$status"
  fi
  dest_dir="$(dirname -- "$dest")"

  if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${BLUE}[DRY RUN] Would copy $source → $dest${NC}"
    return 0
  fi

  if ! mkdir -p -- "$dest_dir" ||
    ! stage=$(mktemp -d -- "$dest_dir/.bootstrap-stage.XXXXXXXXXX"); then
    echo "Error: cannot create staging directory for $dest" >&2
    return 1
  fi
  # Dereference links consistently with the scanner, including directory links.
  if ! cp -RLp -- "$source" "$stage/payload"; then
    echo "Error: copy failed for $source" >&2
    rm -rf -- "$stage" || echo "Error: cannot clean $stage" >&2
    return 1
  fi
  if [[ -e "$dest" || -L "$dest" ]]; then
    validate_backup_root || {
      rm -rf -- "$stage"
      return 1
    }
    if ! mkdir -p -- "$BOOTSTRAP_BACKUP_ROOT"; then
      echo "Error: cannot create backup root: $BOOTSTRAP_BACKUP_ROOT" >&2
      rm -rf -- "$stage"
      return 1
    fi
    if ! backup_root=$(mktemp -d -- "$BOOTSTRAP_BACKUP_ROOT/bootstrap.XXXXXXXXXX"); then
      echo "Error: cannot reserve backup for $dest" >&2
      rm -rf -- "$stage"
      return 1
    fi
    backup="$backup_root/original"
    if ! cp -a -- "$dest" "$backup"; then
      echo "Error: cannot back up $dest" >&2
      rm -rf -- "$backup_root"
      rm -rf -- "$stage"
      return 1
    fi
    if ! rm -rf -- "$dest"; then
      echo "Error: cannot replace $dest after creating backup" >&2
      rm -rf -- "$backup_root"
      rm -rf -- "$stage"
      return 1
    fi
    echo "Backup: $backup"
  fi
  if ! mv -T -- "$stage/payload" "$dest"; then
    echo "Error: cannot install $dest" >&2
    if [[ -n "$backup" ]]; then
      if cp -a -- "$backup" "$dest"; then
        rm -rf -- "$backup_root" || echo "Error: cannot clean backup reservation" >&2
      else
        echo "Error: rollback failed; original retained at $backup" >&2
      fi
    fi
    rm -rf -- "$stage"
    return 1
  fi
  if ! rmdir -- "$stage"; then
    echo "Error: cannot clean $stage" >&2
    return 1
  fi
  echo "Copied $config_name: $source -> $dest"
  return 0
}

check_sensitive_content() {
  local source="$1"
  local result
  reject_directory_symlinks "$source" || return 3
  # Best effort only: detect high-confidence key material and literal values.
  # Variable references such as "$API_KEY" and "${API_KEY}" are not values.
  local credential_pattern="-----BEGIN .*PRIVATE KEY-----|(^|[^\$[:alnum:]_])AKIA[0-9A-Z]{16}|(^|[^\$[:alnum:]_])gh[pousr]_[[:alnum:]]{20,}"
  local assignment_pattern="(^|[[:space:]])(export[[:space:]]+)?[[:alnum:]_-]*(api[_-]?key|secret|password|passwd|token|access[_-]?key[_-]?id)[[:alnum:]_-]*[[:space:]]*="
  if ! result=$(find -L "$source" -exec bash -c '
    credential_pattern=$1
     assignment_pattern=$2
     shift 2
     shopt -s nocasematch
     for file do
      name=${file##*/}
      case "${name,,}" in
        id_rsa*|id_ed25519*|id_dsa*|id_ecdsa*|*.key|*.pem|*.gpg|*.ovpn|cookies.sqlite|places.sqlite|keyring*)
          printf "SENSITIVE: %q\\n" "$file"
          continue
          ;;
      esac
      if [[ -d "$file" ]]; then
        [[ -r "$file" && -x "$file" ]] || printf "ERROR\\n"
        continue
      fi
      if [[ ! -f "$file" || ! -r "$file" ]]; then
        printf "ERROR\\n"
        continue
      fi
      # Do not use -q: read the whole file so read errors remain visible.
      sensitive=false
      grep -aiE -- "$credential_pattern" "$file" >/dev/null
      status=$?
      case $status in
        0) sensitive=true ;;
        1) ;;
        *) printf "ERROR\\n" ;;
      esac
      if [[ "$sensitive" == false ]]; then
        matches=$(grep -aiE -- "$assignment_pattern" "$file")
        status=$?
        case $status in
          0)
            while IFS= read -r line; do
              [[ "$line" =~ ^[[:space:]]*# ]] && continue
              [[ "$line" =~ $assignment_pattern ]] || continue
              value=${line#*=}
              value="${value#"${value%%[![:space:]]*}"}"
              # Ignore environment indirections, including a variable used
              # inside the assigned value, but still inspect literal values
              # on lines that merely mention a variable in a comment.
              [[ -z "$value" || "$value" == *\$* || "$value" == env:* || "$value" == env\(* || "$value" == args.* || "$value" == *.* ]] && continue
              sensitive=true
              break
            done <<< "$matches"
            ;;
          1) ;;
          *) printf "ERROR\\n" ;;
        esac
      fi
      if [[ "$sensitive" == true ]]; then
        printf "SENSITIVE: %q\\n" "$file"
      fi
    done
  ' bash "$credential_pattern" "$assignment_pattern" {} +); then
    echo "Error: cannot traverse $source" >&2
    return 3
  fi
  if [[ $'\n'"$result"$'\n' == *$'\nERROR\n'* ]]; then
    echo "Error: cannot completely scan $source" >&2
    return 3
  fi
  if [[ -n "$result" ]]; then
    printf '%s\n' "$result"
    return 0
  fi
  return 1
}

prompt_user() {
  local source="$1"
  local dest="$2"
  local config_name="$3"

  # Check for sensitive content first
  local scan_status
  if check_sensitive_content "$source"; then
    if [[ "$FORCE_SENSITIVE" != "true" ]]; then
      echo "Skipped: $config_name (potential sensitive content)"
      echo -e "${CYAN}💡 Suggestion: Handle sensitive files separately with encryption or exclude from dotfiles${NC}"
      SKIPPED_SENSITIVE_COUNT=$((SKIPPED_SENSITIVE_COUNT + 1))
      return 2 # Special return code for sensitive skip
    else
      echo -e "${YELLOW}⚠️  FORCE: $config_name contains sensitive files but proceeding due to --force-sensitive${NC}"
    fi
  else
    scan_status=$?
    [[ "$scan_status" -eq 1 ]] || return 4
  fi

  # In dry-run mode, just proceed
  if [[ "$DRY_RUN" == "true" ]]; then
    return 0
  fi

  if [[ "$AUTO_YES" == "true" ]]; then
    return 0
  fi

  echo ""
  echo -e "${PURPLE}Copy $source to $dest?${NC}"
  echo -n "[Y/n/s(kip)/q(uit)]? "

  local response
  if ! read -r response; then
    echo "End of input; cancelled."
    return 3
  fi

  case "${response,,}" in
  "" | "y" | "yes")
    return 0
    ;;
  "n" | "no" | "s" | "skip")
    return 1
    ;;
  "q" | "quit")
    echo -e "${YELLOW}Operation cancelled by user.${NC}"
    return 3
    ;;
  *)
    echo -e "${RED}Invalid response. Skipping.${NC}"
    return 1
    ;;
  esac
}

process_configs() {
  local found_configs=("$@")
  local i config_entry config_name config_type

  echo -e "${YELLOW}🚀 Starting copy process...${NC}"
  echo ""
  for ((i = 0; i < ${#found_configs[@]}; i++)); do
    config_entry="${found_configs[i]}"
    IFS=':' read -r config_name config_type <<<"$config_entry"

    case "$config_type" in
    "config")
      local source="$HOME/.config/$config_name"
      local dest="$BOOTSTRAP_DIR/${CONFIG_MAPPINGS[$config_name]}"
      ;;
    "home")
      local source="$HOME/$config_name"
      local dest="$BOOTSTRAP_DIR/${HOME_MAPPINGS[$config_name]}"
      ;;
    "ssh")
      local source="$SSH_CONFIG_SOURCE"
      local dest="$BOOTSTRAP_DIR/$SSH_CONFIG_DEST"
      ;;
    "bin")
      local source="$HOME/.local/bin/$config_name"
      local dest="$BOOTSTRAP_DIR/scripts/.local/bin/$config_name"
      ;;
    *)
      echo -e "${RED}Unknown config type: $config_type${NC}"
      continue
      ;;
    esac

    echo -e "${BLUE}📂 Starting to copy $config_name ($config_type) from $source to $dest${NC}"

    local exit_code
    if validate_paths "$source" "$dest"; then :; else
      exit_code=$?
      if [[ "$exit_code" -eq 2 ]]; then
        SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
      else
        FAILED_COUNT=$((FAILED_COUNT + 1))
      fi
      continue
    fi

    # Keep prompts and counter updates in the parent shell.
    if prompt_user "$source" "$dest" "$config_name"; then
      exit_code=0
    else
      exit_code=$?
    fi

    if [[ $exit_code -eq 0 ]]; then
      if copy_config "$source" "$dest" "$config_name"; then
        COPIED_COUNT=$((COPIED_COUNT + 1))
      else
        exit_code=$?
        if [[ "$exit_code" -eq 2 ]]; then
          SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
        else
          FAILED_COUNT=$((FAILED_COUNT + 1))
        fi
      fi
    elif [[ $exit_code -eq 3 ]]; then
      break
    elif [[ $exit_code -eq 4 ]]; then
      FAILED_COUNT=$((FAILED_COUNT + 1))
    elif [[ $exit_code -eq 2 ]]; then
      # Already handled sensitive skip in prompt_user
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    else
      echo -e "${YELLOW}⏭️  Skipped $config_name${NC}"
      SKIPPED_COUNT=$((SKIPPED_COUNT + 1))
    fi
  done
}

print_summary() {
  echo ""
  echo -e "${BLUE}📊 Bootstrap Summary${NC}"
  echo -e "${BLUE}===================${NC}"
  if [[ "$DRY_RUN" == true ]]; then
    echo "Would copy: $COPIED_COUNT configuration(s)"
  else
    echo -e "${GREEN}✓ Copied: $COPIED_COUNT configuration(s)${NC}"
  fi
  echo "Failed: $FAILED_COUNT configuration(s)"

  if [[ $SKIPPED_COUNT -gt 0 ]]; then
    echo -e "${YELLOW}⏭️  Skipped: $SKIPPED_COUNT configuration(s)${NC}"
    if [[ $SKIPPED_SENSITIVE_COUNT -gt 0 ]]; then
      echo -e "${RED}   └─ $SKIPPED_SENSITIVE_COUNT skipped due to sensitive content${NC}"
    fi
  fi

  if [[ "$DRY_RUN" != "true" ]] && [[ $COPIED_COUNT -gt 0 ]]; then
    echo ""
    echo -e "${CYAN}💡 Next steps:${NC}"
    echo -e "${CYAN}   • Run 'git add .' to stage changes${NC}"
    echo -e "${CYAN}   • Reconcile imported originals, then run './install.sh --only stow'${NC}"
    echo -e "${CYAN}   • Commit your dotfiles: 'git commit -m \"Add initial configurations\"'${NC}"
  fi

  if [[ $SKIPPED_SENSITIVE_COUNT -gt 0 ]]; then
    echo ""
    echo -e "${YELLOW}🔐 Security Note:${NC}"
    echo -e "${YELLOW}   $SKIPPED_SENSITIVE_COUNT configuration(s) were skipped due to sensitive content.${NC}"
    echo -e "${YELLOW}   Consider using encrypted storage (git-crypt) or separate management for:${NC}"
    echo -e "${YELLOW}   • SSH private keys • API tokens • Passwords • VPN configs${NC}"
  fi
}

main() {
  print_header

  if [[ $# -gt 0 ]]; then
    parse_args "$@"
  fi

  if [[ "$DRY_RUN" == "true" ]]; then
    echo -e "${YELLOW}🔍 DRY RUN MODE - No files will be modified${NC}"
    echo ""
  fi

  if [[ "$AUTO_YES" == "true" ]]; then
    echo -e "${RED}⚠️  AUTO-YES MODE - All prompts will be answered 'yes'${NC}"
    echo -e "${RED}   This could overwrite existing configurations!${NC}"
    echo ""
  fi

  if [[ "$FORCE_SENSITIVE" == "true" ]]; then
    echo -e "${RED}⚠️  FORCE-SENSITIVE MODE - Will copy configs containing sensitive files${NC}"
    echo -e "${RED}   This may include private keys, passwords, and API tokens!${NC}"
    echo -e "${RED}   ENSURE THESE FILES ARE ENCRYPTED OR EXCLUDED FROM GIT!${NC}"
    echo ""
  fi

  check_requirements

  local found_configs_string
  found_configs_string=$(scan_configs)

  if [[ -z "$found_configs_string" ]]; then
    exit 0
  fi

  # Convert string to array
  IFS=' ' read -r -a found_configs <<<"$found_configs_string"

  if [[ ${#found_configs[@]} -eq 0 ]]; then
    exit 0
  fi

  process_configs "${found_configs[@]}"

  print_summary
  [[ "$FAILED_COUNT" -eq 0 ]]
}

# Run main function
if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi

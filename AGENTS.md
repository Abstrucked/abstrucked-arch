# AGENTS.md - Dotfiles Repository Guidelines

## Commands
- **Test single file**: Run syntax checks with `shellcheck <file>` for shell scripts or `yamllint <file>` for YAML configs
- **Lint all**: `find . -name "*.sh" -exec shellcheck {} \;` for shell scripts
- **Format**: Use `shfmt -w <file>` for shell script formatting
- **Validate configs**: `stow --adopt` to test symlink structure

## Code Style Guidelines
- **Shell scripts**: Use POSIX-compliant syntax, add `#!/bin/bash` or `#!/bin/sh` headers
- **Naming**: Use lowercase with hyphens for filenames (e.g., `git-config`, `vim-settings`)
- **Imports**: Source files with `. ~/.config/shell/aliases.sh` pattern
- **Error handling**: Use `set -euo pipefail` in scripts, check exit codes
- **Documentation**: Add comments for non-obvious configurations
- **Types**: Use strong typing in scripts where possible (`declare -r` for constants)

## Repository Structure
- Keep platform-specific configs in separate directories
- Use GNU Stow for symlink management
- Include setup scripts in `install/` directory

## Commit Guidelines
- Use conventional commits: `feat: add vim config`, `fix: correct bash alias`
- Test changes locally before committing
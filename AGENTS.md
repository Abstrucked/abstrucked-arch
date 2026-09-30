# AGENTS.md - Dotfiles Repository Guidelines

## Commands
- **Test single file**: Run syntax checks with `shellcheck <file>` for shell scripts or `yamllint <file>` for YAML configs
- **Lint all**: `python3 -B scripts/check-syntax.py` (first-party Git inputs, including new files and extensionless shell helpers, plus Zsh/Lua/Python syntax; `.shellcheckrc` makes `source` lines resolve)
- **Run tests**: `pytest tests`
- **Format**: Use `shfmt -w -i 4 <file>` (`-i 2` for files already indented with two spaces). Plain `shfmt` indents with tabs, so never run it repo-wide
- **Validate configs**: `stow --simulate --verbose --no-folding -d "$PWD" -t "$HOME" <package>` (read-only; never use `--adopt` for validation, since it moves user files into the repository)

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

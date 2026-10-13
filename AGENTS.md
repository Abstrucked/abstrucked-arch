# AGENTS.md - Dotfiles Repository Guidelines

## Commands
- **Test single file**: Run syntax checks with `shellcheck <file>` for shell scripts or `yamllint <file>` for YAML configs
- **Lint all**: `python3 -B scripts/check-syntax.py` (first-party Git inputs, including new files and extensionless shell helpers, plus Zsh/Lua/Python syntax; `.shellcheckrc` makes `source` lines resolve)
- **Run tests**: `pytest tests`
- **Format**: Before editing, check with `shfmt -d -i 4 <file>` (`-i 2` for two-space files); run `shfmt -w` with that indent only on files that already pass, and match the surrounding style by hand otherwise. Plain `shfmt` indents with tabs, so never run it repo-wide
- **Validate configs**: `stow --simulate --verbose --no-folding -d "$PWD" -t "$HOME" <package>` (read-only; never use `--adopt` for validation, since it moves user files into the repository)

## Code Style Guidelines
- **Shell scripts**: Installers and helpers are Bash (`#!/bin/bash`); files that declare `#!/bin/sh` must stay POSIX, so check them with `shellcheck -s sh`
- **Naming**: Use lowercase with hyphens for filenames (e.g., `git-config`, `vim-settings`)
- **Imports**: Source files with `. ~/.config/shell/aliases.sh` pattern
- **Error handling**: Executable scripts start with `set -euo pipefail` (`set -eu` under `#!/bin/sh`). Sourced files (`lib/*.sh`, `load-api-keys.sh`, shell rc fragments) must not set shell options, because the options would leak into the caller. They check each step explicitly (`|| return 1`, or `|| die` in installer code), and `lib/*.sh` also use an include guard
- **Documentation**: Add comments for non-obvious configurations
- **Types**: Use strong typing in scripts where possible (`declare -r` for constants)

## Repository Structure
- Keep platform-specific configs in separate directories
- Use GNU Stow for symlink management, always with `--no-folding`: a folded directory link makes applications write private state (SSH keys, app data) into the checkout
- Include setup scripts in `install/` directory

## Commit Guidelines
- Use conventional commits: `feat: add vim config`, `fix: correct bash alias`
- Test changes locally before committing

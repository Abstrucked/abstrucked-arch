# AGENTS.md - AwesomeWM Configuration Guidelines

## Commands
- **Lint Lua**: `luacheck rc.lua` or `luacheck awesome-wm-widgets/`
- **Format Lua**: `lua-format -i <file>` for code formatting
- **Validate Lua syntax**: `lua -c <file>` to check syntax
- **Shell scripts**: Use `shellcheck autorun.sh` for validation

## Code Style Guidelines

### Lua Conventions
- **Syntax**: Use Lua 5.1+ compatible code (check awesome/lain compatibility)
- **Naming**: Use `snake_case` for variables and functions, `UPPER_CASE` for constants
- **Local scope**: Always use `local` keyword for variables; keep scope minimal
- **Tables**: Use table constructors `{}` with named keys for clarity
- **Comments**: Use `--[[` for block comments, `--` for inline comments with space before text
- **Modules**: Pattern: `local widget = {}` then `function widget.method()` with `return widget`

### Imports & Requires
- Source Awesome libraries via `require()`: `local awful = require("awful")`
- Keep requires at top of file grouped by library type (awesome, lain, custom)
- Use local aliases for frequently accessed modules to avoid repetition
- Pattern: Cache globals needed in closures at module start (e.g., `local type = type`)

### Widget Implementation
- Follow widget factory pattern: `function worker(args)` accepting configuration table
- Use `args or {}` for safe defaults: `local args = args or {}`
- Return composite `wibox.widget` objects with layout specifications
- Use `wibox.widget.watch()` or `gears.timer` for periodic updates

### Error Handling
- Wrap system commands with `awful.spawn()` to prevent blocking
- Use `pcall()` for optional operations that may fail
- Log errors via `naughty.notify()` for UI visibility in critical failures
- Check file existence with helpers before operations

### Shell Scripts
- Use `#!/usr/bin/env bash` shebang for portability
- Use `set -euo pipefail` for strict error handling
- Quote variables: `"$variable"` to handle spaces safely
- Use `pgrep -f <pattern>` with `if ! pgrep` for process checks

## Repository Structure
- **rc.lua**: Main configuration entry point with keybinds and theme setup
- **awesome-wm-widgets/**: Third-party widget library with modular widget patterns
- **lain/**: Layout and widget library with utility helpers
- **themes/**: Theme files with color and style definitions
- **autorun.sh**: Startup script for background services

## Commit Guidelines
- Use conventional commits: `feat: add new widget`, `fix: correct keybinding`, `refactor: simplify config`
- Test Awesome reload (Ctrl+Super+R) before committing

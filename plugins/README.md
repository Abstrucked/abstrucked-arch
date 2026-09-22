# plugins

Optional widgets and bindings, toggled on top of the base stack instead of
being wired into it permanently.

    pluginctl list | enable <id> | disable <id> | refresh

- `<id>/manifest.conf` - `NAME="Display Name"`, and `WAYBAR_MODULE="custom/<id>"`
  if the plugin has a bar widget.
- `<id>/waybar.jsonc` - the module's config body, e.g. `{ "format": "...",
  "exec": "..." }`. Spliced into waybar's `modules-right` and its module
  definitions when enabled; may use theme `{{key}}` placeholders like any
  other template (see `themes/README.md`).
- `<id>/hypr.lua` - Hyprland Lua config statements (`hl.bind`, `hl.on`, ...),
  concatenated into `~/.config/hypr/lua/plugins.lua` when enabled. Only wired
  into the Lua entry point (`hyprland.lua`, 0.55+); there is no legacy
  `hyprland.conf` equivalent.
- `<id>/bin/*` - helper scripts, symlinked into `~/.local/bin/` when enabled.

Enabled state lives in `~/.local/state/plugins/enabled`, one id per line.
Enabling/disabling regenerates the generated files above and runs `themectl
apply`, which re-renders, re-links and reloads everything (waybar, hyprland,
...) the same way a theme change does.

`themes/templates/waybar-config.jsonc.tpl` and
`hyprland/.config/hypr/lua/plugins.lua` are generated (gitignored) from
`waybar-config.jsonc.base.tpl` and enabled plugins respectively. Run
`pluginctl refresh` after a fresh clone, same as `themectl apply`.

Porting an Omarchy shell plugin means reading what it does and writing a
native version here (a waybar module + script, usually) - Omarchy's plugins
are QML components for its own Quickshell process and don't run as-is
against this stack.

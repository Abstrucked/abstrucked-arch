# plugins

Optional widgets and bindings, toggled on top of the base stack instead of
being wired into it permanently.

    pluginctl list | enable <id> | disable <id> | refresh

Stowed onto PATH from scripts/.local/bin; bash and zsh complete the
subcommands, and `enable` and `disable` complete the plugins each can act on.

- `<id>/manifest.conf` - `NAME="Display Name"`, and if the plugin has a bar
  widget, `WAYBAR_MODULE="custom/<id>"` plus optionally
  `WAYBAR_SECTION="left|center|right"` (default `right`).
- `<id>/waybar.jsonc` - the module's config body, e.g. `{ "format": "...",
  "exec": "..." }`. Its id is added to the declared `WAYBAR_SECTION`'s
  modules array and its config to the module definitions when enabled; may
  use theme `{{key}}` placeholders like any other template (see
  `themes/README.md`).
- `<id>/hypr.lua` - Hyprland Lua config statements (`hl.bind`, `hl.on`, ...),
  concatenated into `~/.config/hypr/lua/plugins.lua` when enabled. Only wired
  into the Lua entry point (`hyprland.lua`, 0.55+); there is no legacy
  `hyprland.conf` equivalent.
- `<id>/awesome.lua` - arbitrary Lua with `left_widgets`, `right_widgets`,
  `pl`, `c`, `s` in scope, concatenated into `~/.config/awesome/plugins.lua`
  when enabled and called once per connected screen from `theme.lua`, right
  after the built-in widgets. Unlike `waybar.jsonc`, this isn't declarative
  data - the fragment must `table.insert()` its own widget into whichever
  table it wants, exactly like the built-ins in `themes/powerarrow/theme.lua`
  do (`pl(...)` themes the widget's background, `c` is the palette, `s` the
  screen). There's no section field for this side; the fragment just picks
  the table.
- `<id>/bin/*` - helper scripts, symlinked into `~/.local/bin/` when enabled.

A pure-waybar plugin is a no-op under Awesome (it has its own wibox bar, not
waybar); a pure-`hypr.lua` plugin is a no-op under Awesome and vice versa. A
widget meant to show up in both sessions needs both a `waybar.jsonc` and an
`awesome.lua`.

Enabled state lives in `~/.local/state/plugins/enabled`, one id per line.
Enabling/disabling regenerates the generated files above and runs `themectl
apply`, which re-renders, re-links and reloads everything (waybar, hyprland,
awesome, ...) the same way a theme change does.

`themes/templates/waybar-config.jsonc.tpl`, `hyprland/.config/hypr/lua/plugins.lua`
and `awesome/.config/awesome/plugins.lua` are generated (gitignored) from
`waybar-config.jsonc.base.tpl` and enabled plugins respectively. Run
`pluginctl refresh` after a fresh clone, same as `themectl apply`. Validate
Awesome's side with `awesome --check` before reloading a live session.

Porting an Omarchy shell plugin means reading what it does and writing a
native version here (a waybar module + script, usually) - Omarchy's plugins
are QML components for its own Quickshell process and don't run as-is
against this stack.

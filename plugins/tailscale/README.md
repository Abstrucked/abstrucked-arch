# tailscale

Connection status in the bar, click to see peers, right-click to toggle.

A native, scoped-down reimplementation for this stack's rofi+waybar+wibox
setup, based on the feature list of
[igor-alexandrov/omarchy-tailscale](https://github.com/igor-alexandrov/omarchy-tailscale)
(MIT), which is itself derived from Omarchy's first-party `omarchy.tailscale`
widget. No code from either is reused — that project is QML/JS for
Quickshell, this is bash/jq/rofi and a wibox widget — only the idea of what
the widget should show and do.

Not included, unlike the original: exit-node selection, Taildrop, and
switching between multiple accounts. Add them here if you need them.

## Requires

- `tailscale`, `jq`, `rofi`, `wl-copy` (wl-clipboard), `xdg-open`
- `sudo tailscale set --operator=$USER` run once, so `tailscale up`/`down`
  work from a bar click, which has no TTY for a sudo password prompt

## Files

- `bin/tailscale-status` - waybar JSON (default) or a plain string (`--plain`,
  used by the awesome widget)
- `bin/tailscale-menu` - rofi menu: toggle, copy this device's IP, admin
  console, copy a peer's IP
- `bin/tailscale-toggle` - `tailscale up`/`down` based on current state
- `waybar.jsonc` / `awesome.lua` - left click opens the menu, right click
  toggles

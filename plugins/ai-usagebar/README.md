# ai-usagebar

AI plan usage in the bar: the active provider's session quota and time to
reset. Click opens the TUI with every provider; scroll cycles which one the
bar shows.

A thin wrapper around [akitaonrails/ai-usagebar](https://github.com/akitaonrails/ai-usagebar)
(MIT), a Rust tool that already speaks waybar's custom-module JSON. Nothing is
reimplemented here — this plugin is the manifest, the module body, an Awesome
widget, and two small scripts.

## Requires

- `ai-usagebar-bin` from the AUR, which installs `ai-usagebar` and
  `ai-usagebar-tui`. `ai-usagebar` builds the same thing from source.
- `jq`, and `alacritty` for the TUI window.
- It is not in `packages.list`: plugins are opt-in, so their dependencies are
  installed with the plugin rather than on every machine.

## Credentials

Providers are read from credentials already on the machine, never from
anything stored here. A single Claude Code login needs no configuration at
all; `ai-usagebar detect` turns on every other vendor that already has a
local credential. Per-vendor setup lives in upstream's `config.example.toml`,
installed at `/usr/share/ai-usagebar/config.example.toml`.

## Notes

- The 300s interval is upstream's guidance, not a preference: the Anthropic
  and OpenAI endpoints rate-limit aggressively below it. The scroll bindings
  refresh through `signal: 13` rather than waiting for the next poll.
- The usage colours are the palette's, not upstream's: `ai-usage-text`
  drops ai-usagebar's own Pango colour and keeps its usage class (`low`,
  `mid`, `high`, `critical`), which the waybar stylesheet colours like the
  CPU and memory states. The Awesome widget is coloured by the bar.
- In waybar the plugin is `group/ai-usagebar`: an `image#ai` module showing
  the provider's logo (`ai-usage-text --icon '{{orange}}'`, recoloured into
  `~/.cache/ai-usagebar`) and the `custom/ai-usagebar` percentage. Their
  definitions live in `waybar-defs.jsonc`, which `pluginctl` splices in
  next to the group. The logo reads the active vendor from
  `ai-usagebar settings show`, which is local, so it adds no API request.
- `ai-usage-text` prints waybar JSON with `--waybar`, JSON for the Awesome
  widget with `--awesome`, a logo path with `--icon COLOR`, and a plain line
  otherwise. Both bars show the provider's logo and the session percentage;
  the reset time is in the hover tooltip. A missing binary or an
  unreachable vendor prints a placeholder instead of emptying the bar.
- `icons/` holds the Claude, OpenAI and Copilot logos, taken from Zed's
  `assets/icons` (github.com/zed-industries/zed). `--awesome` maps
  ai-usagebar's short vendor names (`cld`, `gpt`/`cdx`, `ghc`) to them; any
  other vendor keeps its short name as text.
- Waybar clicks have no terminal, so the TUI goes through `ai-usage-tui`.
  Upstream's example calls `ai-usagebar-tui` directly, which only works from
  a bar that already provides one.
- If a tray expander sits next to the widget, upstream suggests
  `#custom-ai-usagebar { padding-right: 18px; }` in the waybar stylesheet.

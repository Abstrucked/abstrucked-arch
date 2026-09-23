# themes

One palette, rendered into every app's config.

    themectl list | current | set <name> | next | apply | render <name>

Stowed onto PATH from scripts/.local/bin; bash and zsh complete the
subcommands, and the theme names for `set` and `render`.

- `palettes/<name>.lua` - semantic colors (bg, fg, accent, ansi.*, ...).
- `palettes/_defaults.lua` - fills in every key a palette omits, deriving
  shades with `mix(a, b, amount)`. A palette always wins over it.
- `import-omarchy <colors.toml> [name]` - writes a palette from an Omarchy
  theme (github.com/omacom/omarchy, themes/<name>/colors.toml). It carries 28
  of the 66 keys the templates ask for; the rest come from `_defaults.lua`.
  TOML, color values and template rendering are validated before publication.
  Existing palettes require `--force`; failed imports leave them intact.
- `templates/*.tpl` - app configs with `{{key}}` / `{{key|format}}` placeholders
  (formats: nohash, rgb, rgba[:aa], css[:alpha]).
- `targets.conf` - template, destination (symlinked to `out/`), reload command.
  A destination of `-` renders only.
- `hooks/*.sh` - for apps whose config themectl cannot own (herdr, rnmui, nvim).
- `out` - generated, gitignored symlink to an immutable `.generations/` directory.
  Run `themectl apply` after a fresh clone. The Waybar template is generated
  from current plugin state automatically, without changing plugin wiring.

`themectl render <name>` prints a new temporary preview directory. It never
changes live output, links, state or reloads apps. Delete the preview when done.

Switches are serialized with `flock`; fully rendered generations are activated
with one atomic symlink replacement. `current` reads the name from the active
generation. Previous generations are retained for recovery. The first switch
from a legacy `out/` directory moves it into `.generations/legacy.*`; that
one-time migration has a brief gap before its symlink is installed. Initial
destination linking and app hooks are not part of the atomic generation swap.
Hooks and reloads remain best-effort and report failures on stderr. Each has a
five-second timeout (with forced termination one second later) so a stalled IPC
call cannot block later reloads. Hyprland reloads require a running Hyprland
instance and its session signature; SwayNC reloads only when it is running.

The herdr hook validates the replacement TOML and verifies unrelated settings
are preserved before an atomic replacement. Backups are stored under
`${DOTFILES_BACKUP_ROOT:-$HOME/.dotfiles-backups}/themes/`.

Dependencies: Bash, Lua, GNU coreutils, util-linux (`flock`), and Python 3.11+
(`tomllib`, for imports and herdr updates). Run regression checks with
`python3 -m unittest discover -s tests -p 'test_themes.py'`.

Never edit the generated files (or the symlinks pointing at `out/`); edit the
palette or template instead. Awesome restarts on a theme change when it is the
running session. Theme-triggered Awesome restarts preserve selected workspaces
on each screen and the focused screen using a one-shot, display-specific cache
snapshot. This does not change the defaults for a fresh login.

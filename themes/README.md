# themes

One palette, rendered into every app's config.

    themectl list | current | set <name> | next | apply | render <name>

- `palettes/<name>.lua` - semantic colors (bg, fg, accent, ansi.*, ...).
- `templates/*.tpl` - app configs with `{{key}}` / `{{key|format}}` placeholders
  (formats: nohash, rgb, rgba[:aa], css[:alpha]).
- `targets.conf` - template, destination (symlinked to `out/`), reload command.
  A destination of `-` renders only.
- `hooks/*.sh` - for apps whose config themectl cannot own (herdr, rnmui, nvim).
- `out/` - generated, gitignored. Run `themectl apply` after a fresh clone.

Never edit the generated files (or the symlinks pointing at `out/`); edit the
palette or template instead. Awesome restarts on a theme change when it is the
running session.

# wallpaper sets

`display-detect` (in `scripts/.local/bin`) picks each monitor's wallpaper
from a set here, for Awesome, Hyprland (hyprpaper) and the hyprlock screen
alike. Each output is classed by shape:

- `ultrawide` - 2:1 or wider, e.g. the desktop's 3440x1440
- `wide` - any other external monitor, e.g. the desktop's 1920x1080 27"
- `internal` - a laptop's built-in panel; falls back to the `wide` images

Within a set, an output uses the first file that exists of:

1. `<class>-<W>x<H>.<ext>` - made for that exact resolution
2. `<class>.<ext>` - any size, scaled to cover the screen

and then the same two in `default/`. `<ext>` is png, jpg, jpeg or webp. A
set only needs the images it has something special for.

The active set is, in order: `$WALLPAPER_SET`, the one saved with
`display-detect set <name>`, a set named after the current theme
(`themectl current`) if one exists, then `default`. So a theme gets its own
wallpapers just by adding `sets/<theme>/`.

    display-detect sets          # list sets, * marks the active one
    display-detect set nord      # switch and re-apply
    display-detect list          # what each connected output gets

`default/` links the original `cosmo.png` (16:9) and `arch_wide_bluish.png`
(ultrawide) from the folder above.

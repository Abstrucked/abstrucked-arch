-- Mono: graphite surfaces, quiet greens, and a restrained lime accent.
return {
  name = "mono",
  variant = "dark",

  bg = "#171a18",
  bg_alt = "#202420",
  bg_dark = "#111411",
  surface = "#202420",
  surface_alt = "#292e28",

  fg = "#e3e8dd",
  fg_dim = "#b9c2b1",
  fg_subtle = "#99a391",
  muted = "#99a391",
  accent = "#c2d89a",
  selection = "#78876a",

  red = "#d69a91",
  orange = "#d1ac8b",
  yellow = "#d8c69c",
  green = "#c2d89a",
  cyan = "#9fc5ba",
  blue = "#a8bac5",
  magenta = "#bfacc7",

  ansi = {
    normal = {
      black = "#292e28", red = "#d69a91", green = "#b3c98c", yellow = "#d8c69c",
      blue = "#a8bac5", magenta = "#bfacc7", cyan = "#9fc5ba", white = "#c8d0c1",
    },
    bright = {
      black = "#78836f", red = "#e6b0a7", green = "#c2d89a", yellow = "#e6d6af",
      blue = "#bbced8", magenta = "#d3c0db", cyan = "#b3d8cd", white = "#e3e8dd",
    },
  },

  -- Also make this palette useful with the existing Powerarrow layout.
  awesome = {
    bar_bg = "#202420",
    border_normal = "#363e33",
    border_focus = "#c2d89a",
    titlebar_fg_focus = "#e3e8dd",
    widget_a = "#292e28",
    widget_b = "#363e33",
    widget_c = "#99a391",
  },
}

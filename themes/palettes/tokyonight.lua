-- Tokyo Night (night variant).
return {
  name = "tokyonight",
  variant = "dark",

  bg = "#1a1b26",
  bg_alt = "#16161e",
  bg_dark = "#101014",
  surface = "#292e42",
  surface_alt = "#414868",
  overlay = "#545c7e",

  fg = "#c0caf5",
  fg_dim = "#565f89",
  fg_subtle = "#a9b1d6",
  muted = "#a9b1d6",

  accent = "#7aa2f7",
  accent_alt = "#bb9af7",

  cursor = "#c0caf5",
  vi_cursor = "#bb9af7",
  selection = "#33467c",
  search_focus = "#9ece6a",
  hint = "#e0af68",

  red = "#f7768e",
  orange = "#ff9e64",
  yellow = "#e0af68",
  green = "#9ece6a",
  cyan = "#7dcfff",
  blue = "#7aa2f7",
  magenta = "#bb9af7",

  mauve = "#bb9af7",
  maroon = "#db4b4b",
  sapphire = "#2ac3de",
  lavender = "#b4f9f8",
  sky = "#7dcfff",

  -- Names other tools use for this theme.
  rnmui = "tokio-night",
  nvim = { colorscheme = "tokyonight-night", flavour = "night" },
  herdr_base = "tokyo-night",

  -- Awesome's powerarrow bar has its own bespoke colors.
  awesome = {
    bar_bg = "#3b4261",
    border_normal = "#3b4261",
    border_focus = "#7aa2f7",
    titlebar_fg_focus = "#a9b1d6",
    widget_a = "#292e42",
    widget_b = "#3b4261",
    widget_c = "#414868",
  },

  -- The starship prompt keeps its own segment colors.
  starship = {
    cap = "#a9b1d6", seg1 = "#7aa2f7", seg2 = "#3b4261", seg3 = "#24283b",
    seg4 = "#1f2335", on_seg1 = "#e3e5e5", text = "#a9b1d6", on_cap = "#15161e",
  },

  ansi = {
    normal = {
      black = "#15161e", red = "#f7768e", green = "#9ece6a", yellow = "#e0af68",
      blue = "#7aa2f7", magenta = "#bb9af7", cyan = "#7dcfff", white = "#a9b1d6",
    },
    bright = {
      black = "#414868", red = "#f7768e", green = "#9ece6a", yellow = "#e0af68",
      blue = "#7aa2f7", magenta = "#bb9af7", cyan = "#7dcfff", white = "#c0caf5",
    },
  },
}

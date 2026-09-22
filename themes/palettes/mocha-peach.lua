-- Catppuccin Mocha with a peach accent. Matches the Hyprland active border,
-- the Awesome taglist highlight and the Waybar accent.
return {
  name = "mocha-peach",
  variant = "dark",

  bg = "#1e1e2e",
  bg_alt = "#181825",
  bg_dark = "#11111b",
  surface = "#313244",
  surface_alt = "#45475a",
  overlay = "#6c7086",

  fg = "#cdd6f4",
  fg_dim = "#7f849c",
  fg_subtle = "#bac2de",
  muted = "#a6adc8",

  accent = "#fab387",
  accent_alt = "#89dceb",

  cursor = "#f5e0dc",
  vi_cursor = "#b4befe",
  selection = "#f5e0dc",
  search_focus = "#a6e3a1",
  hint = "#f9e2af",

  red = "#f38ba8",
  orange = "#fab387",
  yellow = "#f9e2af",
  green = "#a6e3a1",
  cyan = "#94e2d5",
  blue = "#89b4fa",
  magenta = "#f5c2e7",

  mauve = "#cba6f7",
  maroon = "#eba0ac",
  sapphire = "#74c7ec",
  lavender = "#b4befe",
  sky = "#89dceb",

  -- Names other tools use for this theme.
  rnmui = "catppuccin-mocha",
  nvim = { colorscheme = "catppuccin", flavour = "mocha" },
  herdr_base = "catppuccin",

  -- Awesome's powerarrow bar has its own bespoke colors.
  awesome = {
    bar_bg = "#C0C0A2",
    border_normal = "#c2c490",
    border_focus = "#7b998a",
    titlebar_fg_focus = "#9399b2",
    widget_a = "#4B3B51",
    widget_b = "#C0C0A2",
    widget_c = "#8DAA9A",
  },

  -- The starship prompt keeps its own segment colors.
  starship = {
    cap = "#a3aed2", seg1 = "#769ff0", seg2 = "#394260", seg3 = "#212736",
    seg4 = "#1d2230", on_seg1 = "#e3e5e5", text = "#a0a9cb", on_cap = "#090c0c",
  },

  ansi = {
    normal = {
      black = "#45475a", red = "#f38ba8", green = "#a6e3a1", yellow = "#f9e2af",
      blue = "#89b4fa", magenta = "#f5c2e7", cyan = "#94e2d5", white = "#bac2de",
    },
    bright = {
      black = "#585b70", red = "#f38ba8", green = "#a6e3a1", yellow = "#f9e2af",
      blue = "#89b4fa", magenta = "#f5c2e7", cyan = "#94e2d5", white = "#a6adc8",
    },
  },
}

-- Fallbacks for every key a palette leaves out. A palette always wins, so the
-- hand-written palettes are unaffected; an Omarchy colors.toml, which carries
-- 28 of the 66 keys the templates ask for, is filled in from here.
--
-- render.lua calls this with the palette and a mix(a, b, amount) helper.
return function(p, mix)
  local dark = p.variant ~= "light"

  return {
    -- Shades Omarchy's palette has no equivalent for.
    surface_alt = mix(p.surface, p.fg, 0.15),
    overlay = mix(p.bg, p.fg, 0.45),
    accent_alt = p.cyan or p.blue,
    selection = mix(p.surface, p.fg, 0.15),

    -- Roles the terminal and editor templates ask for by name.
    cursor = p.fg,
    vi_cursor = p.accent,
    search_focus = p.green,
    hint = p.yellow,

    -- The Adwaita stylesheet the login screen's GTK theme builds on.
    adwaita_css = dark and "gtk-contained-dark.css" or "gtk-contained.css",

    -- Catppuccin's extra hues. btop's gradient is the only real consumer.
    mauve = p.magenta,
    maroon = p.red,
    sapphire = p.cyan,
    lavender = mix(p.blue, p.fg, 0.4),
    sky = p.cyan,

    -- Names, not colors: these tools pick a theme of their own. A palette
    -- that has a matching one should say so rather than inherit these.
    rnmui = dark and "catppuccin-mocha" or "catppuccin-latte",
    herdr_base = "catppuccin",
    nvim = { colorscheme = "catppuccin", flavour = dark and "mocha" or "latte" },

    -- The powerarrow bar and the Powerlevel10k prompt keep their own colors
    -- across themes; a palette overrides either block to take them over.
    awesome = {
      bar_bg = "#C0C0A2",
      border_normal = "#c2c490",
      border_focus = "#7b998a",
      titlebar_fg_focus = "#9399b2",
      widget_a = "#4B3B51",
      widget_b = "#C0C0A2",
      widget_c = "#8DAA9A",
    },

    starship = {
      cap = "#a3aed2", seg1 = "#769ff0", seg2 = "#394260", seg3 = "#212736",
      seg4 = "#1d2230", on_seg1 = "#e3e5e5", text = "#a0a9cb", on_cap = "#090c0c",
    },
  }
end

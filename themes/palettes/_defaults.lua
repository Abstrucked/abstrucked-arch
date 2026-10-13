-- Fallbacks for every key a palette leaves out. A palette always wins, so the
-- hand-written palettes are unaffected; an Omarchy colors.toml, which carries
-- 28 of the 66 keys the templates ask for, is filled in from here.
--
-- render.lua calls this with the palette and a mix(a, b, amount) helper.
return function(p, mix)
  local dark = p.variant ~= "light"

  -- WCAG relative luminance and contrast, to pick readable text on a block.
  local function luminance(hex)
    local function channel(i)
      local c = tonumber(hex:sub(i, i + 1), 16) / 255
      return c <= 0.04045 and c / 12.92 or ((c + 0.055) / 1.055) ^ 2.4
    end
    return 0.2126 * channel(2) + 0.7152 * channel(4) + 0.0722 * channel(6)
  end
  local function contrast(a, b)
    local x, y = luminance(a), luminance(b)
    return (math.max(x, y) + 0.05) / (math.min(x, y) + 0.05)
  end
  -- Whichever of bg_dark / fg reads better on c, deepened toward black or
  -- white when neither reaches 4.5:1 (rose-pine's fg on its teal accent).
  local function on(c)
    local best, best_step
    for _, text in ipairs({ p.bg_dark, p.fg }) do
      local extreme = luminance(text) < luminance(c) and "#000000" or "#ffffff"
      local out, step = text, 0
      while contrast(out, c) < 4.5 and step < 10 do
        step = step + 1
        out = mix(text, extreme, step / 10)
      end
      if contrast(out, c) >= 4.5 then step = step - 100 end -- reached it: prefer
      if not best or step < best_step then best, best_step = out, step end
    end
    return best
  end

  -- A powerarrow segment: one of two neutral steps from bg toward fg, which
  -- neighbours alternate between, plain text, and the icon in the full hue.
  local tones = { mix(p.bg, p.fg, 0.09), mix(p.bg, p.fg, 0.17) }
  local function tone(step, hue)
    return { bg = tones[step], fg = p.fg, icon = hue }
  end

  -- Prompts without their own segment colors follow the active palette. Derive
  -- readable text from each effective background, including partial overrides.
  local prompt = type(p.starship) == "table" and p.starship or {}
  local cap = prompt.cap or mix(p.accent, p.fg, 0.35)
  local seg1 = prompt.seg1 or p.accent
  local seg2 = prompt.seg2 or tones[2]
  local seg3 = prompt.seg3 or tones[1]
  local seg4 = prompt.seg4 or p.bg

  return {
    -- Shades Omarchy's palette has no equivalent for.
    surface_alt = mix(p.surface, p.fg, 0.15),
    overlay = mix(p.bg, p.fg, 0.45),
    accent_alt = p.cyan or p.blue,
    selection = mix(p.surface, p.fg, 0.15),
    -- Readable text on an accent-filled block (the tmux session name).
    on_accent = on(p.accent),

    -- Roles the terminal and editor templates ask for by name.
    cursor = p.fg,
    vi_cursor = p.accent,
    search_focus = p.green,
    hint = p.yellow,

    -- The Adwaita stylesheet the login screen's GTK theme builds on.
    adwaita_css = dark and "gtk-contained-dark.css" or "gtk-contained.css",
    -- The GTK3 theme gtk3.css recolors (package adw-gtk-theme), and whether
    -- apps should ask for their dark variant.
    gtk3_theme = dark and "adw-gtk3-dark" or "adw-gtk3",
    gtk_prefer_dark = dark and 1 or 0,

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

    -- The powerarrow bar's borders and the Powerlevel10k prompt keep their own
    -- colors across themes; a palette overrides either block to take them
    -- over. The bar's segments (awesome.seg) follow the palette's hues.
    awesome = {
      bar_bg = "#C0C0A2",
      border_normal = "#c2c490",
      border_focus = "#7b998a",
      titlebar_fg_focus = "#9399b2",
      widget_a = "#4B3B51",
      widget_b = "#C0C0A2",
      widget_c = "#8DAA9A",
      -- One icon hue per widget; bat_mid / bat_low replace bat as the charge
      -- drops.
      seg = {
        -- Steps follow the bar's order, so neighbours never share a tone.
        ai = tone(1, p.orange),
        tailscale = tone(2, p.magenta),
        volume = tone(1, p.blue),
        mem = tone(2, p.yellow),
        cpu = tone(1, p.red),
        fs = tone(2, p.cyan),
        bat = tone(1, p.green),
        bat_mid = tone(1, p.yellow),
        bat_low = tone(1, p.red),
        net = tone(2, p.blue),
        clock = { bg = p.accent, fg = on(p.accent), icon = on(p.accent) },
        layout = tone(1, p.fg),
      },
    },

    starship = {
      cap = cap, seg1 = seg1, seg2 = seg2, seg3 = seg3, seg4 = seg4,
      on_seg1 = on(seg1), text = on(seg4), on_cap = on(cap),
      -- Existing explicit segment designs used seg1 as text on seg2 / seg3.
      -- Keep that choice unless they explicitly set the new foreground roles.
      on_seg2 = prompt.seg1 or on(seg2),
      on_seg3 = prompt.seg1 or on(seg3),
    },
  }
end

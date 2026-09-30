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

  -- OpenCode V2 needs a complete semantic token tree and hue ramps. Derive
  -- these from the active palette so imported palettes work without edits.
  local bg, fg = p.bg, p.fg
  local accent = p.accent or p.blue or fg
  local red = p.red or accent
  local orange = p.orange or p.yellow or accent
  local yellow = p.yellow or accent
  local green = p.green or accent
  local cyan = p.cyan or p.blue or accent
  local blue = p.blue or accent
  local purple = p.magenta or blue
  local original_muted = p.muted or p.fg_dim or fg
  local surface = p.surface or p.bg_alt or bg
  local surface_alt = p.surface_alt or mix(surface, fg, 0.15)
  local raised = mix(surface_alt, fg, 0.12)

  -- Some terminal palettes use very dim muted/status hues. Keep their tint,
  -- but raise contrast for UI text on the surface where it is actually drawn.
  local function readable(color, background)
    local extreme = luminance(background) < 0.179 and "#ffffff" or "#000000"
    for step = 0, 100 do
      local candidate = mix(color, extreme, step / 100)
      if contrast(candidate, background) >= 4.5 then return candidate end
    end
    return extreme
  end
  local muted = readable(original_muted, surface_alt)

  local function extend(color, target_luminance, extreme, brighter)
    for _ = 1, 20 do
      local current = luminance(color)
      if (brighter and current >= target_luminance + 0.01)
          or (not brighter and current <= target_luminance - 0.01) then
        break
      end
      color = mix(color, extreme, 0.10)
    end
    return color
  end

  local function at_luminance(color, target_luminance)
    local current = luminance(color)
    if math.abs(current - target_luminance) < 0.0001 then return color end
    local extreme = target_luminance > current and "#ffffff" or "#000000"
    local low, high = 0, 1
    for _ = 1, 20 do
      local middle = (low + high) / 2
      local blended_luminance = luminance(mix(color, extreme, middle))
      if (target_luminance > current and blended_luminance < target_luminance)
          or (target_luminance < current and blended_luminance > target_luminance) then
        low = middle
      else
        high = middle
      end
    end
    return mix(color, extreme, (low + high) / 2)
  end

  local function ramp(color)
    local color_luminance = luminance(color)
    local first, last
    if dark then
      first = extend(fg, color_luminance, "#ffffff", true)
      last = extend(bg, color_luminance, "#000000", false)
    else
      first = extend(fg, color_luminance, "#000000", false)
      last = extend(bg, color_luminance, "#ffffff", true)
    end
    local first_luminance, last_luminance = luminance(first), luminance(last)
    local result = {}
    for step = 1, 9 do
      local progress = (step - 1) / 8
      local candidate, target_luminance
      if progress <= 0.5 then
        local segment_progress = progress * 2
        candidate = mix(first, color, segment_progress)
        target_luminance = first_luminance + (color_luminance - first_luminance) * segment_progress
      else
        local segment_progress = (progress - 0.5) * 2
        candidate = mix(color, last, segment_progress)
        target_luminance = color_luminance + (last_luminance - color_luminance) * segment_progress
      end
      result[tostring(step * 100)] = at_luminance(candidate, target_luminance)
    end
    return result
  end

  local hue_order = { "gray", "red", "orange", "yellow", "green", "cyan", "blue", "purple" }
  local hue_sources = {
    gray = original_muted, red = red, orange = orange, yellow = yellow,
    green = green, cyan = cyan, blue = blue, purple = purple,
  }
  local hues = {}
  local function distance(a, b)
    local total = 0
    for index = 2, 6, 2 do
      local difference = tonumber(a:sub(index, index + 1), 16) - tonumber(b:sub(index, index + 1), 16)
      total = total + difference * difference
    end
    return total
  end
  local function nearest_hue(color)
    local nearest, nearest_distance
    for _, name in ipairs(hue_order) do
      local candidate = hue_sources[name]
      local current_distance = distance(color, candidate)
      if not nearest_distance or current_distance < nearest_distance then
        nearest, nearest_distance = name, current_distance
      end
    end
    return "$hue." .. nearest
  end
  for _, name in ipairs(hue_order) do
    local color = hue_sources[name]
    hues[name] = ramp(color)
  end
  hues.accent = nearest_hue(accent)
  hues.interactive = hues.accent
  hues.neutral = "$hue.gray"

  local function soft(color, amount)
    return mix(bg, color, amount)
  end
  local error_bg = soft(red, 0.18)
  local warning_bg = soft(yellow, 0.18)
  local success_bg = soft(green, 0.18)
  local info_bg = soft(cyan, 0.18)
  local secondary_text = readable(accent, mix(surface_alt, accent, 0.12))
  local opencode = {
    variant = dark and "dark" or "light",
    mode = {
      hue = hues,
      categorical = { "accent", "red", "green", "blue", "purple" },
    },
    base = {
      categorical = { "accent", "red", "green", "blue", "purple" },
      text = {
        base = fg,
        muted = muted,
        action = {
          primary = {
            base = on(accent),
            hovered = on(mix(accent, fg, 0.10)),
            focused = on(mix(accent, fg, 0.10)),
            pressed = on(mix(accent, bg, 0.12)),
            selected = on(accent),
            disabled = muted,
          },
          secondary = {
            base = secondary_text,
            hovered = secondary_text,
            focused = secondary_text,
            pressed = secondary_text,
            selected = secondary_text,
            disabled = muted,
          },
          destructive = {
            base = on(red),
            hovered = on(mix(red, fg, 0.10)),
            focused = on(mix(red, fg, 0.10)),
            pressed = on(mix(red, bg, 0.12)),
            selected = on(red),
            disabled = muted,
          },
        },
        formfield = {
          base = fg,
          hovered = fg,
          focused = fg,
          pressed = fg,
          selected = fg,
          disabled = muted,
        },
        feedback = {
          error = { base = readable(red, error_bg), muted = readable(red, error_bg) },
          warning = { base = readable(yellow, warning_bg), muted = readable(yellow, warning_bg) },
          success = { base = readable(green, success_bg), muted = readable(green, success_bg) },
          info = { base = readable(cyan, info_bg), muted = readable(cyan, info_bg) },
        },
      },
      background = {
        base = bg,
        raised = { base = surface, high = surface_alt, max = raised },
        action = {
          primary = {
            base = accent,
            hovered = mix(accent, fg, 0.10),
            focused = mix(accent, fg, 0.10),
            pressed = mix(accent, bg, 0.12),
            selected = accent,
            disabled = surface_alt,
          },
          secondary = {
            base = surface_alt,
            hovered = mix(surface_alt, accent, 0.12),
            focused = mix(surface_alt, accent, 0.12),
            pressed = surface,
            selected = surface_alt,
            disabled = surface,
          },
          destructive = {
            base = red,
            hovered = mix(red, fg, 0.10),
            focused = mix(red, fg, 0.10),
            pressed = mix(red, bg, 0.12),
            selected = red,
            disabled = surface_alt,
          },
        },
        formfield = {
          base = mix(bg, surface, 0.35),
          hovered = mix(bg, surface_alt, 0.35),
          focused = mix(bg, accent, 0.12),
          pressed = mix(bg, surface, 0.35),
          selected = mix(bg, accent, 0.12),
          disabled = bg,
        },
        feedback = {
          error = { base = error_bg },
          warning = { base = warning_bg },
          success = { base = success_bg },
          info = { base = info_bg },
        },
      },
      border = { base = mix(surface, fg, 0.18) },
      scrollbar = { base = mix(surface, fg, 0.28) },
      diff = {
        text = {
          added = readable(green, soft(green, 0.16)),
          removed = readable(red, soft(red, 0.16)),
          context = muted,
          hunkHeader = readable(blue, surface),
        },
        background = {
          added = soft(green, 0.16),
          removed = soft(red, 0.16),
          context = surface,
        },
        highlight = { added = green, removed = red },
        lineNumber = {
          text = muted,
          background = { added = soft(green, 0.22), removed = soft(red, 0.22) },
        },
      },
      syntax = {
        comment = muted,
        keyword = purple,
        func = blue,
        variable = fg,
        string = green,
        number = orange,
        type = cyan,
        operator = red,
        punctuation = muted,
      },
      markdown = {
        text = fg,
        heading = accent,
        link = blue,
        linkText = accent,
        code = green,
        blockQuote = muted,
        emphasis = purple,
        strong = yellow,
        horizontalRule = muted,
        listItem = accent,
        listEnumeration = blue,
        image = cyan,
        imageText = muted,
        codeBlock = fg,
      },
    },
  }

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
      cap = "#a3aed2", seg1 = "#769ff0", seg2 = "#394260", seg3 = "#212736",
      seg4 = "#1d2230", on_seg1 = "#e3e5e5", text = "#a0a9cb", on_cap = "#090c0c",
    },

    opencode = opencode,
  }
end

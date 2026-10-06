-- Upstream warns the Anthropic and OpenAI endpoints rate-limit below ~300s,
-- so this polls on the same interval as the waybar module, and once() shares
-- the one watcher across screens rather than polling per monitor. --awesome
-- mode's JSON carries the provider's logo and the same rich tooltip waybar
-- shows on hover, which is where the reset time lives; the bar shows only
-- the logo and the session percentage. Upstream draws that tooltip in One
-- Dark's palette, so it is retinted onto the active theme's colours on the
-- way in.
local ai_usage_widget = once(function()
    local dkjson = require("lain.util").dkjson
    local wibox = require("wibox")
    local seg = c.seg and c.seg.ai or { icon = c.fg }
    local logos = {}
    local logo = wibox.widget.imagebox()
    local text = wibox.widget.textbox()
    local widget = wibox.widget({
        { logo, top = 1, bottom = 1, right = 4, widget = wibox.container.margin },
        text,
        layout = wibox.layout.fixed.horizontal,
    })
    local tooltip = awful.tooltip({ objects = { widget } })
    -- Upstream frames its tooltip in One Dark's blue and greys, which belong to
    -- no palette here. Hand it the palette's usage colours through its own
    -- --color-* flags (covering every usage class without guessing upstream's
    -- hexes) and swap the remaining chrome over below.
    local chrome = {
        ["#61afef"] = seg.icon,            -- frame and title
        ["#5c6370"] = c.muted,             -- rules and secondary text
        ["#abb2bf"] = c.fg,                -- labels
        ["#3e4451"] = c.bg_dark or c.bg,   -- empty bar track, as a groove
    }
    local text_color = c.fg or "#cdd6f4"
    local command = string.format(
        "ai-usage-text --awesome --color-low '%s' --color-mid '%s' --color-high '%s' --color-critical '%s'",
        -- %s must never see nil, so each slot falls back to the text colour.
        c.green or c.accent or text_color, c.yellow or c.accent or text_color,
        c.red or c.accent or text_color, c.red or c.accent or text_color
    )
    awful.widget.watch(command, 300, function(_, stdout)
        local data = dkjson.decode(stdout) or {}
        text:set_text(data.text or "ai ?")
        local path = data.icon or ""
        if path ~= "" and not logos[path] then
            logos[path] = gears.color.recolor_image(path, seg.icon)
        end
        logo:set_image(logos[path])
        logo.visible = path ~= ""
        if data.tooltip then
            -- Only the foreground attributes, so tooltip text that happens to
            -- look like a hex code is left alone.
            tooltip:set_markup((data.tooltip:gsub("(foreground=')(#%x%x%x%x%x%x)(')", function(open, hex, close)
                return open .. (chrome[hex:lower()] or hex) .. close
            end)))
        end
    end, text)
    widget:buttons(gears.table.join(
        awful.button({}, 1, function() awful.spawn("ai-usage-tui") end)
    ))
    return widget
end)
table.insert(right_widgets, pl(ai_usage_widget, c.seg and c.seg.ai or c.widget_c .. "22"))

-- The mark is drawn with cairo rather than loaded from an image because the
-- generated plugins.lua has no path to plugin assets, and drawing stays crisp
-- at any DPI. Three rows of three dots: the middle row and bottom centre form
-- the "T", the other five are faint. Connected is a green T; disconnected and
-- error are a uniform dim grid, so the shape alone reads as "off". Polls every
-- 5 s and refreshes right after a click.
local tailscale_widget = once(function()
    local dkjson = require("lain.util").dkjson
    local wibox = require("wibox")
    local beautiful = require("beautiful")
    local Pango = require("lgi").Pango
    local font = beautiful.get_font(beautiful.widget_font or beautiful.font)
    -- Match the text's font size rather than stretching the mark to bar height.
    local icon_size = font:get_size() / Pango.SCALE
    if not font:get_size_is_absolute() then
        icon_size = icon_size * beautiful.xresources.get_dpi() / 72
    end
    icon_size = math.max(1, math.floor(icon_size + 0.5))
    local state = "error"
    local solid = { [4] = true, [5] = true, [6] = true, [8] = true }
    local widget = wibox.widget.base.make_widget()
    function widget:fit()
        return icon_size, icon_size
    end
    function widget:draw(_, cr, width, height)
        local connected = state == "connected"
        local col
        if connected then
            col = c.green or c.accent or c.fg or "#9ece6a"
        else
            col = c.muted or "#808080"
        end
        local r, g, b = gears.color.parse_color(col)
        local side = math.min(width, height)
        local pitch = side / 3
        cr:translate((width - side) / 2, (height - side) / 2)
        for i = 0, 8 do
            local alpha = 0.35
            if connected then
                alpha = solid[i + 1] and 1 or 0.3
            end
            cr:set_source_rgba(r, g, b, alpha)
            cr:arc((i % 3 + 0.5) * pitch, (i // 3 + 0.5) * pitch, pitch * 0.4, 0, 2 * math.pi)
            cr:fill()
        end
    end
    local tooltip = awful.tooltip({ objects = { widget } })
    local _, timer = awful.widget.watch("tailscale-status", 5, function(_, stdout)
        local data = dkjson.decode(stdout)
        state = type(data) == "table" and data.class or "error"
        if type(data) == "table" and data.tooltip then
            tooltip:set_text(data.tooltip)
        end
        widget:emit_signal("widget::redraw_needed")
    end, widget)
    -- Refresh as soon as the command exits, and again after 2 s in case the
    -- BackendState lags behind.
    local function run_then_refresh(cmd)
        awful.spawn.easy_async(cmd, function()
            timer:emit_signal("timeout")
            gears.timer.start_new(2, function()
                timer:emit_signal("timeout")
                return false
            end)
        end)
    end
    widget:buttons(gears.table.join(
        awful.button({}, 1, function() run_then_refresh("tailscale-menu") end),
        awful.button({}, 3, function() run_then_refresh("tailscale-toggle") end)
    ))
    return widget
end)
table.insert(right_widgets, pl(tailscale_widget, c.seg and c.seg.tailscale or c.widget_b .. "22"))

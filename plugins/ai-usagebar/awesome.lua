-- Upstream warns the Anthropic and OpenAI endpoints rate-limit below ~300s,
-- so this polls on the same interval as the waybar module, and once() shares
-- the one watcher across screens rather than polling per monitor. --awesome
-- mode's JSON carries the provider's logo and the same rich tooltip waybar
-- shows on hover, which is where the reset time lives; the bar shows only
-- the logo and the session percentage.
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
    awful.widget.watch("ai-usage-text --awesome", 300, function(_, stdout)
        local data = dkjson.decode(stdout) or {}
        text:set_text(data.text or "ai ?")
        local path = data.icon or ""
        if path ~= "" and not logos[path] then
            logos[path] = gears.color.recolor_image(path, seg.icon)
        end
        logo:set_image(logos[path])
        logo.visible = path ~= ""
        if data.tooltip then
            tooltip:set_markup(data.tooltip)
        end
    end, text)
    widget:buttons(gears.table.join(
        awful.button({}, 1, function() awful.spawn("ai-usage-tui") end)
    ))
    return widget
end)
table.insert(right_widgets, pl(ai_usage_widget, c.seg and c.seg.ai or c.widget_c .. "22"))

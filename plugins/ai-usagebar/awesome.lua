-- Upstream warns the Anthropic and OpenAI endpoints rate-limit below ~300s,
-- so this polls on the same interval as the waybar module, and once() shares
-- the one watcher across screens rather than polling per monitor. --waybar
-- mode's JSON carries the same rich tooltip waybar shows on hover, so read
-- that instead of the plain-text mode to drive an awful.tooltip too.
local ai_usage_widget = once(function()
    local dkjson = require("lain.util").dkjson
    local widget, tooltip
    widget = awful.widget.watch("ai-usage-text --waybar", 300, function(w, stdout)
        local data = dkjson.decode(stdout)
        local text = (data and data.text) or "ai ?"
        w:set_text((text:gsub("<[^>]*>", "")))
        if data and data.tooltip then
            tooltip:set_markup(data.tooltip)
        end
    end)
    tooltip = awful.tooltip({ objects = { widget } })
    widget:buttons(gears.table.join(
        awful.button({}, 1, function() awful.spawn("ai-usage-tui") end)
    ))
    return widget
end)
table.insert(right_widgets, pl(ai_usage_widget, c.widget_c .. "22"))

-- Upstream warns the Anthropic and OpenAI endpoints rate-limit below ~300s,
-- so this polls on the same interval as the waybar module. --waybar mode's
-- JSON carries the same rich tooltip waybar shows on hover, so read that
-- instead of the plain-text mode to drive an awful.tooltip too.
local dkjson = require("lain.util").dkjson
local ai_usage_widget, ai_usage_tooltip
ai_usage_widget = awful.widget.watch("ai-usage-text --waybar", 300, function(widget, stdout)
    local data = dkjson.decode(stdout)
    local text = (data and data.text) or "ai ?"
    widget:set_text((text:gsub("<[^>]*>", "")))
    if data and data.tooltip then
        ai_usage_tooltip:set_markup(data.tooltip)
    end
end)
ai_usage_tooltip = awful.tooltip({ objects = { ai_usage_widget } })
ai_usage_widget:buttons(gears.table.join(
    awful.button({}, 1, function() awful.spawn("ai-usage-tui") end)
))
table.insert(right_widgets, pl(ai_usage_widget, c.widget_c .. "22"))

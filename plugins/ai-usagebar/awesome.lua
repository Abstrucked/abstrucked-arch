-- Upstream warns the Anthropic and OpenAI endpoints rate-limit below ~300s,
-- so this polls on the same interval as the waybar module.
local ai_usage_widget = awful.widget.watch("ai-usage-text", 300, function(widget, stdout)
    widget:set_text((stdout:gsub("%s+$", "")))
end)
ai_usage_widget:buttons(gears.table.join(
    awful.button({}, 1, function() awful.spawn("ai-usage-tui") end)
))
table.insert(right_widgets, pl(ai_usage_widget, c.widget_c .. "22"))

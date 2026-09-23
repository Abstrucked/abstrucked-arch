local tailscale_widget = once(function()
    local widget = awful.widget.watch("tailscale-status --plain", 15, function(widget, stdout)
        widget:set_text((stdout:gsub("%s+$", "")))
    end)
    widget:buttons(gears.table.join(
        awful.button({}, 1, function() awful.spawn("tailscale-menu") end),
        awful.button({}, 3, function() awful.spawn("tailscale-toggle") end)
    ))
    return widget
end)
table.insert(right_widgets, pl(tailscale_widget, c.widget_b .. "22"))

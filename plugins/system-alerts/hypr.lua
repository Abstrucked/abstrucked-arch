-- The watcher takes a flock, so a Hyprland reload never doubles it.
hl.on("hyprland.start", function()
    hl.exec_cmd("os-assistant --watch-alerts")
end)

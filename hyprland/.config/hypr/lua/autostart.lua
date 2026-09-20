hl.on("hyprland.start", function()
    hl.exec_cmd("hypr-session-start")
    hl.exec_cmd("alacritty --class dropdown-terminal")
end)

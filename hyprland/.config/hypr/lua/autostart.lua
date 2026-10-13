hl.on("hyprland.start", function()
    hl.exec_cmd("hypr-session-start")
    -- Resident Ghostty for ghostty-window, started here for the full session
    -- environment; the last flag keeps it alive after its last window closes.
    hl.exec_cmd("ghostty --gtk-single-instance=true --initial-window=false --quit-after-last-window-closed=false")
    hl.exec_cmd("alacritty --class dropdown-terminal")
end)

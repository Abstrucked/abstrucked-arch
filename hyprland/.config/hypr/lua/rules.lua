-- Application placement mirrors the AwesomeWM rules.
hl.window_rule({
    match = { class = "^(Brave|Brave-browser|brave-browser)$" },
    workspace = "3 silent",
})

hl.window_rule({
    match = { class = "^(discord|Discord)$" },
    workspace = "7 silent",
})

hl.window_rule({
    match = { class = "^(Gimp|gimp|Gimp-3.0)$" },
    workspace = "3 silent",
    maximize = true,
})

-- Applications picom keeps fully opaque through its opacity-rule list.
for _, class in ipairs({
    "^(Brave|Brave-browser|brave-browser)$",
    "^(Gimp|gimp|Gimp-3.0)$",
    "^(org.inkscape.Inkscape|Inkscape|inkscape)$",
    "^(vlc|VLC|mpv|MPlayer)$",
    "^(org.gnome.Loupe|eog|imv|feh)$",
}) do
    hl.window_rule({ match = { class = class }, opacity = "1.0 1.0" })
end

-- A persistent special workspace provides the old quake-terminal workflow.
local dropdown = { class = "^(dropdown-terminal)$" }
hl.window_rule({ match = dropdown, float = true })
hl.window_rule({
    match = dropdown,
    size = {"monitor_w * 0.9", "monitor_h * 0.85"},
    center = true,
    workspace = "special:quake silent",
})

-- Start with a safe fallback. display-detect applies the real layout and
-- wallpapers after the compositor reports the actual connectors and modes.
hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

-- keyword/eval monitor rules are dropped by a reload, and new outputs need
-- the layout and a wallpaper too, so re-apply both on either.
local function apply_layout()
    hl.exec_cmd("display-detect apply")
end

hl.on("config.reloaded", apply_layout)
hl.on("monitor.added", apply_layout)

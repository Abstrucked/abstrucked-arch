-- Start with a safe fallback. display-detect applies the real layout and
-- wallpapers after the compositor reports the actual connectors and modes.
hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

-- keyword/eval monitor rules are dropped by a reload, a new output needs the
-- layout and a wallpaper, and an unplugged one can leave a gap in the row, so
-- re-apply both on any of these.
local function apply_layout()
    hl.exec_cmd("display-detect apply")
end

hl.on("config.reloaded", apply_layout)
hl.on("monitor.added", apply_layout)
hl.on("monitor.removed", apply_layout)

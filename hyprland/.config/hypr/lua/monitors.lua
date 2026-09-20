-- Start with a safe fallback. hypr-monitor-layout applies the known layout
-- after the compositor reports the actual connector names and refresh rates.
hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

-- keyword/eval monitor rules are dropped by a reload, and new outputs need the
-- layout too, so re-apply it on both.
local function apply_layout()
    hl.exec_cmd("hypr-monitor-layout")
end

hl.on("config.reloaded", apply_layout)
hl.on("monitor.added", apply_layout)

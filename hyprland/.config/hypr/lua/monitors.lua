-- Start with a safe fallback. hypr-monitor-layout applies the known layout
-- after the compositor reports the actual connector names and refresh rates.
hl.monitor({
    output = "",
    mode = "preferred",
    position = "auto",
    scale = 1,
})

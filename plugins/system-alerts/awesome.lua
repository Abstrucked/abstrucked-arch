-- The watcher takes a flock, so an awesome restart never doubles it; once()
-- only keeps the per-screen call from spawning it for every monitor.
local system_alerts_watcher = once(function()
    awful.spawn({ "os-assistant", "--watch-alerts" }, false)
    return true
end)

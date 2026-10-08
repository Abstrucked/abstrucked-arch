-- Test the production polling helper from both popup themes in isolation.
local paths = {
    "awesome/.config/awesome/themes/tide/theme.lua",
    "awesome/.config/awesome/themes/nocturne/theme.lua",
}

for _, path in ipairs(paths) do
    local file = assert(io.open(path, "r"))
    local source = file:read("*a")
    file:close()
    local start = assert(source:find("local function make_volume_poller(on_read)", 1, true))
    local marker = assert(source:find("-- End volume polling helper.", start, true))
    local helper = source:sub(start, marker - 1) .. "\nreturn make_volume_poller\n"

    local pending, timers, kills = {}, {}, {}
    local next_pid = 100
    local awful = {
        spawn = setmetatable({
            easy_async = function(command, callback)
                assert(command[1] == "wpctl" and command[3] == "@DEFAULT_AUDIO_SINK@")
                next_pid = next_pid + 1
                table.insert(pending, callback)
                return next_pid
            end,
        }, {
            __call = function(_, command)
                table.insert(kills, command)
            end,
        }),
    }
    local gears = { timer = function(args)
        local timer = { args = args }
        function timer:start() self.started = true end
        function timer:stop() self.stopped = true end
        table.insert(timers, timer)
        return timer
    end }
    local loader, err
    if _VERSION == "Lua 5.1" then
        loader, err = loadstring(helper, "volume_helper")
        if loader then setfenv(loader, { awful = awful, gears = gears, tostring = tostring }) end
    else
        loader, err = load(helper, "volume_helper", "t", { awful = awful, gears = gears, tostring = tostring })
    end
    assert(loader, err)
    local make_poller = loader()
    local reads = 0
    local poll = make_poller(function() reads = reads + 1 end)

    for _ = 1, 20 do poll() end
    assert(#pending == 1, path .. ": rapid refreshes must coalesce to one outstanding spawn")
    pending[1]("Volume: 0.50", "", "", 0)
    assert(reads == 1 and timers[1].stopped, path .. ": callback must complete and stop rescue timer")
    poll()
    assert(#pending == 2, path .. ": a completed callback must permit a later poll")

    timers[2].args.callback()
    assert(#kills == 1 and kills[1][1] == "kill" and kills[1][2] == "-KILL",
        path .. ": rescue timer must terminate stalled process (kills=" .. #kills .. ")")
    poll()
    assert(#pending == 3, path .. ": timeout must recover and permit a later poll")
    pending[2]("", "", "", 1) -- A late callback from the timed-out process is ignored.
    assert(reads == 1, path .. ": stale callback must not consume a newer request")
end

print("Panel volume guard tests passed")

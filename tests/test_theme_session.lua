-- Mock Awesome so workspace restoration tests never touch a real desktop.
local screens = {}
screen = setmetatable({}, {
    __index = function(_, index) return screens[index] end,
    __call = function(_, _, previous)
        return screens[previous and previous.index + 1 or 1]
    end,
})
local focused, pending, restarted
local function reset()
    screens = {}
    for i = 1, 2 do
        screens[i] = { index = i, tags = {} }
        for j = 1, 3 do screens[i].tags[j] = { selected = j == 1 } end
    end
    focused = screens[1]
end
package.preload["awful"] = function()
    return {
        screen = {
            focused = function() return focused end,
            focus = function(s) focused = s end,
        },
        tag = { viewmore = function(tags, s)
            for _, tag in ipairs(s.tags) do tag.selected = false end
            for _, tag in ipairs(tags) do tag.selected = true end
        end },
    }
end
package.preload["gears"] = function()
    return { timer = { start_new = function(_, callback) pending = callback end } }
end
package.preload["gears.filesystem"] = function()
    return { get_cache_dir = function() return arg[2] .. "/" end }
end
awesome = { restart = function() restarted = true end }
local session = dofile(arg[1])
reset()
session.restore() -- No snapshot: retain defaults.
assert(screens[1].tags[1].selected)
screens[1].tags[1].selected = false
screens[1].tags[2].selected = true
screens[2].tags[3].selected = true -- Multiple selected tags must survive too.
focused = screens[2]
session.restart()
assert(not restarted and pending)
assert(pending() == false and restarted)
reset()
session.restore()
assert(not screens[1].tags[1].selected and screens[1].tags[2].selected)
assert(screens[2].tags[1].selected and screens[2].tags[3].selected)
assert(focused == screens[2])
reset()
session.restore() -- Snapshot was consumed, not retained for future logins.
assert(screens[1].tags[1].selected and focused == screens[1])
screens[1].tags[1].selected = false
screens[1].tags[3].selected = true
focused = screens[2]
session.restart()
reset()
screens[2] = nil -- Disconnected monitor.
screens[1].tags[3] = nil -- Removed workspace: keep the valid default selection.
session.restore()
assert(screens[1].tags[1].selected and focused == screens[1])
print("workspace restoration tests passed")

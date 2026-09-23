-- One-shot workspace snapshot for theme reloads, not a saved login session.
local awful = require("awful")
local gears = require("gears")
local gfs = require("gears.filesystem")
local M = {}
local display = (os.getenv("DISPLAY") or "default"):gsub("[^%w_.-]", "_")
local path = gfs.get_cache_dir() .. "theme-workspaces-" .. display

function M.restore()
    local file = io.open(path, "r")
    if not file then return end
    local snapshot = file:read("*a")
    file:close()
    os.remove(path) -- Consume it; a later fresh login must use normal defaults.
    local focused = tonumber(snapshot:match("^focus (%d+)\n"))
    for index, selection in snapshot:gmatch("\nscreen (%d+) ([%d,]+)") do
        local s = screen[tonumber(index)]
        if s then
            local tags = {}
            for tag_index in selection:gmatch("%d+") do
                local tag = s.tags[tonumber(tag_index)]
                if tag then tags[#tags + 1] = tag end
            end
            if #tags > 0 then awful.tag.viewmore(tags, s) end
        end
    end
    if focused and screen[focused] then awful.screen.focus(screen[focused]) end
end

function M.restart()
    local lines = { "focus " .. awful.screen.focused().index }
    for s in screen do
        local selected = {}
        for index, tag in ipairs(s.tags) do
            if tag.selected then selected[#selected + 1] = tostring(index) end
        end
        if #selected > 0 then
            lines[#lines + 1] = "screen " .. s.index .. " " .. table.concat(selected, ",")
        end
    end
    local file = assert(io.open(path .. ".new", "w"))
    assert(file:write(table.concat(lines, "\n") .. "\n"))
    assert(file:close())
    assert(os.rename(path .. ".new", path))
    -- Reply to awesome-client before disconnecting its D-Bus connection.
    gears.timer.start_new(0.1, function()
        awesome.restart()
        return false
    end)
end

return M

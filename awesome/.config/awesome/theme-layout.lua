-- Layout selection is independent of themectl's active color palette.
local gfs = require("gears.filesystem")
local M = {}
local state_dir = (os.getenv("XDG_STATE_HOME") or os.getenv("HOME") .. "/.local/state") .. "/awesome/"
local state_path = state_dir .. "theme-layout"

local function available(name)
    return type(name) == "string" and name:match("^[a-z0-9][a-z0-9-]*$")
        and gfs.file_readable(gfs.get_configuration_dir() .. "themes/" .. name .. "/theme.lua")
end

function M.get()
    local name = os.getenv("AWESOME_THEME")
    if not name or name == "" then
        local file = io.open(state_path, "r")
        if file then
            name = file:read("*l")
            file:close()
        end
    end
    return available(name) and name or "powerarrow"
end

-- Check a selection the running process would accept, without writing state
-- or restarting. Returns the name, or raises.
function M.validate(name)
    assert(available(name), "Unknown AwesomeWM layout: " .. tostring(name))
    local override = os.getenv("AWESOME_THEME")
    assert(not override or override == "" or override == name,
        "AWESOME_THEME overrides the saved layout; unset it in your login environment first")
    return name
end

function M.set(name)
    M.validate(name)
    gfs.make_directories(state_dir)
    local file = assert(io.open(state_path .. ".new", "w"))
    assert(file:write(name .. "\n"))
    assert(file:close())
    assert(os.rename(state_path .. ".new", state_path))
    require("theme-session").restart()
    return name
end

return M

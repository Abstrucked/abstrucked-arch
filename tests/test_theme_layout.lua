-- Exercise persistent layout selection without restarting the host desktop.
local module_path, config_dir = arg[1], arg[2]
local getenv = os.getenv
local override
os.getenv = function(name)
    if name == "AWESOME_THEME" then return override end
    return getenv(name)
end
local state_path = getenv("XDG_STATE_HOME") .. "/awesome/theme-layout"
local restarts = 0
package.loaded["gears.filesystem"] = {
    get_configuration_dir = function() return config_dir .. "/" end,
    make_directories = function() end, -- Python prepared only this test's directory.
    file_readable = function(path)
        local file = io.open(path, "r")
        if not file then return false end
        file:close()
        return true
    end,
}
package.loaded["theme-session"] = { restart = function() restarts = restarts + 1 end }

local layout = dofile(module_path)
assert(layout.get() == "powerarrow", "fresh installs retain the existing default")
assert(layout.set("mono") == "mono")
assert(restarts == 1, "selection uses the workspace-preserving restart")
assert(dofile(module_path).get() == "mono", "selection survives a new Lua session")

override = "powerarrow"
assert(layout.get() == "powerarrow", "explicit environment wins over saved selection")
assert(not pcall(layout.set, "mono"), "do not silently save an ineffective selection")
assert(restarts == 1)
override = nil
assert(layout.get() == "mono")
assert(not pcall(layout.set, "../mono"), "reject path traversal")
assert(not pcall(layout.set, "missing"), "reject uninstalled layouts")
assert(layout.get() == "mono", "failed selections preserve the saved layout")
assert(restarts == 1)

local file = assert(io.open(state_path, "w"))
file:write("missing\n")
file:close()
assert(layout.get() == "powerarrow", "removed layouts fall back to Powerarrow")
override = "../../bad"
assert(layout.get() == "powerarrow", "invalid environment cannot escape the theme directory")
override = ""
assert(layout.set("mono") == "mono")
assert(layout.get() == "mono", "an empty environment override is ignored")
assert(layout.set("powerarrow") == "powerarrow", "switching back is supported")
assert(restarts == 3)
assert(layout.set("slate") == "slate", "new layouts use the same selection path")
assert(dofile(module_path).get() == "slate", "Slate survives a new Lua session")
assert(restarts == 4)
os.getenv = getenv

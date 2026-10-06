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

local function saved()
    local file = io.open(state_path, "r")
    if not file then return nil end
    local name = file:read("*l")
    file:close()
    return name
end

local layout = dofile(module_path)

-- validate() reports what set() would accept without writing or restarting.
assert(layout.validate("mono") == "mono", "validate returns the name")
assert(layout.validate("tide") == "tide", "Tide validates like any other layout")
assert(restarts == 0, "validate never restarts the desktop")
assert(saved() == nil, "validate never writes the saved layout")
assert(not pcall(layout.validate, "missing"), "validate rejects uninstalled layouts")
assert(not pcall(layout.validate, "../mono"), "validate rejects path traversal")
assert(restarts == 0 and saved() == nil, "failed validation is equally mutation-free")
override = "powerarrow"
assert(not pcall(layout.validate, "mono"), "validate checks the running process override")
assert(layout.validate("powerarrow") == "powerarrow", "validate accepts the effective override")
override = nil
assert(restarts == 0 and saved() == nil)

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
assert(layout.set("tide") == "tide", "Tide uses the same selection path")
assert(dofile(module_path).get() == "tide", "Tide survives a new Lua session")
assert(restarts == 5)
assert(layout.validate("mono") == "mono", "validate keeps working after a selection")
assert(restarts == 5 and saved() == "tide", "validate stays mutation-free afterwards")
os.getenv = getenv

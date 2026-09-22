-- Usage: lua render.lua <palette.lua> <template>
-- Renders <template> to stdout, replacing {{key}} / {{key|format}} with values
-- from the palette. Keys may be nested with dots (ansi.normal.red).
--
-- palettes/_defaults.lua, when present, returns a function(palette, mix) whose
-- table fills in every key the palette leaves out, so a palette imported from
-- an Omarchy colors.toml only has to carry the colors it actually has.
--
-- Formats (colors only):
--   (none)     #rrggbb
--   nohash     rrggbb
--   rgb        r, g, b
--   rgba       rgba(rrggbbff)        Hyprland
--   rgba:aa    rgba(rrggbbaa)        Hyprland, aa is hex alpha
--   css:0.5    rgba(r, g, b, 0.5)    CSS

local palette_path, template_path = arg[1], arg[2]
if not palette_path or not template_path then
  io.stderr:write("usage: render.lua <palette.lua> <template>\n")
  os.exit(2)
end

local function fail(msg)
  io.stderr:write("render: " .. msg .. "\n")
  os.exit(1)
end

local ok, palette = pcall(dofile, palette_path)
if not ok then fail("cannot load palette " .. palette_path .. ": " .. tostring(palette)) end

-- Blend two #rrggbb colors. amount is 0..1, 0 being all of `a`.
local function mix(a, b, amount)
  local ha, hb = tostring(a):match("^#(%x%x%x%x%x%x)$"), tostring(b):match("^#(%x%x%x%x%x%x)$")
  if not ha or not hb then fail("mix needs two #rrggbb colors, got " .. tostring(a) .. " and " .. tostring(b)) end
  local out = "#"
  for i = 1, 5, 2 do
    local ca = tonumber(ha:sub(i, i + 1), 16)
    local cb = tonumber(hb:sub(i, i + 1), 16)
    out = out .. ("%02x"):format(math.floor(ca * (1 - amount) + cb * amount + 0.5))
  end
  return out
end

-- Recursively fill only the keys the palette does not already define.
local function fill(target, source)
  for key, value in pairs(source) do
    if type(value) == "table" then
      if type(target[key]) ~= "table" then target[key] = {} end
      fill(target[key], value)
    elseif target[key] == nil then
      target[key] = value
    end
  end
end

local defaults_path = (palette_path:match("^(.*[/\\])") or "./") .. "_defaults.lua"
local defaults_file = io.open(defaults_path, "r")
if defaults_file then
  defaults_file:close()
  local loaded_ok, build_defaults = pcall(dofile, defaults_path)
  if not loaded_ok then fail("cannot load " .. defaults_path .. ": " .. tostring(build_defaults)) end
  if type(build_defaults) ~= "function" then fail(defaults_path .. " must return a function(palette, mix)") end
  local built_ok, defaults = pcall(build_defaults, palette, mix)
  if not built_ok then fail("building defaults failed: " .. tostring(defaults)) end
  fill(palette, defaults)
end

local function lookup(key)
  local v = palette
  for part in key:gmatch("[^.]+") do
    if type(v) ~= "table" then fail("palette has no key '" .. key .. "'") end
    v = v[part]
  end
  if v == nil or type(v) == "table" then fail("palette has no value for '" .. key .. "'") end
  return v
end

local function format(key, value, fmt)
  if not fmt or fmt == "" then return tostring(value) end
  local hex = tostring(value):match("^#(%x%x%x%x%x%x)$")
  if not hex then fail("'" .. key .. "' is not a #rrggbb color, cannot apply '" .. fmt .. "'") end
  local name, arg1 = fmt:match("^(%a+):?(.*)$")
  local r, g, b = tonumber(hex:sub(1, 2), 16), tonumber(hex:sub(3, 4), 16), tonumber(hex:sub(5, 6), 16)
  if name == "nohash" then return hex end
  if name == "rgb" then return ("%d, %d, %d"):format(r, g, b) end
  if name == "rgba" then return "rgba(" .. hex .. (arg1 ~= "" and arg1 or "ff") .. ")" end
  if name == "css" then return ("rgba(%d, %d, %d, %s)"):format(r, g, b, arg1 ~= "" and arg1 or "1") end
  fail("unknown format '" .. fmt .. "' for '" .. key .. "'")
end

local f = io.open(template_path, "rb")
if not f then fail("cannot read template " .. template_path) end
local text = f:read("a")
f:close()

io.write((text:gsub("{{(.-)}}", function(expr)
  local key, fmt = expr:match("^%s*([%w_%.]+)%s*|?%s*(.-)%s*$")
  if not key then fail("bad placeholder {{" .. expr .. "}} in " .. template_path) end
  return format(key, lookup(key), fmt)
end)))

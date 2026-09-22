-- Usage: lua render.lua <palette.lua> <template>
-- Renders <template> to stdout, replacing {{key}} / {{key|format}} with values
-- from the palette. Keys may be nested with dots (ansi.normal.red).
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

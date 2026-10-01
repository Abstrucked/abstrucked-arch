-- Small monochrome vector icons, independent of installed icon fonts.
local cairo = require("lgi").cairo
local gears = require("gears")
local cache = {}
local M = {}

function M.get(name, color, size)
    local key = name .. color .. size
    if cache[key] then return cache[key] end
    local image = cairo.ImageSurface.create(cairo.Format.ARGB32, size, size)
    local cr = cairo.Context(image)
    cr:scale(size / 24, size / 24)
    cr:set_source(gears.color(color))
    cr:set_line_width(1.6)
    cr:set_line_cap(cairo.LineCap.ROUND)
    cr:set_line_join(cairo.LineJoin.ROUND)
    local function line(x1, y1, x2, y2)
        cr:move_to(x1, y1)
        cr:line_to(x2, y2)
    end
    if name == "launcher" then
        for _, x in ipairs({ 3, 14 }) do
            for _, y in ipairs({ 3, 14 }) do cr:rectangle(x, y, 7, 7) end
        end
    elseif name == "volume" then
        cr:move_to(11, 4)
        cr:line_to(6, 8)
        cr:line_to(3, 8)
        cr:line_to(3, 16)
        cr:line_to(6, 16)
        cr:line_to(11, 20)
        cr:close_path()
        cr:move_to(15, 8)
        cr:curve_to(18, 10, 18, 14, 15, 16)
        cr:move_to(18, 5)
        cr:curve_to(23, 9, 23, 15, 18, 19)
    elseif name == "battery" then
        cr:rectangle(2, 6, 17, 12)
        cr:rectangle(5, 9, 10, 6)
        line(22, 10, 22, 14)
    elseif name == "network" then
        cr:move_to(2, 8)
        cr:curve_to(8, 3, 16, 3, 22, 8)
        cr:move_to(5, 12)
        cr:curve_to(9, 8, 15, 8, 19, 12)
        cr:move_to(8, 16)
        cr:curve_to(11, 13, 13, 13, 16, 16)
        line(12, 20, 12.1, 20)
    elseif name == "power" then
        line(12, 3, 12, 12)
        cr:move_to(7, 5)
        cr:curve_to(-3, 12, 5, 22, 12, 21)
        cr:curve_to(20, 22, 27, 12, 17, 5)
    end
    cr:stroke()
    cache[key] = image
    return image
end

return M

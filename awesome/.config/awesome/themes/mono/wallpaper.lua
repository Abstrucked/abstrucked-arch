-- Original sculpted wallpaper, redrawn at screen resolution with the palette.
local cairo = require("lgi").cairo
local gears = require("gears")
local style = require("themes.mono.style")

return function(c, s)
    local image = cairo.ImageSurface.create(cairo.Format.RGB24, s.geometry.width, s.geometry.height)
    local cr = cairo.Context(image)
    cr:scale(s.geometry.width / 1600, s.geometry.height / 900)
    local function gradient(from, to, a, b)
        cr:set_source(gears.color({ type = "linear", from = from, to = to, stops = { { 0, a }, { 1, b } } }))
    end

    gradient({ 0, 0 }, { 1600, 900 }, c.bg, style.mix(c.bg, c.accent, 0.10))
    cr:paint()

    cr:move_to(600, 900)
    cr:curve_to(818, 841, 1026, 789, 1047, 558)
    cr:curve_to(1068, 327, 1031, 140, 1295, 52)
    cr:curve_to(1559, -36, 1770, 96, 1790, 244)
    cr:line_to(1790, 900)
    cr:close_path()
    gradient({ 650, 900 }, { 1550, 0 }, style.mix(c.bg, c.accent, 0.04), style.mix(c.bg, c.accent, 0.28))
    cr:fill()

    cr:move_to(771, 900)
    cr:curve_to(891, 724, 1167, 664, 1187, 459)
    cr:curve_to(1207, 254, 1130, 103, 1378, 77)
    cr:curve_to(1577, 56, 1673, 126, 1688, 263)
    cr:line_to(1688, 900)
    cr:close_path()
    gradient({ 750, 900 }, { 1500, 250 }, c.bg, style.mix(c.bg, c.accent, 0.13))
    cr:fill()

    cr:move_to(1231, 900)
    cr:curve_to(1020, 727, 1125, 608, 1363, 527)
    cr:curve_to(1601, 446, 1652, 425, 1687, 219)
    cr:line_to(1687, 900)
    cr:close_path()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.08)))
    cr:fill()
    return image
end

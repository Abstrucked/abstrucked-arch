-- The preview's ocean contours drawn at each screen's native resolution.
local cairo = require("lgi").cairo
local gears = require("gears")
local style = require("themes.mono.style")

return function(c, s)
    local width, height = s.geometry.width, s.geometry.height
    local image = cairo.ImageSurface.create(cairo.Format.RGB24, width, height)
    local cr = cairo.Context(image)
    local scale = math.max(width / 1600, height / 900)
    cr:translate((width - 1600 * scale) / 2, (height - 900 * scale) / 2)
    cr:scale(scale, scale)
    local function gradient(x, y, a, b)
        local pattern = cairo.Pattern.create_linear(0, 0, x, y)
        for i, color in ipairs({ a, b }) do
            local r, g, blue = gears.color.parse_color(color)
            pattern:add_color_stop_rgb(i - 1, r, g, blue)
        end
        return pattern
    end
    cr:set_source(gradient(1280, 900, c.bg, style.mix(c.bg, c.accent, 0.15)))
    cr:paint()
    cr:move_to(730, 900)
    cr:curve_to(920, 700, 840, 380, 1160, 280)
    cr:curve_to(1480, 180, 1536, 64, 1660, -30)
    cr:line_to(1660, 900)
    cr:close_path()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.22)))
    cr:fill()
    local function wave_one()
        cr:move_to(960, 900)
        cr:curve_to(850, 584, 1213, 394, 1170, 218)
        cr:curve_to(1127, 42, 1440, -60, 1620, -30)
    end
    local function wave_two()
        cr:move_to(1265, 900)
        cr:curve_to(888, 668, 1210, 428, 1300, 289)
        cr:curve_to(1390, 150, 1280, 27, 1480, -30)
    end
    wave_one()
    cr:line_to(1620, 900)
    cr:close_path()
    cr:set_source(gradient(160, 900, style.mix(c.bg, c.accent, 0.55), style.mix(c.bg, c.accent, 0.24)))
    cr:fill()
    wave_two()
    cr:line_to(1640, -30)
    cr:line_to(1640, 900)
    cr:close_path()
    cr:set_source(gradient(1600, 900, style.mix(c.bg, c.accent, 0.22), style.mix(c.bg, c.accent, 0.4)))
    cr:fill()
    cr:move_to(1490, 940)
    cr:curve_to(1032, 741, 1261, 535, 1425, 385)
    cr:curve_to(1589, 235, 1436, 37, 1630, -5)
    cr:line_to(1630, 940)
    cr:close_path()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.17)))
    cr:fill()
    wave_one()
    wave_two()
    cr:set_source(gears.color(c.accent .. "38"))
    cr:set_line_width(2)
    cr:stroke()
    return image
end

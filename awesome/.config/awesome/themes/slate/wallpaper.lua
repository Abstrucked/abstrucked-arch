-- An original architectural study, rendered at the output's own resolution.
local cairo = require("lgi").cairo
local gears = require("gears")
local style = require("themes.mono.style")

return function(c, s)
    local width, height = s.geometry.width, s.geometry.height
    local image = cairo.ImageSurface.create(cairo.Format.RGB24, width, height)
    local cr = cairo.Context(image)
    -- Uniform scaling keeps the circles round on ultrawide and portrait outputs.
    local scale = math.max(width / 1600, height / 900)
    cr:translate((width - 1600 * scale) / 2, (height - 900 * scale) / 2)
    cr:scale(scale, scale)
    cr:set_source(gears.color(c.bg))
    cr:paint()

    cr:move_to(-800, 1400)
    cr:line_to(2000, 1400)
    cr:line_to(2000, 180)
    cr:close_path()
    cr:set_source(gears.color({
        type = "linear", from = { 500, 900 }, to = { 1300, 250 },
        stops = { { 0, style.mix(c.bg, c.fg, 0.018) }, { 1, style.mix(c.bg, c.accent, 0.065) } },
    }))
    cr:fill()

    cr:set_line_width(1)
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.09)))
    cr:move_to(-800, 1400)
    cr:line_to(2000, 180)
    cr:stroke()

    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.045)))
    cr:arc(1350, 735, 310, 0, math.pi * 2)
    cr:fill()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.16)))
    cr:arc(1350, 735, 310, 0, math.pi * 2)
    cr:stroke()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.065)))
    cr:arc(1350, 735, 348, 0, math.pi * 2)
    cr:stroke()
    return image
end

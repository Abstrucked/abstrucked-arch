-- Two faint rings rising from the lower right, drawn at the output's resolution.
local cairo = require("lgi").cairo
local gears = require("gears")
local style = require("themes.mono.style")

return function(c, s)
    local width, height = s.geometry.width, s.geometry.height
    local image = cairo.ImageSurface.create(cairo.Format.RGB24, width, height)
    local cr = cairo.Context(image)
    -- Designed on a 1440x900 canvas; uniform scaling keeps the rings round.
    local scale = math.max(width / 1440, height / 900)
    cr:translate((width - 1440 * scale) / 2, (height - 900 * scale) / 2)
    cr:scale(scale, scale)
    cr:set_source(gears.color(c.bg))
    cr:paint()

    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.025)))
    cr:arc(1180, 1040, 300, 0, math.pi * 2)
    cr:fill()

    cr:set_line_width(1)
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.09)))
    cr:arc(1180, 1040, 430, 0, math.pi * 2)
    cr:stroke()
    cr:set_source(gears.color(style.mix(c.bg, c.accent, 0.16)))
    cr:arc(1180, 1040, 560, 0, math.pi * 2)
    cr:stroke()
    return image
end

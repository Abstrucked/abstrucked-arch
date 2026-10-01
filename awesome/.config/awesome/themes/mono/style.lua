-- Pure palette helpers, shared by the panel, client decorations and wallpaper.
local M = {}

function M.mix(a, b, amount)
    local out = "#"
    for i = 2, 6, 2 do
        local left, right = tonumber(a:sub(i, i + 1), 16), tonumber(b:sub(i, i + 1), 16)
        out = out .. string.format("%02x", math.floor(left * (1 - amount) + right * amount + 0.5))
    end
    return out
end

local function luminance(color)
    local function channel(index)
        local value = tonumber(color:sub(index, index + 1), 16) / 255
        return value <= 0.04045 and value / 12.92 or ((value + 0.055) / 1.055) ^ 2.4
    end
    return 0.2126 * channel(2) + 0.7152 * channel(4) + 0.0722 * channel(6)
end

local function contrast(a, b)
    local left, right = luminance(a), luminance(b)
    return (math.max(left, right) + 0.05) / (math.min(left, right) + 0.05)
end

function M.on(background, c)
    local fg = contrast(background, c.bg) >= contrast(background, c.fg) and c.bg or c.fg
    if contrast(background, fg) >= 4.5 then return fg end
    return contrast(background, "#000000") >= contrast(background, "#ffffff") and "#000000" or "#ffffff"
end

return M

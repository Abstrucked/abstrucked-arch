local awful = require("awful")
local gears = require("gears")
local lain = require("lain")
local naughty = require("naughty")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local icons = require("themes.mono.icons")
local power_mode = require("awesome-wm-widgets.power-mode-widget.power-mode")

-- Built once and shared by all bars, so hotplugging screens adds no pollers.
return function(args)
    local c, theme = args.colors, args.theme
    local widgets = {}
    local function text(value)
        return wibox.widget({ text = value, font = theme.widget_font, widget = wibox.widget.textbox })
    end
    local function image(name, color)
        return wibox.widget({
            image = icons.get(name, color or c.fg, dpi(16)),
            forced_width = dpi(16), forced_height = dpi(16), widget = wibox.widget.imagebox,
        })
    end
    local function group(...)
        return wibox.widget({ spacing = dpi(6), layout = wibox.layout.fixed.horizontal, ... })
    end
    local function rate(value)
        value = math.max(0, tonumber(value) or 0)
        return value >= 1024 and string.format("%.1f MiB/s", value / 1024) or string.format("%.0f KiB/s", value)
    end

    local volume_icon, volume_text = image("volume"), text("—")
    local volume_tooltip = "Audio status unavailable"
    -- Fixed horizontal layouts give children the full row height; imageboxes
    -- paint from the top unless a place container centers their 16 px image.
    widgets.volume = group(wibox.container.place(volume_icon, "center", "center"), volume_text)
    volume_text.forced_width = dpi(32)
    volume_text.align = "right"
    local function volume_update(_, stdout, _, _, code)
        local level = code == 0 and tonumber(stdout:match("Volume:%s*([%d%.]+)"))
        if not level then
            volume_text.text = "—"
            volume_tooltip = "Audio status unavailable"
            return
        end
        local muted = stdout:find("[MUTED]", 1, true)
        volume_text.text = muted and "off" or string.format("%.0f%%", level * 100)
        volume_icon.image = icons.get("volume", muted and theme.muted or c.fg, dpi(16))
        volume_tooltip = "Volume: " .. volume_text.text .. "\nClick to mute · scroll to adjust"
    end
    local volume_command = { "wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@" }
    awful.widget.watch(volume_command, 2, volume_update, volume_text)
    local function adjust(command)
        awful.spawn.easy_async(command, function()
            awful.spawn.easy_async(volume_command, function(stdout, stderr, reason, code)
                volume_update(volume_text, stdout, stderr, reason, code)
            end)
        end)
    end
    widgets.volume:buttons(gears.table.join(
        awful.button({}, 1, function() adjust({ "wpctl", "set-mute", "@DEFAULT_AUDIO_SINK@", "toggle" }) end),
        awful.button({}, 4, function() adjust({ "wpctl", "set-volume", "-l", "1.0", "@DEFAULT_AUDIO_SINK@", "5%+" }) end),
        awful.button({}, 5, function() adjust({ "wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", "5%-" }) end)
    ))
    awful.tooltip({ objects = { widgets.volume }, timer_function = function() return volume_tooltip end })

    local network_icon, network_tooltip = image("network", theme.muted), "Network status unavailable"
    widgets.network = wibox.container.place(network_icon, "center", "center")
    widgets.net = lain.widget.net({
        notify = "off",
        settings = function()
            local connected = false
            for _, device in pairs(net_now.devices or {}) do
                if device.carrier == "1" then connected = true end
            end
            network_icon.image = icons.get("network", connected and c.accent or theme.muted, dpi(16))
            network_tooltip = (connected and "Network connected" or "Network disconnected")
                .. "\nDown " .. rate(net_now.received) .. " · Up " .. rate(net_now.sent)
        end,
    })
    awful.tooltip({ objects = { widgets.network }, timer_function = function() return network_tooltip end })

    local battery_icon, battery_text = image("battery"), text("")
    local battery_tooltip = "Power"
    widgets.battery = group(wibox.container.place(battery_icon, "center", "center"), battery_text)
    widgets.bat = lain.widget.bat({
        timeout = 5,
        notification_preset = { fg = c.fg, bg = c.surface, font = theme.font },
        settings = function()
            local percent = tonumber(bat_now.perc)
            widgets.battery.visible = percent ~= nil and bat_now.status ~= "N/A"
            if not widgets.battery.visible then return end
            local charging = bat_now.ac_status == 1
            local color = not charging and percent <= 15 and (c.red or c.accent) or c.fg
            battery_icon.image = icons.get("battery", color, dpi(16))
            battery_text.text = (charging and "+" or "") .. string.format("%.0f%%", percent)
            battery_tooltip = (bat_now.status or "Battery") .. " · " .. battery_text.text
                .. "\nClick for power profiles"
        end,
    })
    widgets.battery:buttons(gears.table.join(awful.button({}, 1, function() power_mode.launch() end)))
    awful.tooltip({ objects = { widgets.battery }, timer_function = function() return battery_tooltip end })

    local stats = { cpu = "CPU —", memory = "Memory —", disk = "Disk —" }
    widgets.cpu = lain.widget.cpu({ settings = function() stats.cpu = "CPU " .. cpu_now.usage .. "%" end })
    widgets.mem = lain.widget.mem({
        settings = function() stats.memory = string.format("Memory %.1f GiB", (tonumber(mem_now.used) or 0) / 1024) end,
    })
    widgets.fs = lain.widget.fs({
        followtag = true,
        notification_preset = { fg = c.fg, bg = c.surface, font = theme.font },
        settings = function()
            local root_fs = fs_now["/"]
            if root_fs then stats.disk = string.format("Disk %.1f%s free", root_fs.free, root_fs.units) end
        end,
    })
    local function summary() return stats.cpu .. "\n" .. stats.memory .. "\n" .. stats.disk end
    local dot = wibox.widget({
        forced_width = dpi(5), forced_height = dpi(5), shape = gears.shape.circle,
        color = c.accent, widget = wibox.widget.separator,
    })
    widgets.system = wibox.container.place(dot, "center", "center")
    widgets.system.forced_width = dpi(12)
    awful.tooltip({ objects = { widgets.system }, timer_function = summary })
    widgets.system:buttons(gears.table.join(awful.button({}, 1, function()
        naughty.notify({ title = "System / Mono", text = summary(), screen = awful.screen.focused() })
    end)))
    return widgets
end

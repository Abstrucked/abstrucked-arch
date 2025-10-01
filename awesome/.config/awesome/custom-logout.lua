-------------------------------------------------
-- Custom Logout Popup for Awesome Window Manager
-- Replaces the broken awesome-wm-widgets logout widget
-- Provides a simple popup with logout options
-------------------------------------------------

local awful = require("awful")
local capi = { keygrabber = keygrabber }
local wibox = require("wibox")
local gears = require("gears")
local beautiful = require("beautiful")



local w = wibox {
    bg = beautiful.bg_normal or "#000000",
    ontop = true,
    height = 200,
    width = 400,
    shape = function(cr, width, height)
        gears.shape.rounded_rect(cr, width, height, 8)
    end
}

local action = wibox.widget {
    text = ' ',
    widget = wibox.widget.textbox
}

local phrase_widget = wibox.widget {
    align = 'center',
    widget = wibox.widget.textbox
}

local function create_button(text, action_name, onclick)
    local button = wibox.widget {
        {
            text = text,
            align = 'center',
            widget = wibox.widget.textbox
        },
        bg = beautiful.bg_focus or "#333333",
        fg = beautiful.fg_normal or "#ffffff",
        shape = gears.shape.rounded_rect,
        widget = wibox.container.background
    }

    button:buttons(awful.util.table.join(
        awful.button({}, 1, function()
            onclick()
            w.visible = false
            capi.keygrabber.stop()
        end)
    ))

    button:connect_signal("mouse::enter", function() action:set_text(action_name) end)
    button:connect_signal("mouse::leave", function() action:set_text(' ') end)

    return button
end

local function launch(args)
    args = args or {}
    local phrases = args.phrases or {'Goodbye!'}
    local onlogout = args.onlogout or function() awesome.quit() end
    local onlock = args.onlock or function() awful.spawn.with_shell("slock") end
    local onreboot = args.onreboot or function() awful.spawn.with_shell("reboot") end
    local onsuspend = args.onsuspend or function() awful.spawn.with_shell("systemctl suspend") end
    local onpoweroff = args.onpoweroff or function() awful.spawn.with_shell("shutdown now") end

    if #phrases > 0 then
        phrase_widget:set_markup('<span color="' .. (beautiful.fg_normal or "#ffffff") .. '" size="20000">' .. phrases[math.random(#phrases)] .. '</span>')
    end

    w:setup {
        {
            phrase_widget,
            {
                {
                    create_button('Logout', 'Log Out (l)', onlogout),
                    create_button('Lock', 'Lock (k)', onlock),
                    create_button('Reboot', 'Reboot (r)', onreboot),
                    create_button('Suspend', 'Suspend (u)', onsuspend),
                    create_button('Power Off', 'Power Off (s)', onpoweroff),
                    spacing = 8,
                    layout = wibox.layout.fixed.horizontal
                },
                valign = 'center',
                layout = wibox.container.place
            },
            {
                action,
                halign = 'center',
                layout = wibox.container.place
            },
            spacing = 32,
            layout = wibox.layout.fixed.vertical
        },
        valign = 'center',
        layout = wibox.container.place
    }

    w.screen = mouse.screen
    w.visible = true

    awful.placement.centered(w)
    capi.keygrabber.run(function(_, key, event)
        if event == "release" then return end
        if key then
            if key == 'Escape' then
                phrase_widget:set_text('')
                capi.keygrabber.stop()
                w.visible = false
            elseif key == 's' then onpoweroff()
            elseif key == 'r' then onreboot()
            elseif key == 'u' then onsuspend()
            elseif key == 'k' then onlock()
            elseif key == 'l' then onlogout()
            end

            if key == 'Escape' or string.match("srukl", key) then
                phrase_widget:set_text('')
                capi.keygrabber.stop()
                w.visible = false
            end
        end
    end)
end

return {
    launch = launch
}
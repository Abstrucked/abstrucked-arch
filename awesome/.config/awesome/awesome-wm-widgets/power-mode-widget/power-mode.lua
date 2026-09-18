-------------------------------------------------
-- Power Mode widget for Awesome Window Manager
-- Switches between battery save, balanced, and performance modes
-- using ryzenadj for AMD Ryzen processors
-------------------------------------------------

local awful = require("awful")
local wibox = require("wibox")
local gears = require("gears")
local beautiful = require("beautiful")
local naughty = require("naughty")
local mouse = _G.mouse

local power_mode = {}

-- Power mode definitions
local modes = {
    {
        id = "battery-save",
        name = "Battery Save",
        icon = "󰁹",
        key = "1",
        alt_key = "b",
        script = "batt-save-mode.sh",
        color = "#a6e3a1",
        desc = "1.6GHz, 10W, 70°C"
    },
    {
        id = "balanced",
        name = "Balanced",
        icon = "󰗑",
        key = "2",
        alt_key = "a",
        script = "balanced-mode.sh",
        color = "#89b4fa",
        desc = "2.1GHz, 15W, 80°C"
    },
    {
        id = "performance",
        name = "Performance",
        icon = "󰓅",
        key = "3",
        alt_key = "p",
        script = "perf-mode.sh",
        color = "#f38ba8",
        desc = "2.5GHz, 20W, 85°C"
    },
}

local state_dir = os.getenv("XDG_STATE_HOME") or (os.getenv("HOME") .. "/.local/state")
local state_file = state_dir .. "/awesome/power-mode"

local function load_current_mode()
    local file = io.open(state_file, "r")
    if not file then
        return 2
    end

    local saved_mode = file:read("*l")
    file:close()

    for index, mode in ipairs(modes) do
        if mode.id == saved_mode then
            return index
        end
    end

    return 2
end

-- Current mode tracking
local current_mode = load_current_mode()
local update_callback = nil
local active_keygrabber = nil
local status_notification = nil

-- Popup widget
local popup = wibox {
    bg = beautiful.popup_bg or "#313244",
    max_widget_size = 500,
    ontop = true,
    border_width = 0,
    shape_border_width = 0,
    height = 180,
    width = 380,
    shape = beautiful.popup_shape or function(cr, width, height)
        gears.shape.rounded_rect(cr, width, height, 8)
    end,
}

-- Action text widget
local action = wibox.widget {
    text = ' ',
    widget = wibox.widget.textbox
}

local function stop_popup()
    if active_keygrabber then
        active_keygrabber:stop()
    else
        popup.visible = false
    end
end

-- Title widget
local title_widget = wibox.widget {
    align = 'center',
    font = beautiful.font or "Hack Nerd Font 12",
    widget = wibox.widget.textbox
}

-- Create a mode button
local function create_button(mode, index)
    local is_active = (current_mode == index)
    local bg_color = is_active and mode.color or "#313244"
    local fg_color = is_active and "#1e1e2e" or (beautiful.fg_normal or "#cdd6f4")

    local button = wibox.widget {
        {
            {
                {
                    markup = '<span font="Hack Nerd Font 16" color="' .. fg_color .. '">' .. mode.icon .. '</span>',
                    align = 'center',
                    widget = wibox.widget.textbox,
                },
                {
                    markup = '<span font="Hack Nerd Font 10" color="' .. fg_color .. '">' .. mode.name .. '</span>',
                    align = 'center',
                    widget = wibox.widget.textbox,
                },
                {
                    markup = '<span font="Hack Nerd Font 8" color="' .. fg_color .. '">' .. mode.desc .. '</span>',
                    align = 'center',
                    widget = wibox.widget.textbox,
                },
                spacing = 4,
                layout = wibox.layout.fixed.vertical,
            },
            margins = 12,
            widget = wibox.container.margin,
        },
        bg = bg_color,
        shape = function(cr, w, h)
            gears.shape.rounded_rect(cr, w, h, 8)
        end,
        widget = wibox.container.background,
    }

    -- Hover effects
    button:connect_signal("mouse::enter", function()
        if current_mode ~= index then
            button:set_bg("#45475a")
        end
    end)
    button:connect_signal("mouse::leave", function()
        if current_mode ~= index then
            button:set_bg("#313244")
        end
    end)

    -- Click handler
    button:buttons(awful.util.table.join(
        awful.button({}, 1, function()
            power_mode.set_mode(index)
            stop_popup()
        end)
    ))

    -- Hover action text
    button:connect_signal("mouse::enter", function()
        action:set_markup('<span color="' .. mode.color .. '"> ' .. mode.name .. '</span>')
    end)
    button:connect_signal("mouse::leave", function()
        action:set_text(' ')
    end)

    return button
end

-- Set power mode
function power_mode.set_mode(index)
    if index < 1 or index > #modes then return end

    local mode = modes[index]
    local script_path = os.getenv("HOME") .. "/.local/bin/" .. mode.script

    awful.spawn.easy_async({ "bash", script_path }, function(_, stderr, _, exit_code)
        if exit_code ~= 0 then
            naughty.notify({
                title = "Power Mode",
                text = "Could not enable " .. mode.name .. ": " .. stderr,
                timeout = 5,
                urgency = "critical",
            })
            return
        end

        current_mode = index
        naughty.notify({
            title = "Power Mode",
            text = mode.name .. " activated (" .. mode.desc .. ")",
            icon = nil,
            timeout = 3,
            fg = mode.color,
        })

        if update_callback then
            update_callback()
        end
    end)
end

-- Launch the popup
function power_mode.launch(args)
    args = args or {}

    stop_popup()

    local bg_color = args.bg_color or (beautiful.popup_bg or "#313244")
    local text_color = args.text_color or (beautiful.fg_normal or "#cdd6f4")

    popup:set_bg(bg_color)
    title_widget:set_markup('<span color="' .. text_color .. '" size="14000"> Power Mode </span>')

    popup:setup {
        {
            title_widget,
            {
                {
                    create_button(modes[1], 1),
                    create_button(modes[2], 2),
                    create_button(modes[3], 3),
                    spacing = 8,
                    layout = wibox.layout.fixed.horizontal,
                },
                valign = 'center',
                layout = wibox.container.place,
            },
            {
                action,
                halign = 'center',
                layout = wibox.container.place,
            },
            spacing = 16,
            layout = wibox.layout.fixed.vertical,
        },
        id = 'a',
        valign = 'center',
        layout = wibox.container.place,
    }

    popup.screen = args.screen or awful.screen.focused()

    -- Keygrabber for keyboard shortcuts
    local keygrabber_instance
    keygrabber_instance = awful.keygrabber({
        start_callback = function()
            popup.visible = true
            awful.placement.centered(popup)
        end,
        stop_callback = function()
            popup.visible = false
            if active_keygrabber == keygrabber_instance then
                active_keygrabber = nil
            end
        end,
        keypressed_callback = function(_, _, key, event)
            if event ~= "press" then
                return
            end

            for index, mode in ipairs(modes) do
                if key == mode.key or key == mode.alt_key then
                    power_mode.set_mode(index)
                    keygrabber_instance:stop()
                    return
                end
            end

            if key == "Escape" then
                keygrabber_instance:stop()
            end
        end,
    })

    active_keygrabber = keygrabber_instance
    keygrabber_instance:start()
end

-- Status bar widget
function power_mode.widget(args)
    args = args or {}

    local icon_font = args.icon_font or "Hack Nerd Font 14"
    local current_icon = modes[current_mode].icon
    local current_color = modes[current_mode].color

    local icon_widget = wibox.widget {
        markup = '<span font="' .. icon_font .. '" color="' .. current_color .. '">' .. current_icon .. '</span>',
        widget = wibox.widget.textbox,
    }

    local widget = wibox.widget {
        {
            icon_widget,
            margins = 4,
            widget = wibox.container.margin,
        },
        layout = wibox.layout.fixed.horizontal,
    }

    -- Update function
    update_callback = function()
        local new_icon = modes[current_mode].icon
        local new_color = modes[current_mode].color
        icon_widget:set_markup('<span font="' .. icon_font .. '" color="' .. new_color .. '">' .. new_icon .. '</span>')
    end

    -- Click to open popup
    widget:buttons(
        awful.util.table.join(
            awful.button({}, 1, function()
                if popup.visible then
                    stop_popup()
                else
                    args.screen = mouse.screen
                    power_mode.launch(args)
                end
            end)
        )
    )

    widget:connect_signal("mouse::enter", function()
        status_notification = naughty.notify({
            title = "Power Mode",
            text = modes[current_mode].name .. " (" .. modes[current_mode].desc .. ")\nClick to change",
            screen = mouse.screen,
            timeout = 0,
        })
    end)
    widget:connect_signal("mouse::leave", function()
        if status_notification then
            naughty.destroy(status_notification)
            status_notification = nil
        end
    end)

    return widget
end

return power_mode

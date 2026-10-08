-- Tide: an ocean contour wallpaper and a slim top desktop bar.
-- Floating workspaces leave room around softly rounded windows.
local awful = require("awful")
local gears = require("gears")
local gfs = require("gears.filesystem")
local lain = require("lain")
local naughty = require("naughty")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local c = require("themes.colors")
-- Reuse the existing palette helpers, vector icons and shared status pollers.
local style = require("themes.mono.style")
local icons = require("themes.mono.icons")
local build_widgets = require("themes.mono.widgets")
local wallpaper = require("themes.tide.wallpaper")
local run_shell = require("awesome-wm-widgets.run-shell-3.run-shell")
local logout = require("awesome-wm-widgets.logout-widget.logout")
local tag = tag
local theme = {}
local transparent = "#00000000"
local line = style.mix(c.bg, c.fg, 0.12)
local raised = style.mix(c.surface, c.fg, 0.06)
local shared_widgets

theme.name = "tide"
theme.system_title = "System / Tide"
-- Match the preview typography, with a sans fallback.
theme.font = "Inter, sans 10"
theme.widget_font = "JetBrains Mono 9"
theme.muted = c.muted or style.mix(c.bg, c.fg, 0.6)
theme.fg_normal = c.fg
theme.bg_normal = c.bg
theme.fg_focus = c.fg
theme.bg_focus = c.surface
theme.fg_urgent = style.on(c.red or c.accent, c)
theme.bg_urgent = c.red or c.accent
theme.useless_gap = dpi(24)
theme.gap_single_client = true
theme.border_width = dpi(1)
-- Quiet outlines keep floating windows distinct; focus brightens the border.
theme.border_normal = line
theme.border_focus = style.mix(c.accent, c.bg, 0.3)
theme.border_marked = c.accent
theme.keep_single_client_border = true
theme.titlebars_enabled = false
theme.titlebar_bg_normal = c.surface
theme.titlebar_bg_focus = c.surface
theme.titlebar_fg_normal = theme.muted
theme.titlebar_fg_focus = c.fg
theme.icon_theme = "Numix"

local function rounded(radius)
    return function(cr, width, height) gears.shape.rounded_rect(cr, width, height, dpi(radius)) end
end

theme.popup_bg = c.surface
theme.popup_fg = c.fg
theme.popup_shape = rounded(12)
theme.tooltip_bg = c.surface
theme.tooltip_fg = c.fg
theme.tooltip_border_color = line
theme.tooltip_border_width = dpi(1)
theme.tooltip_shape = rounded(10)
theme.notification_bg = c.surface
theme.notification_fg = c.fg
theme.notification_border_color = line
theme.notification_border_width = dpi(1)
theme.notification_shape = rounded(14)
theme.notification_margin = dpi(14)
theme.menu_bg_normal = c.surface
theme.menu_fg_normal = c.fg
theme.menu_bg_focus = raised
theme.menu_fg_focus = c.fg
theme.menu_border_color = line
theme.menu_border_width = dpi(1)
theme.menu_height = dpi(30)
theme.menu_width = dpi(220)
theme.awesome_icon = icons.get("launcher", c.accent, dpi(16))

-- The selected workspace has an icy underline; the rest are plain digits.
theme.taglist_font = theme.widget_font
theme.taglist_shape = gears.shape.rectangle
theme.taglist_bg_empty = transparent
theme.taglist_bg_occupied = transparent
theme.taglist_bg_focus = transparent
theme.taglist_bg_urgent = transparent
theme.taglist_fg_empty = theme.muted
theme.taglist_fg_occupied = c.fg
theme.taglist_fg_focus = c.accent
theme.taglist_fg_urgent = c.red or c.accent
theme.taglist_disable_icon = true
theme.taglist_squares_sel = nil
theme.taglist_squares_unsel = nil
theme.tasklist_font = theme.font
theme.tasklist_plain_task_name = true
theme.tasklist_disable_icon = true
theme.tasklist_bg_normal = transparent
theme.tasklist_bg_focus = transparent
theme.systray_icon_spacing = dpi(8)
theme.bg_systray = c.bg

local layout_icons = gfs.get_themes_dir() .. "default/layouts/"
for _, name in ipairs({ "tile", "tileleft", "tilebottom", "tiletop", "fairv", "fairh", "spiral",
    "dwindle", "max", "fullscreen", "magnifier", "floating" }) do
    theme["layout_" .. name] = gears.color.recolor_image(layout_icons .. name .. ".png", c.accent)
end

naughty.config.padding = dpi(14)
naughty.config.spacing = dpi(8)
naughty.config.defaults.position = "top_right"
naughty.config.defaults.margin = theme.notification_margin

function theme.wallpaper_for(s)
    return wallpaper(c, s)
end

function theme.client_shape(cl)
    cl.shape = (cl.fullscreen or cl.maximized or cl.maximized_horizontal or cl.maximized_vertical)
        and gears.shape.rectangle or rounded(12)
end

-- Keep explicit titlebar requests from falling back to rc.lua's generic builder.
function theme.titlebar_fun(_) end

local function text(value, color, font)
    return wibox.widget({
        markup = color and ("<span foreground='" .. color .. "'>" .. value .. "</span>") or value,
        font = font or theme.font, widget = wibox.widget.textbox,
    })
end

local function rate(value)
    value = math.max(0, tonumber(value) or 0)
    return value >= 1024 and string.format("%.1f MiB/s", value / 1024) or string.format("%.0f KiB/s", value)
end

-- The focused client as "class  title", with the title dimmed.
local function task_update(widget, cl)
    local label = widget:get_children_by_id("label_role")[1]
    local class = gears.string.xml_escape((cl.class or ""):lower())
    local name = gears.string.xml_escape(cl.name or "")
    if class == "" then class, name = name, "" end
    if name:lower() == class then name = "" end
    label.markup = name == "" and class
        or class .. "  <span foreground='" .. theme.muted .. "'>" .. name .. "</span>"
end

-- The layout chip names the selected workspace's layout ("tile", "max", ...).
local function sync_layout_chip(t)
    local s = t.screen
    if s and s.layout_name then
        s.layout_name.text = awful.layout.getname(awful.layout.get(s)) or ""
    end
end
tag.connect_signal("property::layout", sync_layout_chip)
tag.connect_signal("property::selected", sync_layout_chip)

local function tile(title, ...)
    return wibox.container.background(wibox.widget({
        {
            text(title, theme.muted, "Inter, sans 9"),
            spacing = dpi(4), layout = wibox.layout.fixed.vertical, ...
        },
        top = dpi(12), bottom = dpi(12), left = dpi(14), right = dpi(14),
        widget = wibox.container.margin,
    }), c.bg, rounded(12))
end

local function panel_button(label, action)
    local button = wibox.container.background(
        wibox.container.margin(text(label), dpi(14), dpi(14), dpi(7), dpi(7)), transparent, rounded(10)
    )
    button.shape_border_width, button.shape_border_color = dpi(1), line
    button:buttons(gears.table.join(awful.button({}, 1, action)))
    button:connect_signal("mouse::enter", function() button.bg = raised end)
    button:connect_signal("mouse::leave", function() button.bg = transparent end)
    return button
end

-- Details that do not earn a place in the bar, read from the same pollers.
local function build_panel(s, on_toggle)
    local network = text("—")
    local traffic = text("—", theme.muted, theme.widget_font)
    local level = text("—", nil, theme.widget_font)
    local volume = wibox.widget({
        max_value = 100, value = 0, forced_height = dpi(4), color = c.accent, background_color = line,
        shape = gears.shape.rounded_bar, bar_shape = gears.shape.rounded_bar,
        widget = wibox.widget.progressbar,
    })
    local system = text("—")
    local disk = text("—")
    local battery = text("", theme.muted, theme.widget_font)

    local content = wibox.widget({
        {
            tile("Network", network, traffic),
            tile("Volume", {
                nil, wibox.container.place(volume, "center", "center"), wibox.container.margin(level, dpi(12)),
                layout = wibox.layout.align.horizontal,
            }),
            tile("System", system),
            tile("Disk", disk),
            forced_num_cols = 2, homogeneous = true, expand = true, spacing = dpi(8),
            layout = wibox.layout.grid,
        },
        {
            wibox.container.place(battery, "left", "center"), nil,
            {
                panel_button("Lock", function() awful.spawn("slock") end),
                panel_button("Session", function() logout.launch({ screen = s }) end),
                spacing = dpi(8), layout = wibox.layout.fixed.horizontal,
            },
            layout = wibox.layout.align.horizontal,
        },
        forced_width = dpi(348), spacing = dpi(14), layout = wibox.layout.fixed.vertical,
    })
    local panel = awful.popup({
        screen = s, ontop = true, visible = false, bg = c.surface, fg = c.fg,
        border_color = line, border_width = dpi(1), shape = rounded(16),
        minimum_width = dpi(380), maximum_width = dpi(380),
        widget = wibox.container.margin(content, dpi(16), dpi(16), dpi(16), dpi(16)),
        -- Re-applied whenever the popup resizes: just under the bar, flush with
        -- the status group's right edge.
        placement = function(popup)
            local area = s.workarea
            popup.x = area.x + area.width - popup.width - dpi(16)
            popup.y = area.y + dpi(6)
        end,
    })

    local function refresh()
        -- lain's pollers publish their latest readings as globals.
        local net, connected = net_now or {}, false
        for _, device in pairs(net.devices or {}) do
            if device.carrier == "1" then connected = true end
        end
        network.text = connected and "Connected" or "Offline"
        -- Two lines: a tile is too narrow for both rates side by side.
        traffic.markup = "<span foreground='" .. theme.muted .. "'>down " .. rate(net.received)
            .. "\nup " .. rate(net.sent) .. "</span>"
        local cpu = cpu_now and cpu_now.usage
        local memory = mem_now and tonumber(mem_now.used)
        system.text = (cpu and ("CPU " .. cpu .. "%") or "CPU —")
            .. (memory and string.format(" · %.1f GiB", memory / 1024) or "")
        local root_fs = fs_now and fs_now["/"]
        disk.text = root_fs and string.format("%.1f %s free", root_fs.free, root_fs.units) or "—"
        local percent = bat_now and tonumber(bat_now.perc)
        battery.visible = percent ~= nil and bat_now.status ~= "N/A"
        if battery.visible then
            battery.markup = string.format("<span foreground='%s'>Battery %d%% · %s</span>",
                theme.muted, percent, gears.string.xml_escape(bat_now.status or ""))
        end
        awful.spawn.easy_async({ "wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@" }, function(stdout, _, _, code)
            local value = code == 0 and tonumber(stdout:match("Volume:%s*([%d%.]+)"))
            volume.value = value and value * 100 or 0
            level.text = not value and "—" or stdout:find("[MUTED]", 1, true) and "off"
                or string.format("%.0f%%", value * 100)
        end)
    end
    local timer = gears.timer({ timeout = 2, callback = refresh })

    local function set_visible(visible)
        if visible then
            refresh()
            timer:again()
        else
            timer:stop()
        end
        panel.visible = visible
        on_toggle(visible)
    end
    panel:connect_signal("mouse::leave", function() set_visible(false) end)
    return function() set_visible(not panel.visible) end
end

-- Live readings from the shared pollers, rather than illustrative bars.
local function build_monitor(s)
    local graph_width = dpi(260)
    local label = text("CPU —", c.fg, theme.widget_font)
    local cpu_graph = wibox.widget({
        width = graph_width, forced_width = graph_width, forced_height = dpi(32), max_value = 100,
        background_color = transparent, color = c.accent,
        step_width = dpi(5), step_spacing = dpi(3), widget = wibox.widget.graph,
    })
    local cpu_header = wibox.layout.align.horizontal(
        text("SYSTEM / AT EASE", theme.muted, "JetBrains Mono 8"), nil, label)

    local ram_label = text("—", c.fg, theme.widget_font)
    ram_label.align = "right"
    local ram_graph = wibox.widget({
        width = graph_width, forced_width = graph_width, forced_height = dpi(32), max_value = 100,
        background_color = transparent, color = c.accent,
        step_width = dpi(5), step_spacing = dpi(3), widget = wibox.widget.graph,
    })
    local ram_header = wibox.layout.align.horizontal(
        text("MEMORY", theme.muted, "JetBrains Mono 8"), nil,
        wibox.container.constraint(ram_label, "max", dpi(190))
    )

    local down_color = c.seg and c.seg.net and c.seg.net.icon or c.accent
    local up_color = c.seg and c.seg.fs and c.seg.fs.icon or c.fg
    local download = text("DL —", down_color, "JetBrains Mono 8")
    local upload = text("UL —", up_color, "JetBrains Mono 8")
    local network_rates = wibox.widget({
        download, upload, spacing = dpi(8), layout = wibox.layout.fixed.horizontal,
    })
    local network_graph = wibox.widget({
        width = graph_width, forced_width = graph_width, forced_height = dpi(32), max_value = 1, scale = true, stack = true,
        background_color = transparent, stack_colors = { down_color, up_color },
        step_width = dpi(5), step_spacing = dpi(3), widget = wibox.widget.graph,
    })
    local network_header = wibox.layout.align.horizontal(
        text("NETWORK", theme.muted, "JetBrains Mono 8"), nil,
        wibox.container.constraint(network_rates, "max", dpi(190))
    )

    local function card(header, graph)
        return awful.popup({
            screen = s, type = "desktop", ontop = false, visible = true,
            bg = c.surface, fg = c.fg, border_color = line, border_width = dpi(1), shape = rounded(12),
            minimum_width = dpi(292), maximum_width = dpi(292),
            widget = {
                { header, graph, spacing = dpi(12), layout = wibox.layout.fixed.vertical },
                margins = dpi(16), widget = wibox.container.margin,
            },
        })
    end

    s.tide_monitor = card(cpu_header, cpu_graph)
    s.tide_ram_monitor = card(ram_header, ram_graph)
    s.tide_network_monitor = card(network_header, network_graph)
    s.tide_monitors = { s.tide_monitor, s.tide_ram_monitor, s.tide_network_monitor }

    local function position()
        local g = s.workarea
        local gap = dpi(12)
        local total_height = gap * (#s.tide_monitors - 1)
        local maximum_width = 0
        for _, monitor in ipairs(s.tide_monitors) do
            total_height = total_height + monitor.height
            maximum_width = math.max(maximum_width, monitor.width)
        end
        local right = math.min(dpi(48), math.max(0, g.width - maximum_width))
        local bottom = math.min(dpi(120), math.max(0, g.height - total_height))
        local y = g.y + g.height - bottom - total_height
        for _, monitor in ipairs(s.tide_monitors) do
            monitor.x = g.x + g.width - monitor.width - right
            monitor.y = y
            y = y + monitor.height + gap
        end
    end
    for _, monitor in ipairs(s.tide_monitors) do
        monitor:connect_signal("property::width", position)
        monitor:connect_signal("property::height", position)
    end
    s:connect_signal("property::workarea", position)
    position()

    local seen_interfaces, previous_network_snapshot, traffic_totals = {}, nil, {}
    local function numeric(value)
        local number = tonumber(value)
        if number and number == number and number > -math.huge and number < math.huge then return number end
    end
    -- lain reports KiB/s; prime each interface once so startup byte totals are not graphed.
    local function refresh_network()
        local net = type(net_now) == "table" and net_now or nil
        if not net then
            seen_interfaces, previous_network_snapshot = {}, nil
            download.text, upload.text = "DL —", "UL —"
            return
        end
        if net == previous_network_snapshot then return end
        previous_network_snapshot = net

        local devices = type(net.devices) == "table" and net.devices or {}
        local present, received, sent, primed = {}, 0, 0, false
        for name, device in pairs(devices) do
            if type(device) == "table" then
                present[name] = true
                local down, up = numeric(device.received), numeric(device.sent)
                if down ~= nil or up ~= nil then
                    down, up = math.max(0, down or 0), math.max(0, up or 0)
                    if seen_interfaces[name] then
                        received, sent, primed = received + down, sent + up, true
                    else
                        seen_interfaces[name] = true
                    end
                end
            end
        end
        for name in pairs(seen_interfaces) do
            if not present[name] then seen_interfaces[name] = nil end
        end

        if not primed then
            download.text, upload.text = "DL —", "UL —"
            return
        end
        download.text, upload.text = "DL " .. rate(received), "UL " .. rate(sent)
        table.insert(traffic_totals, received + sent)
        while #traffic_totals > graph_width do table.remove(traffic_totals, 1) end
        local maximum = 1
        for _, total in ipairs(traffic_totals) do maximum = math.max(maximum, total) end
        -- Stacked graphs scale groups independently, so use the largest combined column.
        network_graph.max_value = maximum
        network_graph:add_value(received, 1)
        network_graph:add_value(sent, 2)
    end

    s.tide_monitor_timer = gears.timer({ timeout = 2, autostart = true, call_now = true, callback = function()
        local usage = type(cpu_now) == "table" and numeric(cpu_now.usage)
        label.text = usage and string.format("%.0f%% cpu", usage) or "CPU —"
        if usage then cpu_graph:add_value(usage) end

        local memory = type(mem_now) == "table" and mem_now or nil
        local percent = memory and numeric(memory.perc)
        local used = memory and numeric(memory.used)
        local total = memory and numeric(memory.total)
        if percent and used and total and total > 0 then
            percent = math.min(100, math.max(0, percent))
            ram_label.text = string.format("%.0f%% · %.1f/%.1f GiB", percent, used / 1024, total / 1024)
            ram_graph:add_value(percent)
        else
            ram_label.text = "—"
        end

        refresh_network()
    end })
    s:connect_signal("removed", function() s.tide_monitor_timer:stop() end)
end

function theme.at_screen_connect(s)
    s.quake = lain.util.quake({ app = awful.util.terminal })
    gears.wallpaper.maximized(theme.wallpaper_for(s), s, false)
    awful.tag(awful.util.tagnames, s, awful.layout.suit.floating)
    for _, t in ipairs(s.tags) do
        t.master_width_factor = 0.5
        t.gap_single_client = true
    end
    s.mypromptbox = awful.widget.prompt()

    s.mytaglist = awful.widget.taglist({
        screen = s, filter = awful.widget.taglist.filter.all, buttons = awful.util.taglist_buttons,
        layout = { layout = wibox.layout.fixed.horizontal },
        widget_template = {
            {
                [2] = { id = "text_role", align = "center", valign = "center", widget = wibox.widget.textbox },
                [3] = { id = "underline", forced_height = dpi(2), bg = transparent,
                    widget = wibox.container.background },
                layout = wibox.layout.align.vertical,
            },
            id = "background_role", forced_width = dpi(30), widget = wibox.container.background,
            create_callback = function(widget, t)
                widget:get_children_by_id("underline")[1].bg = t.selected and c.accent or transparent
            end,
            update_callback = function(widget, t)
                widget:get_children_by_id("underline")[1].bg = t.selected and c.accent or transparent
            end,
        },
    })
    s.mytasklist = awful.widget.tasklist({
        screen = s, filter = awful.widget.tasklist.filter.focused, buttons = awful.util.tasklist_buttons,
        widget_template = {
            { id = "label_role", ellipsize = "end", font = theme.font, widget = wibox.widget.textbox },
            widget = wibox.container.place, halign = "left",
            create_callback = task_update, update_callback = task_update,
        },
    })
    local task = wibox.container.constraint(s.mytasklist, "max", dpi(300))
    shared_widgets = shared_widgets or build_widgets({ colors = c, theme = theme })
    local widgets = shared_widgets
    -- The status dot opens the drop-down below instead of a notification.
    widgets.system:buttons({})
    s.fs = widgets.fs

    local clock = wibox.widget.textclock(
        "<span foreground='" .. theme.muted .. "'>%a %d %b</span>   %H:%M", 30
    )
    clock.font = theme.font
    s.cal = lain.widget.cal({
        attach_to = { clock }, followtag = true,
        notification_preset = { font = theme.widget_font, fg = c.fg, bg = c.surface },
    })

    s.layout_name = wibox.widget({ font = theme.widget_font, align = "center", widget = wibox.widget.textbox })
    sync_layout_chip(s.selected_tag or s.tags[1])
    local layout_chip = wibox.container.background(
        wibox.container.margin(s.layout_name, dpi(8), dpi(8), dpi(3), dpi(3)), raised, rounded(6)
    )
    layout_chip.fg = c.accent
    layout_chip:buttons(gears.table.join(
        awful.button({}, 1, function() awful.layout.inc(1, s) end),
        awful.button({}, 3, function() awful.layout.inc(-1, s) end),
        awful.button({}, 4, function() awful.layout.inc(1, s) end),
        awful.button({}, 5, function() awful.layout.inc(-1, s) end)
    ))
    awful.tooltip({ objects = { layout_chip }, text = "Layout · click or scroll to change" })

    local divider = wibox.container.margin(wibox.widget({
        forced_width = dpi(1), color = line, widget = wibox.widget.separator,
    }), dpi(4), dpi(4), dpi(8), dpi(8))
    local left = {
        s.mytaglist, divider, task, s.mypromptbox,
        spacing = dpi(10), layout = wibox.layout.fixed.horizontal,
    }
    local right = { spacing = dpi(16), layout = wibox.layout.fixed.horizontal }
    -- The primary-screen systray follows hotplugging without duplicate icons.
    local tray = wibox.widget.systray()
    tray:set_base_size(dpi(14))
    tray:set_screen("primary")
    -- Fixed margins, not place: the tray must never be drawn 0 px tall.
    table.insert(right, wibox.container.margin(tray, 0, 0, dpi(7), dpi(7)))
    local plugin_containers = {}
    local function plugin_container(widget)
        local container = wibox.container.place(widget, "center", "center")
        for _, child in ipairs(container:get_all_children()) do
            if child.set_font then child.font = theme.widget_font end
        end
        plugin_containers[#plugin_containers + 1] = container
        return container
    end
    local plugin_colors = gears.table.clone(c, true)
    for _, segment in pairs(plugin_colors.seg or {}) do
        segment.bg, segment.fg, segment.icon = transparent, theme.muted, theme.muted
    end
    require("plugins")(left, right, plugin_container, plugin_colors, s)
    local network = wibox.container.place(widgets.network, "center", "center")
    table.insert(right, network)
    table.insert(right, widgets.volume)
    table.insert(right, widgets.battery)
    table.insert(right, wibox.container.place(layout_chip, "center", "center"))
    local trigger = wibox.container.background(widgets.system, transparent, rounded(6))
    trigger.forced_width = dpi(20)
    table.insert(right, trigger)

    local right_layout = wibox.widget(right)
    -- Everything right of the clock reads as one group; it lights up while
    -- its drop-down is open.
    local status = wibox.container.background(
        wibox.container.margin(right_layout, dpi(12), dpi(8)), transparent, rounded(10)
    )
    status.forced_height = dpi(30)
    local toggle_panel = build_panel(s, function(open) status.bg = open and raised or transparent end)
    trigger:buttons(gears.table.join(awful.button({}, 1, toggle_panel)))
    awful.tooltip({ objects = { trigger }, text = "System status" })

    local launcher = wibox.container.background(
        wibox.container.place(wibox.widget({
            image = icons.get("launcher", theme.muted, dpi(14)),
            forced_width = dpi(14), forced_height = dpi(14), widget = wibox.widget.imagebox,
        }), "center", "center"), transparent, rounded(8)
    )
    launcher.forced_width = dpi(32)
    launcher:buttons(gears.table.join(
        awful.button({}, 1, function()
            awful.screen.focus(s)
            run_shell.launch()
        end),
        awful.button({}, 3, function() awful.util.mymainmenu:toggle() end)
    ))
    awful.tooltip({ objects = { launcher }, text = "App launcher · right-click for Awesome menu" })
    table.insert(left, 1, launcher)

    local left_layout = wibox.widget(left)
    -- "outside" keeps the clock centered on the screen whatever the sides hold.
    local row = wibox.layout.align.horizontal(left_layout, clock, wibox.container.place(status, "right", "center"))
    row.expand = "outside"
    s.mywibox = awful.wibar({ screen = s, position = "top", height = dpi(32), bg = c.surface, fg = c.fg })
    s.mywibox:setup({
        [2] = { row, left = dpi(16), right = dpi(16), widget = wibox.container.margin },
        [3] = { forced_height = dpi(1), color = line, widget = wibox.widget.separator },
        layout = wibox.layout.align.vertical,
    })
    build_monitor(s)
    -- Desktop furniture yields to fullscreen clients on its own screen.
    local function furniture_visibility()
        local visible = true
        for _, cl in ipairs(s.clients) do
            if cl.fullscreen and cl:isvisible() then visible = false; break end
        end
        for _, monitor in ipairs(s.tide_monitors or {}) do monitor.visible = visible end
    end
    s:connect_signal("arrange", furniture_visibility)
    furniture_visibility()

    local function resize()
        local width = s.geometry.width
        task.visible = width >= dpi(1500)
        clock.format = width >= dpi(1100)
            and "<span foreground='" .. theme.muted .. "'>%a %d %b</span>   %H:%M" or "%H:%M"
        network.visible = width >= dpi(850)
        for _, container in ipairs(plugin_containers) do container.visible = width >= dpi(1000) end
    end
    s:connect_signal("property::geometry", resize)
    resize()
end

return theme

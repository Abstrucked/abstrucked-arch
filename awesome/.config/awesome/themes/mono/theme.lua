-- Mono: three floating panel islands, palette-driven surfaces and quiet tiling.
local awful = require("awful")
local gears = require("gears")
local gfs = require("gears.filesystem")
local lain = require("lain")
local naughty = require("naughty")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local c = require("themes.colors")
local style = require("themes.mono.style")
local icons = require("themes.mono.icons")
local wallpaper = require("themes.mono.wallpaper")
local build_widgets = require("themes.mono.widgets")
local run_shell = require("awesome-wm-widgets.run-shell-3.run-shell")
local logout = require("awesome-wm-widgets.logout-widget.logout")
local theme = {}
local transparent = "#00000000"
local line = style.mix(c.bg, c.fg, 0.14)
local raised = style.mix(c.surface, c.fg, 0.06)
local on_accent = style.on(c.accent, c)
local shared_widgets

theme.name = "mono"
theme.font = "Inter 10"
theme.widget_font = "JetBrains Mono Nerd Font 9"
theme.muted = style.mix(c.surface, c.fg, 0.64)
theme.fg_normal = c.fg
theme.bg_normal = c.bg
theme.fg_focus = c.fg
theme.bg_focus = c.surface
theme.fg_urgent = style.on(c.red or c.accent, c)
theme.bg_urgent = c.red or c.accent
theme.useless_gap = dpi(14)
theme.gap_single_client = true
theme.border_width = dpi(1)
theme.border_normal = line
theme.border_focus = c.accent
theme.border_marked = c.accent
theme.keep_single_client_border = true
theme.titlebars_enabled = true
theme.titlebar_bg_normal = c.surface
theme.titlebar_bg_focus = c.surface
theme.titlebar_fg_normal = theme.muted
theme.titlebar_fg_focus = c.fg
theme.icon_theme = "Numix"

local function rounded(cr, width, height) gears.shape.rounded_rect(cr, width, height, dpi(8)) end
local function tag_shape(cr, width, height) gears.shape.rounded_rect(cr, width, height, dpi(4)) end

theme.popup_bg = c.surface
theme.popup_fg = c.fg
theme.popup_shape = rounded
theme.tooltip_bg = c.surface
theme.tooltip_fg = c.fg
-- Box-drawn tooltips (ai-usagebar's) only line up in a monospace face, and
-- theme.font is a proportional sans here. Give every Mono tooltip the widget
-- font so panels built from ASCII art do not ragged their right edge.
theme.tooltip_font = theme.widget_font
theme.tooltip_border_color = line
theme.tooltip_border_width = dpi(1)
theme.tooltip_shape = rounded
theme.notification_bg = c.surface
theme.notification_fg = c.fg
theme.notification_border_color = line
theme.notification_border_width = dpi(1)
theme.notification_shape = rounded
theme.notification_margin = dpi(14)
theme.menu_bg_normal = c.surface
theme.menu_fg_normal = c.fg
theme.menu_bg_focus = c.accent
theme.menu_fg_focus = on_accent
theme.menu_border_color = line
theme.menu_border_width = dpi(1)
theme.menu_height = dpi(28)
theme.menu_width = dpi(210)
theme.awesome_icon = icons.get("launcher", c.accent, dpi(20))

theme.taglist_font = theme.widget_font
theme.taglist_bg_empty = transparent
theme.taglist_bg_occupied = transparent
theme.taglist_bg_focus = c.accent
theme.taglist_bg_urgent = c.red or c.accent
theme.taglist_fg_empty = theme.muted
theme.taglist_fg_occupied = c.fg
theme.taglist_fg_focus = on_accent
theme.taglist_fg_urgent = theme.fg_urgent
theme.taglist_shape = tag_shape
theme.taglist_disable_icon = true
theme.taglist_squares_sel = nil
theme.taglist_squares_unsel = nil
theme.tasklist_font = theme.widget_font
theme.tasklist_plain_task_name = true
theme.tasklist_disable_icon = true
theme.tasklist_bg_normal = transparent
theme.tasklist_bg_focus = transparent
theme.tasklist_fg_normal = theme.muted
theme.tasklist_fg_focus = c.fg
theme.systray_icon_spacing = dpi(8)
theme.bg_systray = c.surface

local layout_icons = gfs.get_themes_dir() .. "default/layouts/"
for _, name in ipairs({ "tile", "tileleft", "tilebottom", "tiletop", "fairv", "fairh", "spiral",
    "dwindle", "max", "fullscreen", "magnifier", "floating" }) do
    theme["layout_" .. name] = gears.color.recolor_image(layout_icons .. name .. ".png", c.accent)
end

naughty.config.padding = dpi(16)
naughty.config.spacing = dpi(8)
naughty.config.defaults.position = "top_right"
naughty.config.defaults.margin = theme.notification_margin

function theme.wallpaper_for(s)
    return wallpaper(c, s)
end

function theme.client_shape(cl)
    if cl.fullscreen or cl.maximized or cl.maximized_horizontal or cl.maximized_vertical then
        cl.shape = gears.shape.rectangle
    else
        cl.shape = rounded
    end
end

local function title_button(label, action, hover)
    local text = wibox.widget({ text = label, align = "center", font = "sans 12", widget = wibox.widget.textbox })
    local button = wibox.container.background(text, transparent, tag_shape)
    button.forced_width = dpi(26)
    button:buttons(gears.table.join(awful.button({}, 1, action)))
    button:connect_signal("mouse::enter", function() button.bg = hover or raised end)
    button:connect_signal("mouse::leave", function() button.bg = transparent end)
    return button
end

function theme.titlebar_fun(cl)
    local drag = gears.table.join(
        awful.button({}, 1, function()
            cl:emit_signal("request::activate", "titlebar", { raise = true })
            awful.mouse.client.move(cl)
        end),
        awful.button({}, 3, function()
            cl:emit_signal("request::activate", "titlebar", { raise = true })
            awful.mouse.client.resize(cl)
        end)
    )
    local title = awful.titlebar.widget.titlewidget(cl)
    title.font = theme.widget_font
    title.align = "left"
    title.ellipsize = "end"
    title:buttons(drag)
    awful.titlebar(cl, { size = dpi(30) }):setup({
        {
            {
                title,
                nil,
                {
                    title_button("−", function() cl.minimized = true end),
                    title_button("×", function() cl:kill() end, style.mix(c.surface, c.red or c.accent, 0.25)),
                    layout = wibox.layout.fixed.horizontal,
                },
                layout = wibox.layout.align.horizontal,
            },
            left = dpi(12), right = dpi(5), top = dpi(3), bottom = dpi(3),
            widget = wibox.container.margin,
        },
        bg = c.surface, widget = wibox.container.background,
    })
end

local function separator()
    return wibox.container.margin(wibox.widget({
        forced_width = dpi(1), color = line, widget = wibox.widget.separator,
    }), dpi(4), dpi(4), dpi(10), dpi(10))
end

local function island(content)
    local panel = wibox.container.background(wibox.container.margin(content, dpi(12), dpi(12)), c.surface, rounded)
    panel.forced_height = dpi(36)
    panel.shape_border_width = dpi(1)
    panel.shape_border_color = line
    return panel
end

local function icon_button(name, tooltip, action, alternate)
    local image = wibox.widget({
        image = icons.get(name, c.accent, dpi(16)),
        forced_width = dpi(16), forced_height = dpi(16), widget = wibox.widget.imagebox,
    })
    local button = wibox.container.place(image, "center", "center")
    button.forced_width = dpi(22)
    button:buttons(gears.table.join(
        awful.button({}, 1, action), awful.button({}, 3, alternate or action)
    ))
    awful.tooltip({ objects = { button }, text = tooltip })
    return button
end

-- Plugin snippets keep their existing API; their containers and icons take
-- Mono's neutral surfaces instead of Powerarrow's colored arrow segments.
local plugin_colors = gears.table.clone(c, true)
for _, segment in pairs(plugin_colors.seg or {}) do
    segment.bg, segment.fg, segment.icon = c.surface, c.fg, c.accent
end
local function plugin_container(widget)
    local container = wibox.container.margin(widget, dpi(4), dpi(4), dpi(6), dpi(6))
    for _, child in ipairs(container:get_all_children()) do
        if child.set_font then child.font = theme.widget_font end
    end
    return container
end

function theme.at_screen_connect(s)
    s.quake = lain.util.quake({ app = awful.util.terminal })
    gears.wallpaper.maximized(theme.wallpaper_for(s), s, false)
    awful.tag(awful.util.tagnames, s, awful.layout.suit.tile)
    for _, tag in ipairs(s.tags) do
        tag.master_width_factor = 0.62
        tag.gap_single_client = true
    end
    s.tags[2].layout = awful.layout.suit.max
    s.tags[3].layout = awful.layout.suit.max
    s.mypromptbox = awful.widget.prompt()

    s.mytaglist = awful.widget.taglist({
        screen = s,
        filter = awful.widget.taglist.filter.all,
        buttons = awful.util.taglist_buttons,
        layout = { spacing = dpi(4), layout = wibox.layout.fixed.horizontal },
        widget_template = {
            {
                {
                    { id = "text_role", align = "center", widget = wibox.widget.textbox },
                    left = dpi(7), right = dpi(7), widget = wibox.container.margin,
                },
                id = "background_role", shape = tag_shape, widget = wibox.container.background,
            },
            top = dpi(6), bottom = dpi(6), widget = wibox.container.margin,
        },
    })
    s.mytasklist = awful.widget.tasklist({
        screen = s, filter = awful.widget.tasklist.filter.focused,
        buttons = awful.util.tasklist_buttons,
        widget_template = {
            { id = "text_role", ellipsize = "end", widget = wibox.widget.textbox },
            id = "background_role", widget = wibox.container.background,
        },
    })
    local task = wibox.container.constraint(s.mytasklist, "exact", dpi(130))

    local clock = wibox.widget.textclock("%a, %d %b   <b>%H:%M</b>", 30)
    clock.font = theme.widget_font
    s.cal = lain.widget.cal({
        attach_to = { clock }, followtag = true,
        notification_preset = { font = theme.widget_font, fg = c.fg, bg = c.surface },
    })
    shared_widgets = shared_widgets or build_widgets({ colors = c, theme = theme })
    local widgets = shared_widgets
    s.fs = widgets.fs

    s.mylayoutbox = awful.widget.layoutbox(s)
    s.mylayoutbox:buttons(gears.table.join(
        awful.button({}, 1, function() awful.layout.inc(1, s) end),
        awful.button({}, 3, function() awful.layout.inc(-1, s) end),
        awful.button({}, 4, function() awful.layout.inc(1, s) end),
        awful.button({}, 5, function() awful.layout.inc(-1, s) end)
    ))
    local layoutbox = wibox.container.constraint(wibox.container.margin(s.mylayoutbox, 0, 0, dpi(10), dpi(10)), "exact", dpi(16))
    local left = {
        icon_button("launcher", "App launcher · right-click for Awesome menu", function()
            awful.screen.focus(s)
            run_shell.launch()
        end, function() awful.util.mymainmenu:toggle() end),
        separator(), s.mytaglist, task, s.mypromptbox,
        spacing = dpi(6), layout = wibox.layout.fixed.horizontal,
    }
    local right = { spacing = dpi(12), layout = wibox.layout.fixed.horizontal }
    -- Systray is a singleton. The primary-screen placeholder follows changes
    -- through wibox.widget.systray's own screen handling.
    local tray = wibox.widget.systray()
    tray:set_base_size(dpi(16))
    tray:set_screen("primary")
    -- Keep a positive height even with no tray entries (Awesome 4.3's tray
    -- draw function rejects a zero icon size inside a shrink-wrapped place).
    table.insert(right, wibox.container.margin(tray, 0, 0, dpi(10), dpi(10)))

    require("plugins")(left, right, plugin_container, plugin_colors, s)
    table.insert(right, widgets.system)
    table.insert(right, widgets.network)
    table.insert(right, widgets.volume)
    table.insert(right, widgets.battery)
    table.insert(right, layoutbox)
    table.insert(right, icon_button("power", "Session controls", function() logout.launch({ screen = s }) end))

    local left_island = wibox.container.place(island(wibox.widget(left)), "left", "center")
    local center_island = wibox.container.place(island(clock), "center", "center")
    local right_island = wibox.container.place(island(wibox.widget(right)), "right", "center")
    local row = wibox.layout.align.horizontal(left_island, center_island, right_island)
    row.expand = "none"

    -- One transparent wibar reserves space for the islands and makes Super+B
    -- hide the entire panel. Clients can never tile underneath the floating UI.
    s.mywibox = awful.wibar({
        screen = s, position = "top", height = dpi(52), bg = transparent, fg = c.fg,
    })
    s.mywibox:setup({
        row, left = dpi(16), right = dpi(16), top = dpi(12), bottom = dpi(4),
        widget = wibox.container.margin,
    })

    local function resize()
        task.visible = s.geometry.width >= dpi(1500)
        clock.format = s.geometry.width >= dpi(1200) and "%a, %d %b   <b>%H:%M</b>" or "<b>%H:%M</b>"
        -- Tiny/portrait outputs keep the clock accessible via the calendar key.
        center_island.visible = s.geometry.width >= dpi(1000)
    end
    s:connect_signal("property::geometry", resize)
    resize()
end

return theme

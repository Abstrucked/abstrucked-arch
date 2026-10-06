-- Slate: one slim rail, understated workspace markers and uncluttered tiling.
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
local wallpaper = require("themes.slate.wallpaper")
local run_shell = require("awesome-wm-widgets.run-shell-3.run-shell")
local logout = require("awesome-wm-widgets.logout-widget.logout")
local screen = screen
local theme = {}
local transparent = "#00000000"
local line = style.mix(c.surface, c.fg, 0.11)
local hover_bg = style.mix(c.surface, c.fg, 0.06)
local shared_widgets
local titlebars = setmetatable({}, { __mode = "k" })

theme.name = "slate"
theme.system_title = "System / Slate"
theme.font = "Inter 10"
theme.widget_font = "Inter 9"
theme.muted = c.muted or style.mix(c.surface, c.fg, 0.6)
theme.fg_normal = c.fg
theme.bg_normal = c.bg
theme.fg_focus = c.fg
theme.bg_focus = c.surface
theme.fg_urgent = style.on(c.red or c.accent, c)
theme.bg_urgent = c.red or c.accent
theme.useless_gap = dpi(12)
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

local function rounded(cr, width, height) gears.shape.rounded_rect(cr, width, height, dpi(6)) end

theme.popup_bg = c.surface
theme.popup_fg = c.fg
theme.popup_shape = rounded
theme.tooltip_bg = c.surface
theme.tooltip_fg = c.fg
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
theme.menu_bg_focus = hover_bg
theme.menu_fg_focus = c.fg
theme.menu_border_color = line
theme.menu_border_width = dpi(1)
theme.menu_height = dpi(28)
theme.menu_width = dpi(220)
theme.awesome_icon = icons.get("launcher", c.accent, dpi(16))

theme.taglist_font = theme.widget_font
theme.taglist_bg_empty = transparent
theme.taglist_bg_occupied = transparent
theme.taglist_bg_focus = transparent
theme.taglist_bg_urgent = transparent
theme.taglist_fg_empty = theme.muted
theme.taglist_fg_occupied = c.fg
theme.taglist_fg_focus = c.fg
theme.taglist_fg_urgent = c.red or c.accent
theme.taglist_disable_icon = true
theme.taglist_squares_sel = nil
theme.taglist_squares_unsel = nil
theme.tasklist_font = theme.widget_font
theme.tasklist_plain_task_name = true
theme.tasklist_disable_icon = true
theme.tasklist_bg_normal = transparent
theme.tasklist_bg_focus = transparent
theme.tasklist_fg_normal = theme.muted
theme.tasklist_fg_focus = theme.muted
theme.systray_icon_spacing = dpi(8)
theme.bg_systray = c.surface

local layout_icons = gfs.get_themes_dir() .. "default/layouts/"
for _, name in ipairs({ "tile", "tileleft", "tilebottom", "tiletop", "fairv", "fairh", "spiral",
    "dwindle", "max", "fullscreen", "magnifier", "floating" }) do
    theme["layout_" .. name] = gears.color.recolor_image(layout_icons .. name .. ".png", theme.muted)
end

naughty.config.padding = dpi(12)
naughty.config.spacing = dpi(8)
naughty.config.defaults.position = "top_right"
naughty.config.defaults.margin = theme.notification_margin

function theme.wallpaper_for(s)
    return wallpaper(c, s)
end

function theme.client_shape(cl)
    cl.shape = (cl.fullscreen or cl.maximized or cl.maximized_horizontal or cl.maximized_vertical)
        and gears.shape.rectangle or rounded
end

local function title_button(label, action, danger)
    local text = wibox.widget({ text = label, align = "center", font = "sans 11", widget = wibox.widget.textbox })
    local button = wibox.container.background(text, transparent, rounded)
    button.forced_width = dpi(26)
    button:buttons(gears.table.join(awful.button({}, 1, action)))
    button:connect_signal("mouse::enter", function()
        button.bg = danger and style.mix(c.surface, c.red or c.accent, 0.2) or hover_bg
    end)
    button:connect_signal("mouse::leave", function() button.bg = transparent end)
    return button
end

local function sync_titlebar(cl)
    if not titlebars[cl] then return end
    local floating = cl.floating or awful.layout.get(cl.screen) == awful.layout.suit.floating
    local visible = floating and not (cl.fullscreen or cl.maximized or cl.maximized_horizontal or cl.maximized_vertical)
    local _, height = cl:titlebar_top()
    if visible and height == 0 then
        awful.titlebar.show(cl)
    elseif not visible and height > 0 then
        awful.titlebar.hide(cl)
    end
end

-- Changing a workspace's layout also changes whether its clients need handles.
screen.connect_signal("arrange", function(s)
    for _, cl in ipairs(s.clients) do sync_titlebar(cl) end
end)

function theme.titlebar_fun(cl)
    local title = awful.titlebar.widget.titlewidget(cl)
    title.font, title.align, title.ellipsize = theme.widget_font, "left", "end"
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
    local heading = wibox.container.margin(title, dpi(10), dpi(10))
    heading:buttons(drag)
    awful.titlebar(cl, { size = dpi(28) }):setup({
        heading, nil,
        {
            title_button("−", function() cl.minimized = true end),
            title_button("×", function() cl:kill() end, true),
            layout = wibox.layout.fixed.horizontal,
        },
        layout = wibox.layout.align.horizontal,
    })
    -- Tiled clients use their app's own chrome. Floating windows get a handle.
    titlebars[cl] = true
    for _, property in ipairs({ "floating", "fullscreen", "maximized", "maximized_horizontal", "maximized_vertical", "screen" }) do
        cl:connect_signal("property::" .. property, sync_titlebar)
    end
    sync_titlebar(cl)
end

local function separator()
    return wibox.container.margin(wibox.widget({
        forced_width = dpi(1), color = line, widget = wibox.widget.separator,
    }), dpi(6), dpi(6), dpi(12), dpi(12))
end

local function icon_button(name, tooltip, action, alternate)
    local image = wibox.widget({
        image = icons.get(name, theme.muted, dpi(15)),
        forced_width = dpi(15), forced_height = dpi(15), widget = wibox.widget.imagebox,
    })
    local button = wibox.container.background(wibox.container.place(image, "center", "center"), transparent, rounded)
    button.forced_width = dpi(28)
    button:buttons(gears.table.join(awful.button({}, 1, action), awful.button({}, 3, alternate or action)))
    button:connect_signal("mouse::enter", function() image.image = icons.get(name, c.accent, dpi(15)) end)
    button:connect_signal("mouse::leave", function() image.image = icons.get(name, theme.muted, dpi(15)) end)
    awful.tooltip({ objects = { button }, text = tooltip })
    return button
end

local plugin_colors = gears.table.clone(c, true)
for _, segment in pairs(plugin_colors.seg or {}) do
    segment.bg, segment.fg, segment.icon = c.surface, theme.muted, theme.muted
end

local function tag_update(widget, tag)
    local indicator = widget:get_children_by_id("indicator_role")[1]
    indicator.color = tag.urgent and (c.red or c.accent) or tag.selected and c.accent or theme.muted
    indicator.visible = tag.selected or tag.urgent or #tag:clients() > 0
end

function theme.at_screen_connect(s)
    s.quake = lain.util.quake({ app = awful.util.terminal })
    gears.wallpaper.maximized(theme.wallpaper_for(s), s, false)
    awful.tag(awful.util.tagnames, s, awful.layout.suit.tile)
    for _, tag in ipairs(s.tags) do
        tag.master_width_factor = 0.6
        tag.gap_single_client = true
    end
    s.tags[2].layout = awful.layout.suit.max
    s.tags[3].layout = awful.layout.suit.max
    s.mypromptbox = awful.widget.prompt()

    s.mytaglist = awful.widget.taglist({
        screen = s, filter = awful.widget.taglist.filter.all, buttons = awful.util.taglist_buttons,
        layout = { spacing = dpi(2), layout = wibox.layout.flex.horizontal },
        widget_template = {
            {
                nil,
                {
                    { id = "text_role", align = "center", widget = wibox.widget.textbox },
                    widget = wibox.container.place,
                },
                {
                    { id = "indicator_role", forced_height = dpi(2), widget = wibox.widget.separator },
                    left = dpi(8), right = dpi(8), widget = wibox.container.margin,
                },
                layout = wibox.layout.align.vertical,
            },
            top = dpi(4), bottom = dpi(4),
            widget = wibox.container.margin,
            create_callback = tag_update, update_callback = tag_update,
        },
    })
    local tags = wibox.container.constraint(s.mytaglist, "exact", dpi(268))
    s.mytasklist = awful.widget.tasklist({
        screen = s, filter = awful.widget.tasklist.filter.focused, buttons = awful.util.tasklist_buttons,
        widget_template = {
            { id = "text_role", ellipsize = "end", widget = wibox.widget.textbox },
            id = "background_role", widget = wibox.container.background,
        },
    })
    local task = wibox.container.constraint(s.mytasklist, "max", dpi(240))
    shared_widgets = shared_widgets or build_widgets({ colors = c, theme = theme })
    local widgets = shared_widgets
    s.fs = widgets.fs

    local clock = wibox.widget.textclock("%a %d %b   <b>%H:%M</b>", 30)
    clock.font = "JetBrains Mono 9"
    s.cal = lain.widget.cal({
        attach_to = { clock }, followtag = true,
        notification_preset = { font = theme.font, fg = c.fg, bg = c.surface },
    })

    s.mylayoutbox = awful.widget.layoutbox(s)
    s.mylayoutbox:buttons(gears.table.join(
        awful.button({}, 1, function() awful.layout.inc(1, s) end),
        awful.button({}, 3, function() awful.layout.inc(-1, s) end),
        awful.button({}, 4, function() awful.layout.inc(1, s) end),
        awful.button({}, 5, function() awful.layout.inc(-1, s) end)
    ))
    local layoutbox = wibox.container.constraint(
        wibox.container.margin(s.mylayoutbox, 0, 0, dpi(11), dpi(11)), "exact", dpi(14)
    )
    local left = {
        icon_button("launcher", "App launcher · right-click for Awesome menu", function()
            awful.screen.focus(s)
            run_shell.launch()
        end, function() awful.util.mymainmenu:toggle() end),
        separator(), tags, task, s.mypromptbox,
        spacing = dpi(8), layout = wibox.layout.fixed.horizontal,
    }
    local right = { spacing = dpi(14), layout = wibox.layout.fixed.horizontal }
    -- The primary-screen systray follows hotplugging without duplicate icons.
    local tray = wibox.widget.systray()
    tray:set_base_size(dpi(14))
    tray:set_screen("primary")
    table.insert(right, wibox.container.margin(tray, 0, 0, dpi(11), dpi(11)))
    local plugin_containers = {}
    local function plugin_container(widget)
        local container = wibox.container.margin(widget, 0, 0, dpi(8), dpi(8))
        for _, child in ipairs(container:get_all_children()) do
            if child.set_font then child.font = theme.widget_font end
        end
        plugin_containers[#plugin_containers + 1] = container
        return container
    end
    require("plugins")(left, right, plugin_container, plugin_colors, s)
    local system = wibox.container.margin(widgets.system)
    local network = wibox.container.margin(widgets.network)
    table.insert(right, system)
    table.insert(right, network)
    table.insert(right, widgets.volume)
    table.insert(right, widgets.battery)
    table.insert(right, clock)
    table.insert(right, layoutbox)
    table.insert(right, icon_button("power", "Session controls", function() logout.launch({ screen = s }) end))

    local left_layout, right_layout = wibox.widget(left), wibox.widget(right)
    local row = wibox.layout.align.horizontal(left_layout, nil, right_layout)
    row.expand = "inside"
    s.mywibox = awful.wibar({ screen = s, position = "top", height = dpi(37), bg = c.surface, fg = c.fg })
    s.mywibox:setup({
        {
            row, left = dpi(16), right = dpi(12), widget = wibox.container.margin,
        },
        nil,
        { forced_height = dpi(1), color = line, widget = wibox.widget.separator },
        layout = wibox.layout.align.vertical,
    })

    local function resize()
        local width = s.geometry.width
        tags.width = width < dpi(600) and dpi(180) or dpi(268)
        left_layout.spacing = width < dpi(600) and dpi(4) or dpi(8)
        right_layout.spacing = width < dpi(600) and dpi(8) or dpi(14)
        task.visible = width >= dpi(1300)
        clock.format = width >= dpi(1100) and "%a %d %b   <b>%H:%M</b>" or "<b>%H:%M</b>"
        system.visible, network.visible, layoutbox.visible = width >= dpi(850), width >= dpi(850), width >= dpi(850)
        for _, container in ipairs(plugin_containers) do container.visible = width >= dpi(1000) end
    end
    s:connect_signal("property::geometry", resize)
    resize()
end

return theme

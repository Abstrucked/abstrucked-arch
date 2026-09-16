--[[

     Powerarrow Awesome WM theme
     github.com/lcpz

--]]

local gears = require("gears")
local gfs = require("gears.filesystem")
local lain = require("lain")
local awful = require("awful")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local logout = require("awesome-wm-widgets.logout-widget.logout")
local math, string, os, screen = math, string, os, screen
local my_table = awful.util.table or gears.table -- 4.{0,1} compatibility

local theme = {}
theme.bgDir = os.getenv("THEME_BG_DIR") or os.getenv("HOME") .. "/.backgrounds"
theme.dir = gfs.get_configuration_dir() .. "themes/powerarrow"
theme.wallpaper = theme.bgDir .. "/cosmo.png"
theme.wallpaperUltrawide = theme.bgDir .. "/arch_wide_bluish.png"

function theme.wallpaper_for(s)
	if s.geometry.width == 3440 and s.geometry.height == 1440 then
		return theme.wallpaperUltrawide
	end
	return theme.wallpaper
end

theme.font = "JetBrains Mono Nerd Font 10"

theme.fg_normal = "#cdd6f4" -- Font Color
theme.bg_normal = "#1e1e2e"

theme.fg_focus = "#ffffff"
theme.bg_focus = "#C0C0A2" -- Bars BG Color

theme.fg_urgent = "#aaaaaa"
theme.bg_urgent = "#fab387"

theme.taglist_fg_focus = "#fab387"
theme.taglist_bg_focus = "#00000000"

theme.tasklist_bg_focus = "#00000000"
theme.tasklist_fg_focus = "#fab387"

--theme.tasklist_bg_normal                        = "#333333"
--theme.tasklist_fg_normal                        = "#999999"

theme.border_width = dpi(0)
theme.border_normal = "#c2c490"
theme.border_focus = "#7b998a"
theme.border_marked = "#c2c490"

theme.titlebar_fg_focus = "#9399b2"
theme.titlebar_bg_focus = "#313244"
theme.titlebar_bg_normal = "#11111b"
theme.titlebar_fg_normal = "#a6adc8"

theme.menu_height = dpi(16)
theme.menu_width = dpi(140)
theme.menu_submenu_icon = theme.dir .. "/icons/submenu.png"
theme.awesome_icon = theme.dir .. "/icons/awesome_icon.png"
theme.taglist_squares_sel = theme.dir .. "/icons/square_sel.png"
theme.taglist_squares_unsel = theme.dir .. "/icons/square_unsel.png"
theme.layout_tile = theme.dir .. "/icons/tile.png"
theme.layout_tileleft = theme.dir .. "/icons/tileleft.png"
theme.layout_tilebottom = theme.dir .. "/icons/tilebottom.png"
theme.layout_tiletop = theme.dir .. "/icons/tiletop.png"
theme.layout_fairv = theme.dir .. "/icons/fairv.png"
theme.layout_fairh = theme.dir .. "/icons/fairh.png"
theme.layout_spiral = theme.dir .. "/icons/spiral.png"
theme.layout_dwindle = theme.dir .. "/icons/dwindle.png"
theme.layout_max = theme.dir .. "/icons/max.png"
theme.layout_fullscreen = theme.dir .. "/icons/fullscreen.png"
theme.layout_magnifier = theme.dir .. "/icons/magnifier.png"
theme.layout_floating = theme.dir .. "/icons/floating.png"
theme.widget_ac = theme.dir .. "/icons/ac.png"
theme.widget_battery = theme.dir .. "/icons/battery.png"
theme.widget_battery_low = theme.dir .. "/icons/battery_low.png"
theme.widget_battery_empty = theme.dir .. "/icons/battery_empty.png"
theme.widget_brightness = theme.dir .. "/icons/brightness.png"
theme.widget_mem = theme.dir .. "/icons/mem.png"
theme.widget_cpu = theme.dir .. "/icons/cpu.png"
theme.widget_temp = theme.dir .. "/icons/temp.png"
theme.widget_net = theme.dir .. "/icons/net.png"
theme.widget_hdd = theme.dir .. "/icons/hdd.png"
theme.widget_music = theme.dir .. "/icons/note.png"
theme.widget_music_on = theme.dir .. "/icons/note_on.png"
theme.widget_music_pause = theme.dir .. "/icons/pause.png"
theme.widget_music_stop = theme.dir .. "/icons/stop.png"
theme.widget_vol = theme.dir .. "/icons/vol.png"
theme.widget_vol_low = theme.dir .. "/icons/vol_low.png"
theme.widget_vol_no = theme.dir .. "/icons/vol_no.png"
theme.widget_vol_mute = theme.dir .. "/icons/vol_mute.png"
theme.widget_mail = theme.dir .. "/icons/mail.png"
theme.widget_mail_on = theme.dir .. "/icons/mail_on.png"
theme.widget_task = theme.dir .. "/icons/task.png"
theme.widget_scissors = theme.dir .. "/icons/scissors.png"
theme.tasklist_plain_task_name = true
theme.tasklist_disable_icon = false
theme.useless_gap = 4
theme.titlebar_close_button_focus = theme.dir .. "/icons/titlebar/close_focus.png"
theme.titlebar_close_button_normal = theme.dir .. "/icons/titlebar/close_normal.png"
theme.titlebar_ontop_button_focus_active = theme.dir .. "/icons/titlebar/ontop_focus_active.png"
theme.titlebar_ontop_button_normal_active = theme.dir .. "/icons/titlebar/ontop_normal_active.png"
theme.titlebar_ontop_button_focus_inactive = theme.dir .. "/icons/titlebar/ontop_focus_inactive.png"
theme.titlebar_ontop_button_normal_inactive = theme.dir .. "/icons/titlebar/ontop_normal_inactive.png"
theme.titlebar_sticky_button_focus_active = theme.dir .. "/icons/titlebar/sticky_focus_active.png"
theme.titlebar_sticky_button_normal_active = theme.dir .. "/icons/titlebar/sticky_normal_active.png"
theme.titlebar_sticky_button_focus_inactive = theme.dir .. "/icons/titlebar/sticky_focus_inactive.png"
theme.titlebar_sticky_button_normal_inactive = theme.dir .. "/icons/titlebar/sticky_normal_inactive.png"
theme.titlebar_floating_button_focus_active = theme.dir .. "/icons/titlebar/floating_focus_active.png"
theme.titlebar_floating_button_normal_active = theme.dir .. "/icons/titlebar/floating_normal_active.png"
theme.titlebar_floating_button_focus_inactive = theme.dir .. "/icons/titlebar/floating_focus_inactive.png"
theme.titlebar_floating_button_normal_inactive = theme.dir .. "/icons/titlebar/floating_normal_inactive.png"
theme.titlebar_maximized_button_focus_active = theme.dir .. "/icons/titlebar/maximized_focus_active.png"
theme.titlebar_maximized_button_normal_active = theme.dir .. "/icons/titlebar/maximized_normal_active.png"
theme.titlebar_maximized_button_focus_inactive = theme.dir .. "/icons/titlebar/maximized_focus_inactive.png"
theme.titlebar_maximized_button_normal_inactive = theme.dir .. "/icons/titlebar/maximized_normal_inactive.png"
theme.icon_theme = "Numix"
local markup = lain.util.markup

-- Volume
local volumebar_widget = require("awesome-wm-widgets.volumebar-widget.volumebar")

local function build_screen_widgets()
	local widgets = {}

	widgets.clock = wibox.widget.textclock("<span font='Misc Tamsyn 5'> </span>%H:%M ")
	widgets.clock.font = theme.font

	widgets.cal = lain.widget.cal({
		followtag = true,
		notification_preset = {
			font = "Monospace 11",
			fg = theme.fg_normal,
			bg = theme.bg_normal,
			border_color = theme.border_focus,
			border_width = dpi(2),
			timeout = 0,
		},
	})

	local memicon = wibox.widget.imagebox(theme.widget_mem)
	widgets.mem = lain.widget.mem({
		settings = function()
			widget:set_markup(markup.font(theme.font, " " .. mem_now.used .. "MB "))
		end,
	})

	local cpuicon = wibox.widget.imagebox(theme.widget_cpu)
	widgets.cpu = lain.widget.cpu({
		settings = function()
			widget:set_markup(markup.font(theme.font, " " .. cpu_now.usage .. "% "))
		end,
	})

	local fsicon = wibox.widget.imagebox(theme.widget_hdd)
	widgets.fs = lain.widget.fs({
		followtag = true,
		notification_preset = { fg = theme.fg_normal, bg = theme.bg_normal, font = "InputMono 8" },
		settings = function()
			local root = fs_now["/"]
			if root then
				local fsp = string.format("%3.2f%s", root.free, root.units)
				widget:set_markup(markup.font(theme.font, fsp))
			end
		end,
	})

	local baticon = wibox.widget.imagebox(theme.widget_battery)
	widgets.bat = lain.widget.bat({
		notification_preset = { fg = theme.fg_normal, bg = theme.bg_normal, font = "Monospace 10" },
		settings = function()
			if bat_now.status and bat_now.status ~= "N/A" then
				if bat_now.ac_status == 1 then
					widget:set_markup(markup.font(theme.font, " AC "))
					baticon:set_image(theme.widget_ac)
					return
				elseif bat_now.perc and tonumber(bat_now.perc) <= 5 then
					baticon:set_image(theme.widget_battery_empty)
				elseif bat_now.perc and tonumber(bat_now.perc) <= 15 then
					baticon:set_image(theme.widget_battery_low)
				else
					baticon:set_image(theme.widget_battery)
				end
				widget:set_markup(markup.font(theme.font, " " .. bat_now.perc .. "% "))
			else
				widget:set_markup()
				baticon:set_image(theme.widget_ac)
			end
		end,
	})

	local neticon = wibox.widget.imagebox(theme.widget_net)
	widgets.net = lain.widget.net({
		screen = function()
			return awful.screen.focused()
		end,
		notification_preset = { fg = theme.fg_normal, bg = theme.bg_normal, font = "Monospace 10" },
		settings = function()
			widget:set_markup(
				markup.fontfg(
					theme.font,
					theme.titlebar_fg_focus,
					" ↓ "
						.. string.format("%.1f", net_now.received / 1024)
						.. " MiB/s ↑ "
						.. string.format("%.1f", net_now.sent / 1024)
						.. " MiB/s "
					)
			)
		end,
	})

	widgets.volume = volumebar_widget({
		main_color = theme.bg_urgent,
		mute_color = "#777E7655",
		width = 80,
		shape = "rounded_bar",
		margins = 4,
		timeout = 2,
	})
	widgets.memicon = memicon
	widgets.cpuicon = cpuicon
	widgets.fsicon = fsicon
	widgets.baticon = baticon
	widgets.neticon = neticon

	return widgets
end

function theme.powerline_rl(cr, width, height)
	local arrow_depth, offset = height / 2, 0
	if arrow_depth < 0 then
		width = width + 2 * arrow_depth
		offset = -arrow_depth
	end
	-- Avoid going out of the (potential) clip area
	cr:move_to(offset + arrow_depth, 0)
	cr:line_to(offset + width, 0)
	cr:line_to(offset + width - arrow_depth, height / 2)
	cr:line_to(offset + width, height)
	cr:line_to(offset + arrow_depth, height)
	cr:line_to(offset, height / 2)

	cr:close_path()
end
local function pl(widget, bgcolor, padding)
	return wibox.container.background(wibox.container.margin(widget, dpi(16), dpi(16)), bgcolor, theme.powerline_rl)
end

function theme.at_screen_connect(s)
	-- Quake application
	s.quake = lain.util.quake({ app = awful.util.terminal })
	local widgets = build_screen_widgets()
	s.cal = widgets.cal
	s.fs = widgets.fs

	gears.wallpaper.maximized(theme.wallpaper_for(s), s, true)

	-- Tags
	awful.tag(awful.util.tagnames, s, awful.layout.layouts)
	s.tags[1].layout = lain.layout.centerwork
	s.tags[2].layout = awful.layout.suit.max
	s.tags[3].layout = awful.layout.suit.max
	-- Create a promptbox for each screen
	s.mypromptbox = awful.widget.prompt()
	-- Create an imagebox widget which will contains an icon indicating which layout we're using.
	-- We need one layoutbox per screen.
	s.mylayoutbox = awful.widget.layoutbox(s)
	s.mylayoutbox:buttons(my_table.join(
		awful.button({}, 1, function()
			awful.layout.inc(1)
		end),
		awful.button({}, 2, function()
			awful.layout.set(awful.layout.layouts[1])
		end),
		awful.button({}, 3, function()
			awful.layout.inc(-1)
		end),
		awful.button({}, 4, function()
			awful.layout.inc(1)
		end),
		awful.button({}, 5, function()
			awful.layout.inc(-1)
		end)
	))

	-- Create a taglist widget
	s.mytaglist = awful.widget.taglist(s, awful.widget.taglist.filter.all, awful.util.taglist_buttons)

	-- Create a tasklist widget
	s.mytasklist = awful.widget.tasklist(s, awful.widget.tasklist.filter.currenttags, awful.util.tasklist_buttons)

	-- Create the wibox
	s.mywibox =
		awful.wibar({ position = "top", screen = s, height = dpi(18), bg = theme.bg_normal, fg = theme.fg_normal })

	local right_widgets = {
		layout = wibox.layout.fixed.horizontal,
	}
	if s == screen.primary then
		table.insert(right_widgets, wibox.widget.systray())
	end
	table.insert(right_widgets, pl(widgets.volume, "#4B3B5122"))
	table.insert(right_widgets, pl(wibox.widget({ widgets.memicon, widgets.mem.widget, layout = wibox.layout.align.horizontal }), "#4B3B5122"))
	table.insert(right_widgets, pl(wibox.widget({ widgets.cpuicon, widgets.cpu.widget, layout = wibox.layout.align.horizontal }), "#C0C0A222"))
	table.insert(right_widgets, pl(wibox.widget({ widgets.fsicon, widgets.fs.widget, layout = wibox.layout.align.horizontal }), "#4B3B5122"))
	table.insert(right_widgets, pl(wibox.widget({ widgets.baticon, widgets.bat.widget, layout = wibox.layout.align.horizontal }), "#8DAA9A22"))
	table.insert(right_widgets, pl(wibox.widget({ widgets.neticon, widgets.net.widget, layout = wibox.layout.align.horizontal }), "#C0C0A222"))
	table.insert(right_widgets, pl(widgets.clock, "#4B3B5122"))
	table.insert(right_widgets, logout.widget({}))
	table.insert(right_widgets, pl(s.mylayoutbox, ""))

	-- Add widgets to the wibox
	s.mywibox:setup({
		layout = wibox.layout.align.horizontal,
		{ -- Left widgets
			layout = wibox.layout.fixed.horizontal,
			--spr,
			s.mytaglist,
			s.mypromptbox,
			-- spr,
		},
		s.mytasklist, -- Middle widget
		right_widgets,
	})
end

return theme

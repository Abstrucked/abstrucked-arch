--[[

     Powerarrow Awesome WM theme
     github.com/lcpz

--]]

local gears = require("gears")
local lain = require("lain")
local awful = require("awful")
local wibox = require("wibox")
local dpi = require("beautiful.xresources").apply_dpi
local logout = require("awesome-wm-widgets.logout-widget.logout")
local math, string, os = math, string, os
local my_table = awful.util.table or gears.table -- 4.{0,1} compatibility

local theme = {}
theme.dir = os.getenv("HOME") .. "/.config/awesome/themes/powerarrow"
theme.wallpaper = theme.dir .. "/cosmo.png"
theme.wallpaperUltrawide = theme.dir .. "/arch_wide_bluish.png"
theme.font = "JetBrains Mono Nerd Font 10"

theme.fg_normal = "#cdd6f4" -- Font Color
theme.bg_normal = "#1e1e2e"

theme.fg_focus = "#ffffff"
theme.bg_focus = "#C0C0A2" -- Bars BG Color

theme.fg_urgent = "#aaaaaa"
theme.bg_urgent = "#fab387"

theme.taglist_fg_focus = "#fab387"
theme.taglist_bg_focus = "#"

theme.tasklist_bg_focus = "#"
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
local separators = lain.util.separators

-- Binary clock
--local binclock = require("themes.powerarrow.binclock"){
--    height = dpi(32),
--    show_seconds = true,
--    color_active = theme.fg_normal,
--    color_inactive = theme.bg_focus
--}
-- Textclock
--os.setlocale(os.getenv("LANG")) -- to localize the clock
local mytextclock = wibox.widget.textclock("<span font='Misc Tamsyn 5'> </span>%H:%M ")
mytextclock.font = theme.font

-- Calendar
theme.cal = lain.widget.cal({
	cal = "cal --color=always",
	-- attach_to = { mytextclock },
	-- notification_preset = {
	-- 	--font = "Monospace 11",
	-- 	fg = theme.fg_normal,
	-- 	bg = theme.bg_normal,
	-- },
})

-- WIDGET EXAMPLE
--[[local w = wibox {
    visible = true,
    width = 1000,
    height = 100,
    bg = "#ffffff55",
    fg = "#000000",
    below = false,
}
w:setup {
    
    widget = wibox.widget.textclock
}--]]
-- Taskwarrior
-- local task = wibox.widget.imagebox(theme.widget_task)
-- lain.widget.contrib.task.attach(task, {
-- 	-- do not colorize output
-- 	show_cmd = "task | sed -r 's/\\x1B\\[([0-9]{1,2}(;[0-9]{1,2})?)?[mGK]//g'",
-- })
-- task:buttons(my_table.join(awful.button({}, 1, lain.widget.contrib.task.prompt)))

-- Scissors (xsel copy and paste)
-- local scissors = wibox.widget.imagebox(theme.widget_scissors)
-- scissors:buttons(my_table.join(awful.button({}, 1, function()
-- 	awful.spawn.with_shell("xsel | xsel -i -b")
-- end)))

-- Mail IMAP check
--commented because it needs to be set before use
--[[local mailicon = wibox.widget.imagebox(theme.widget_mail)
mailicon:buttons(my_table.join(awful.button({ }, 1, function () awful.spawn(mail) end)))
theme.mail = lain.widget.imap({
    timeout  = 180,
    server   = "server",
    mail     = "mail",
    password = "keyring get mail",
    settings = function()
        if mailcount > 0 then
            widget:set_text(" " .. mailcount .. " ")
            mailicon:set_image(theme.widget_mail_on)
        else
            widget:set_text("")
            mailicon:set_image(theme.widget_mail)
        end
    end
})
--]]

-- Volume
local volumebar_widget = require("awesome-wm-widgets.volumebar-widget.volumebar")
--[[local volicon = wibox.widget.imagebox(theme.widget_vol)
theme.volume = lain.widget.alsa({
    settings = function()
        if volume_now.status == "off" then
            volicon:set_image(theme.widget_vol_mute)
        elseif tonumber(volume_now.level) == 0 then
            volicon:set_image(theme.widget_vol_no)
        elseif tonumber(volume_now.level) <= 50 then
            volicon:set_image(theme.widget_vol_low)
        else
            volicon:set_image(theme.widget_vol)
        end

        widget:set_markup(markup.font(theme.font, " " .. volume_now .. "% "))
    end
})
--]]

-- ALSA volume
--[[theme.volume = lain.widget.alsabar({
    togglechannel = "IEC958,3",
    notification_preset = { fg = theme.fg_normal },
})--]]
--local volume_widget = require("awesome-wm-widgets.volume-widget.volume")

-- Spotify  widget
local spotify_widget = require("awesome-wm-widgets.spotify-widget.spotify")

-- -- MPD
-- local musicplr = awful.util.terminal .. "-e, ncmpcpp"
-- local mpdicon = wibox.widget.imagebox(theme.widget_music)
-- mpdicon:buttons(my_table.join(
-- 	awful.button({ modkey }, 1, function()
-- 		awful.spawn.with_shell(musicplr)
-- 	end),
-- 	awful.button({}, 1, function()
-- 		os.execute("mpc prev")
-- 		theme.mpd.update()
-- 	end),
-- 	awful.button({}, 2, function()
-- 		os.execute("mpc toggle")
-- 		theme.mpd.update()
-- 	end),
-- 	awful.button({}, 3, function()
-- 		os.execute("mpc next")
-- 		theme.mpd.update()
-- 	end)

-- 	settings = function()
-- 		if mpd_now.state == "play" then
-- 			artist = " " .. mpd_now.artist .. " "
-- 			title = mpd_now.title .. " "
-- 			mpdicon:set_image(theme.widget_music_on)
-- 			widget:set_markup(markup.font(theme.font, markup(theme.bg_urgent, artist) .. " " .. title))
-- 		elseif mpd_now.state == "pause" then
-- 			widget:set_markup(markup.font(theme.font, "||"))
-- 			mpdicon:set_image(theme.widget_music_pause)
-- 		else
-- 			widget:set_text("")
-- 			mpdicon:set_image(theme.widget_music)
-- 		end
-- 	end,
-- })

-- MEM
local memicon = wibox.widget.imagebox(theme.widget_mem)
local mem = lain.widget.mem({
	settings = function()
		widget:set_markup(markup.font(theme.font, " " .. mem_now.used .. "MB "))
	end,
})

-- CPU
local cpuicon = wibox.widget.imagebox(theme.widget_cpu)
local cpu = lain.widget.cpu({
	settings = function()
		widget:set_markup(markup.font(theme.font, " " .. cpu_now.usage .. "% "))
	end,
})
-- [Coretemp (lm_sensors, per core)
--[[local tempwidget = awful.widget.watch({ awful.util.shell, "-c", "sensors | grep Core" }, 30, function(widget, stdout)
	local temps = ""
	for line in stdout:gmatch("[^\r\n]+") do
		temps = temps .. line:match("+(%d+).*°C") .. "° " -- in Celsius
	end
	widget:set_markup(markup.font(theme.font, " " .. temps))
end)--]]
-- Coretemp (lain, average)

local temp = lain.widget.temp({
	settings = function()
		widget:set_markup(markup.font(theme.font, " " .. coretemp_now .. "°C "))
	end,
})

-- local tempicon = wibox.widget.imagebox(theme.widget_temp)

-- / fs
local fsicon = wibox.widget.imagebox(theme.widget_hdd)
-- commented because it needs Gio/Glib >= 2.54
theme.fs = lain.widget.fs({
	notification_preset = { fg = theme.fg_normal, bg = theme.bg_normal, font = "InputMono 8" },
	settings = function()
		local fsp = string.format("%3.2f%s", fs_now["/"].free, fs_now["/"].units)
		widget:set_markup(markup.font(theme.font, fsp))
	end,
})

-- Battery
--[[local baticon = wibox.widget.imagebox(theme.widget_battery)
local bat = lain.widget.bat({
    settings = function()
        if bat_now.status and bat_now.status ~= "N/A" then
            if bat_now.ac_status == 1 then
                widget:set_markup(markup.font(theme.font, " AC "))
                baticon:set_image(theme.widget_ac)
                return
            elseif not bat_now.perc and tonumber(bat_now.perc) <= 5 then
                baticon:set_image(theme.widget_battery_empty)
            elseif not bat_now.perc and tonumber(bat_now.perc) <= 15 then
                baticon:set_image(theme.widget_battery_low)
            else
                baticon:set_image(theme.widget_battery)
            end
            widget:set_markup(markup.font(theme.font, " " .. bat_now.perc .. "% "))
        else
            widget:set_markup()
            baticon:set_image(theme.widget_ac)
        end
    end
})
--]]

-- Net
local neticon = wibox.widget.imagebox(theme.widget_net)
local net = lain.widget.net({
	settings = function()
		widget:set_markup(
			markup.fontfg(
				theme.font,
				theme.titlebar_fg_focus,
				" ↓ " .. net_now.received .. " ↑ " .. net_now.sent .. " "
			)
		)
	end,
})

--[[Brigtness
local brighticon = wibox.widget.imagebox(theme.widget_brightness)
-- If you use xbacklight, comment the line with "light -G" and uncomment the line bellow
 local brightwidget = awful.widget.watch('xbacklight -get', 0.1,
--local brightwidget = awful.widget.watch('light -G', 0.1,
    function(widget, stdout, stderr, exitreason, exitcode)
        local brightness_level = tonumber(string.format("%.0f", stdout))
        widget:set_markup(markup.font(theme.font, " " .. brightness_level .. "%"))
end)
]]
--
-- Separators
local arrow = separators.arrow_left

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
function theme.rouded_bar(cr, width, height) end
--  local shape.rounded_bar(cr, 70, 70) --arrow_depth, offset = height/2, 0

local function pl(widget, bgcolor, padding)
	return wibox.container.background(wibox.container.margin(widget, dpi(16), dpi(16)), bgcolor, theme.powerline_rl)
end

function theme.at_screen_connect(s)
	-- Quake application
	s.quake = lain.util.quake({ app = awful.util.terminal })

	-- If wallpaper is a function, call it with the screen

	-- Set wallpaper based on screen resolution

	if s.geometry.width == 3440 and s.geometry.height == 1440 then
		local wallpaper = theme.wallpaperUltrawide
		if type(wallpaper) == "function" then
			wallpaper = wallpaper(s)
		end
		gears.wallpaper.maximized(wallpaper, s, true)
	else
		local wallpaper = theme.wallpaper
		if type(wallpaper) == "function" then
			wallpaper = wallpaper(s)
		end
		gears.wallpaper.maximized(wallpaper, s, true)
	end
	-- local function set_wallpaper(s)
	--     wallpaper_safety =	function(arg)	if 	type(arg) == "table" then	return tostring( arg[s.index] or "" )
	--                             elseif	type(arg) == "string" then
	--                                 return arg
	--                             else
	--                                 return ""
	--                             end
	--                         end
	--                         gears.wallpaper.maximized( (theme.dir or "") .. wallpaper_safety( theme.wallpaper ), s, true )
	-- end

	-- Tags
	awful.tag(awful.util.tagnames, s, awful.layout.layouts)

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
		{ -- Right widgets
			layout = wibox.layout.fixed.horizontal,
			wibox.widget.systray(),
			-- wibox.container.margin(scissors, dpi(4), dpi(8)), -- using shapes
			-- pl(wibox.widget({ mpdicon, theme.mpd.widget, layout = wibox.layout.align.horizontal }), "#C0C0A222"),
			pl(
				volumebar_widget({
					main_color = theme.bg_urgent,
					mute_color = "#777E7655",
					width = 80,
					shape = "rounded_bar",
					margins = 4,
				}),
				"#4B3B5122"
			),
			-- default
			pl(spotify_widget()),
			-- customized
			--[[spotify_widget({
           fontont = 'Ubuntu Mono 9',
           play_icon = '/usr/share/icons/Papirus-Light/24x24/categories/spotify.svg',
           pause_icon = '/usr/share/icons/Papirus-Dark/24x24/panel/spotify-indicator.svg'
        }),--]]

			-- pl(task, "#C0C0A222"),
			--pl(wibox.widget { mailicon, mail and theme.mail.widget, layout = wibox.layout.align.horizontal }, "#777E7622"),
			pl(wibox.widget({ memicon, mem.widget, layout = wibox.layout.align.horizontal }), "#4B3B5122"),
			pl(wibox.widget({ cpuicon, cpu.widget, layout = wibox.layout.align.horizontal }), "#C0C0A222"),
			-- pl(wibox.widget({ tempicon, temp.widget, layout = wibox.layout.align.horizontal }), "#4B3B5122"),
			pl(
				wibox.widget({ fsicon, theme.fs and theme.fs.widget, layout = wibox.layout.align.horizontal }),
				"#4B3B5122"
			),
			--pl(wibox.widget { baticon, bat.widget, layout = wibox.layout.align.horizontal }, "#8DAA9A22"),
			pl(wibox.widget({ neticon, net.widget, layout = wibox.layout.align.horizontal }), "#C0C0A222"),
			pl(mytextclock, "#4B3B5122"),
			logout.widget({}),

			--[[
	    -- using separators
            -- arrow(theme.bg_normal, "#34343400"),
            wibox.container.background(wibox.container.margin(wibox.widget { mailicon, theme.mail and theme.mail.widget, layout = wibox.layout.align.horizontal }, dpi(4), dpi(7)), "#34343400"),
            -- arrow("#34343400", theme.bg_normal),
             wibox.container.background(wibox.container.margin(wibox.widget { mpdicon, theme.mpd.widget, layout = wibox.layout.align.horizontal }, dpi(3), dpi(6)), "#CB755B00"),
            -- arrow(theme.bg_normal, "#34343400"),
             wibox.container.background(wibox.container.margin(task, dpi(3), dpi(7)), "#34343400"),
            -- arrow("#34343422", "#777E7600"),
            wibox.container.background(wibox.container.margin(wibox.widget { memicon, mem.widget, layout = wibox.layout.align.horizontal }, dpi(2), dpi(3)), "#777E7600"),
            -- arrow("#00000000", "#4B69aa"),
            wibox.container.background(wibox.container.margin(wibox.widget { cpuicon, cpu.widget, layout = wibox.layout.align.horizontal }, dpi(3), dpi(4)), "#4B696D00"),
            -- arrow("#4B696D22", "#4B3B5100"),
            --wibox.container.background(wibox.container.margin(wibox.widget { tempicon, temp.widget, layout = wibox.layout.align.horizontal }, dpi(4), dpi(4)), "#4B3B5100"),
            -- arrow("#4B3B5122", "#CB755B00"),
            wibox.container.background(wibox.container.margin(wibox.widget { fsicon, theme.fs and theme.fs.widget, layout = wibox.layout.align.horizontal }, dpi(3), dpi(3)), "#CB755B00"),
            -- arrow("#CB755B22", "#8DAA9A00"),
            wibox.container.background(wibox.container.margin(wibox.widget { baticon, bat.widget, layout = wibox.layout.align.horizontal }, dpi(3), dpi(3)), "#8DAA9A00"),
            -- arrow("#8DAA9A00", "#C0C0A200"),
            wibox.container.background(wibox.container.margin(wibox.widget { nil, neticon, net.widget, layout = wibox.layout.align.horizontal }, dpi(3), dpi(3)), "#C0C0A200"),
            -- arrow("#C0C0A200", "#4B696D00"),
            wibox.container.background(wibox.container.margin(volicon, dpi(8), dpi(8)), "#4B696D00"),
            -- arrow("#4B696D00", "#777e7600"),
            wibox.container.background(wibox.container.margin(mytextclock, dpi(4), dpi(8)), "#777E7600"),
            -- arrow("#777E7600", "alpha"),
            --]]
			pl(s.mylayoutbox, ""),
		},
	})
end

return theme

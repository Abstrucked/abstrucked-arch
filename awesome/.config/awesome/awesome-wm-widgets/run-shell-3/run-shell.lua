-------------------------------------------------
-- Run Shell for Awesome Window Manager
-- More details could be found here:
-- https://github.com/streetturtle/awesome-wm-widgets/tree/master/run-shell

-- @author Pavel Makhov
-- @copyright 2018 Pavel Makhov
-- @copyright 2019 Pavel Makhov
-------------------------------------------------

local awful = require("awful")
local gfs = require("gears.filesystem")
local wibox = require("wibox")
local gears = require("gears")
local naughty = require("naughty")
local beautiful = require("beautiful")
local completion = require("awful.completion")
local math, os, string = math, os, string

local run_shell = awful.widget.prompt()
run_shell.with_shell = true

local widget = {}

function widget.new()
	local cache_dir = gfs.get_cache_dir() .. "run-shell/"
	gfs.make_directories(cache_dir)

	local widget_instance = {
		_cached_wiboxes = {},
		_running = false,
	}

	function widget_instance:_create_wibox(s)
		local w = wibox({
			visible = false,
			ontop = true,
			border_width = 0,
			screen = s,
			height = s.geometry.height,
			width = s.geometry.width,
		})

		w:setup({
			{
				{
					{
						{
							markup = '<span font="awesomewm-font 14" color="' .. beautiful.fg_normal .. '">a</span>',
							widget = wibox.widget.textbox,
						},
						id = "icon",
						left = 10,
						layout = wibox.container.margin,
					},
					{
						run_shell,
						left = 10,
						layout = wibox.container.margin,
					},
					id = "left",
					layout = wibox.layout.fixed.horizontal,
				},
				widget = wibox.container.background,
					bg = beautiful.popup_bg or "#313244",
					shape = beautiful.popup_shape or function(cr, width, height)
						gears.shape.rounded_rect(cr, width, height, 8)
					end,
					forced_width = 360,
					forced_height = 56,
			},
			layout = wibox.container.place,
		})

		return w
	end

	function widget_instance:_capture_command(s, image_path)
		local geometry = s.geometry
		local display = os.getenv("DISPLAY") or ":0.0"
		return {
			"ffmpeg",
			"-loglevel",
			"error",
			"-f",
			"x11grab",
			"-video_size",
			string.format("%dx%d", geometry.width, geometry.height),
			"-y",
			"-i",
			string.format("%s+%d,%d", display, geometry.x, geometry.y),
			"-vf",
			"boxblur=7",
			"-frames:v",
			"1",
			image_path,
		}
	end

	function widget_instance:launch(s)
		if self._running then
			return
		end

		s = s or awful.screen.focused()
		local w = self._cached_wiboxes[s]
		if not w then
			w = self:_create_wibox(s)
			self._cached_wiboxes[s] = w
		end

		w.screen = s
		w.width = s.geometry.width
		w.height = s.geometry.height

		local image_path = string.format(
			"%scapture-%d-%d.png",
			cache_dir,
			os.time(),
			math.random(1, 1000000000)
		)
		self._running = true

		awful.spawn.easy_async(self:_capture_command(s, image_path), function(_, stderr, reason, exitcode)
			if reason ~= "exit" or exitcode ~= 0 then
				self._running = false
				awful.spawn({ "rm", "-f", image_path }, false)
				naughty.notify({
					title = "Run prompt",
					text = stderr ~= "" and stderr or "Could not capture the screen",
				})
				return
			end

			w.visible = true
			w.bgimage = image_path
				awful.placement.top(w, { margins = { top = 2 }, parent = s })
			awful.prompt.run({
				prompt = "Run: ",
					bg_cursor = beautiful.bg_focus,
				textbox = run_shell.widget,
				completion_callback = completion.shell,
				exe_callback = function(command)
					run_shell:spawn_and_handle_error(command)
				end,
				history_path = cache_dir .. "history",
				done_callback = function()
					w.visible = false
					w.bgimage = nil
					self._running = false
					awful.spawn({ "rm", "-f", image_path }, false)
				end,
			})
		end)
	end

	return widget_instance
end

local function get_default_widget()
	if not widget.default_widget then
		widget.default_widget = widget.new()
	end
	return widget.default_widget
end

function widget.launch(...)
	return get_default_widget():launch(...)
end

return widget

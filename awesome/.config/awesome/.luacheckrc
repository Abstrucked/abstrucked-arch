-- luacheck configuration for the AwesomeWM configuration.
-- Run with: luacheck rc.lua

std = "lua53"

-- `client.focus` is assignable, so `client` cannot be read-only.
globals = { "client" }

-- Globals injected by the AwesomeWM C core; see `man awesomerc`.
read_globals = {
	"awesome",
	"button",
	"drawable",
	"drawin",
	"key",
	"keygrabber",
	"mouse",
	"mousegrabber",
	"root",
	"screen",
	"selection",
	"tag",
	"window",
}

-- lain widget callbacks receive their state through globals.
files["themes/"] = {
	read_globals = {
		"bat_now",
		"cpu_now",
		"fs_now",
		"mem_now",
		"net_now",
		"volume_now",
		"weather_now",
		"widget",
	},
}

-- Vendored third-party code is linted upstream, not here.
exclude_files = {
	"awesome-buttons/",
	"awesome-wm-widgets/",
	"freedesktop/",
	"lain/",
	"volume-widget/",
}

max_line_length = 140

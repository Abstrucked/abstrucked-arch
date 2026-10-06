-- Regression checks for the Powerarrow theme's bar spacing and
-- composition. Every Awesome module is mocked, so the real theme
-- file runs without a desktop and the widget trees it builds can
-- be inspected directly.
local theme_path = arg[1]
assert(theme_path, "usage: lua test_powerarrow.lua <theme.lua>")
local theme_dir = theme_path:match("(.*/)")

-- The palette the theme renders with: the installed one when the
-- generated colors are present, a stand-in otherwise.
local ok, palette = pcall(dofile, theme_dir .. "colors.lua")
if not ok or type(palette) ~= "table" or not palette.seg then
	palette = {
		bg = "#1e1e2e",
		fg = "#cdd6f4",
		accent = "#fab387",
		surface = "#313244",
		bg_dark = "#11111b",
		muted = "#a6adc8",
		bar_bg = "#c0c0a2",
		border_normal = "#c2c490",
		border_focus = "#7b998a",
		titlebar_fg_focus = "#9399b2",
		seg = {
			ai = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#fab387" },
			volume = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#89b4fa" },
			mem = { bg = "#3c3d50", fg = "#cdd6f4", icon = "#f9e2af" },
			cpu = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#f38ba8" },
			fs = { bg = "#3c3d50", fg = "#cdd6f4", icon = "#94e2d5" },
			bat = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#a6e3a1" },
			bat_mid = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#f9e2af" },
			bat_low = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#f38ba8" },
			net = { bg = "#3c3d50", fg = "#cdd6f4", icon = "#89b4fa" },
			clock = { bg = "#fab387", fg = "#11111b", icon = "#11111b" },
			layout = { bg = "#2e2f40", fg = "#cdd6f4", icon = "#cdd6f4" },
		},
	}
end

-- A fixed scale proves every geometry goes through dpi().
package.preload["beautiful.xresources"] = function()
	return { apply_dpi = function(value) return value * 2 end }
end
local dpi = require("beautiful.xresources").apply_dpi

-- A stand-in for the wibox widget system: every widget records its
-- children, properties and handlers, so the test can inspect what
-- the theme built.
local wibox = {}
local build_widget -- forward declaration: setup() calls it below

local widget_methods = {
	connect_signal = function(self, name, handler)
		self.signals[name] = self.signals[name] or {}
		table.insert(self.signals[name], handler)
	end,
	buttons = function(self, widget_buttons)
		self.buttons = widget_buttons
	end,
	set_text = function(self, text) self.text = text end,
	set_markup = function(self, markup) self.markup = markup end,
	set_image = function(self, image) self.image = image end,
	set_margins = function(self, value)
		self.left = value
		self.right = value
		self.top = value
		self.bottom = value
	end,
	get_children = function(self) return self.children end,
	get_all_children = function(self)
		local all = {}
		for _, child in ipairs(self.children) do
			table.insert(all, child)
			for _, grandchild in ipairs(child:get_all_children()) do
				table.insert(all, grandchild)
			end
		end
		return all
	end,
	get_children_by_id = function(self, wanted)
		local found = {}
		for _, child in ipairs(self:get_all_children()) do
			if child.id == wanted then
				table.insert(found, child)
			end
		end
		return found
	end,
	setup = function(self, spec)
		self.setup_spec = build_widget(spec)
	end,
}

local function new_widget(kind)
	return setmetatable(
		{ widget = kind, children = {}, signals = {} },
		{ __index = widget_methods }
	)
end

-- Only text widgets carry a font, like the real ones.
local function new_text_widget(kind)
	local widget = new_widget(kind)
	widget.set_font = function(self, font) self.font = font end
	return widget
end

local function is_widget(value)
	return type(value) == "table" and type(value.widget) == "string"
		and type(value.children) == "table"
end

-- The declarative constructor: a table with a layout becomes a
-- layout widget, a table with a widget key applies its properties
-- to that widget, and anything else is already a widget.
build_widget = function(spec)
	if type(spec) == "string" then
		local widget = new_text_widget("textbox")
		widget.text = spec
		return widget
	end
	assert(type(spec) == "table", "widget spec must be a table or a string")
	if is_widget(spec) then
		return spec
	end
	local children = {}
	local layout, instance, constructor
	local properties = {}
	for key, value in pairs(spec) do
		if type(key) == "number" then
			children[key] = value
		elseif key == "layout" then
			layout = value
		elseif key == "widget" then
			if type(value) == "function" then
				constructor = value
			else
				instance = value
			end
		else
			properties[key] = value
		end
	end
	if constructor or instance then
		local widget = instance or constructor()
		for key, value in pairs(properties) do
			widget[key] = value
		end
		return widget
	end
	local widget = new_widget(layout and layout.name or "layout")
	widget.layout = layout
	for key, value in pairs(properties) do
		widget[key] = value
	end
	for _, child in ipairs(children) do
		table.insert(widget.children, build_widget(child))
	end
	return widget
end

local function layout_kind(name)
	return { name = name }
end

wibox.layout = {
	fixed = {
		horizontal = layout_kind("fixed.horizontal"),
		vertical = layout_kind("fixed.vertical"),
	},
	align = {
		horizontal = layout_kind("align.horizontal"),
		vertical = layout_kind("align.vertical"),
	},
}

wibox.widget = setmetatable({
	textbox = function() return new_text_widget("textbox") end,
	imagebox = function(image)
		local widget = new_widget("imagebox")
		widget.image = image
		return widget
	end,
	textclock = function(format)
		local widget = new_text_widget("textclock")
		widget.format = format
		return widget
	end,
	systray = function()
		local widget = new_widget("systray")
		widget.role = "systray"
		return widget
	end,
	base = {
		make_widget = function() return new_widget("base") end,
	},
}, {
	__call = function(_, spec)
		return build_widget(spec)
	end,
})

wibox.container = {
	background = function(child, background, shape)
		local widget = new_widget("background")
		widget.bg = background
		widget.shape = shape
		if child then
			table.insert(widget.children, build_widget(child))
		end
		return widget
	end,
	margin = function(child, left, right, top, bottom)
		local widget = new_widget("margin")
		widget.left = left or 0
		widget.right = right or 0
		widget.top = top or 0
		widget.bottom = bottom or 0
		if child then
			table.insert(widget.children, build_widget(child))
		end
		return widget
	end,
	place = function(child, halign, valign)
		local widget = new_widget("place")
		widget.halign = halign or "center"
		widget.valign = valign or "center"
		if child then
			table.insert(widget.children, build_widget(child))
		end
		return widget
	end,
}

package.preload["wibox"] = function()
	return wibox
end

package.preload["gears"] = function()
	return {
		color = {
			recolor_image = function(path, color)
				return "recolor:" .. path .. ":" .. color
			end,
		},
		wallpaper = { maximized = function() end },
		shape = { rounded_rect = function() end },
		table = { join = function(...) return { ... } end },
	}
end

package.preload["gears.filesystem"] = function()
	return {
		get_configuration_dir = function() return "/test-config/" end,
		get_themes_dir = function() return "/test-themes/" end,
		file_readable = function() return false end,
	}
end

package.preload["themes.colors"] = function()
	return palette
end

local notifications, destroyed = {}, {}
package.preload["naughty"] = function()
	return {
		config = { defaults = {}, presets = {} },
		notify = function(args)
			local notification = { args = args }
			table.insert(notifications, notification)
			return notification
		end,
		destroy = function(notification)
			table.insert(destroyed, notification)
		end,
	}
end

-- Lain widgets run their settings callback once at creation, the
-- way lain's timers fire immediately; the settings read globals
-- (mem_now and friends) that the test fills in.
local lain_widgets, lain_args = {}, {}

local function lain_widget(kind)
	return function(args)
		args = args or {}
		lain_args[kind] = args
		local textbox = new_text_widget("textbox")
		textbox.role = kind
		local wrapper = {
			widget = textbox,
			update = function()
				-- lain's own update fills these globals from the
				-- system before settings(); the test sets them to
				-- choose the displayed values, so only defaults.
				mem_now = mem_now or { used = 0 }
				cpu_now = cpu_now or { usage = 0 }
				fs_now = fs_now or {}
				bat_now = bat_now or {}
				net_now = net_now or { received = 0, sent = 0 }
				widget = textbox
				if args.settings then
					args.settings()
				end
			end,
		}
		wrapper.update()
		lain_widgets[kind] = wrapper
		return wrapper
	end
end

package.preload["lain"] = function()
	return {
		util = {
			markup = {},
			quake = function() return {} end,
		},
		layout = { centerwork = "centerwork" },
		widget = {
			cal = function(args)
				lain_args.cal = args or {}
				return {}
			end,
			mem = lain_widget("mem"),
			cpu = lain_widget("cpu"),
			fs = lain_widget("fs"),
			bat = lain_widget("bat"),
			net = lain_widget("net"),
		},
	}
end

package.preload["awful"] = function()
	return {
		util = {
			terminal = "xterm",
			tagnames = { "1", "2", "3" },
			taglist_buttons = { "taglist" },
			tasklist_buttons = { "tasklist" },
			table = { join = function(...) return { ... } end },
		},
		tag = function(names, screen, layouts)
			screen.tags = {}
			for index, name in ipairs(names) do
				screen.tags[index] = {
					name = name,
					layout = layouts[index],
					selected = index == 1,
					clients = function() return {} end,
				}
			end
			return screen.tags
		end,
		layout = {
			layouts = { "tile", "max" },
			inc = function() end,
			set = function() end,
			suit = { max = "max" },
		},
		button = function(_, number, callback)
			return { button = number, callback = callback }
		end,
		widget = {
			prompt = function() return new_text_widget("promptbox") end,
			layoutbox = function(screen)
				local imagebox = new_widget("imagebox")
				imagebox.id = "imagebox"
				local textbox = new_text_widget("textbox")
				textbox.id = "textbox"
				local box = new_widget("layoutbox")
				box.role = "layoutbox"
				box.children = { imagebox, textbox }
				box.layout = wibox.layout.fixed.horizontal
				box.screen = screen
				return box
			end,
			taglist = setmetatable({
				filter = { all = "all" },
			}, {
				__call = function(_, args)
					local widget = new_widget("taglist")
					widget.taglist_args = args
					return widget
				end,
			}),
			tasklist = setmetatable({
				filter = { currenttags = "currenttags" },
			}, {
				__call = function(_, screen, filter, buttons)
					local widget = new_widget("tasklist")
					widget.tasklist_filter = filter
					widget.tasklist_buttons = buttons
					return widget
				end,
			}),
		},
		wibar = function(args)
			local widget = new_widget("wibar")
			widget.wibar_args = args
			return widget
		end,
	}
end

-- The vendored widgets, mirrored closely enough to check how the
-- theme wraps them.
local logout_args, power_mode_args, volumebar_args

package.preload["awesome-wm-widgets.logout-widget.logout"] = function()
	return {
		widget = function(args)
			logout_args = args
			-- The vendored widget: a fixed row holding the icon
			-- inside a 4px margin, with its own buttons.
			local imagebox = new_widget("imagebox")
			imagebox.role = "logout-icon"
			-- A real imagebox has no set_margins; hide the shared mock one.
			imagebox.set_margins = false
			local padded = new_widget("margin")
			padded.left = 4
			padded.right = 4
			padded.top = 4
			padded.bottom = 4
			padded.children = { imagebox }
			local row = new_widget("fixed.horizontal")
			row.role = "logout"
			row.layout = wibox.layout.fixed.horizontal
			row.children = { padded }
			row:buttons({ { button = 1 } })
			return row
		end,
	}
end

package.preload["awesome-wm-widgets.power-mode-widget.power-mode"] = function()
	return {
		widget = function(args)
			power_mode_args = args
			local widget = new_text_widget("textbox")
			widget.role = "power-mode"
			return widget
		end,
	}
end

package.preload["awesome-wm-widgets.volumebar-widget.volumebar"] = function()
	return setmetatable({}, {
		__call = function(_, args)
			volumebar_args = args
			local widget = new_widget("progressbar")
			widget.role = "volume"
			-- The vendored widget reacts to clicks and scrolling.
			widget:connect_signal("button::press", function() end)
			return widget
		end,
	})
end

-- The generated Plugins module: records the API it receives and
-- optionally contributes a segment, to exercise both cases.
local plugin_calls = {}
local plugins_enabled = false

package.preload["plugins"] = function()
	return function(left_widgets, right_widgets, pl, plugin_palette, screen)
		table.insert(plugin_calls, {
			left_widgets = left_widgets,
			right_widgets = right_widgets,
			pl = pl,
			palette = plugin_palette,
			screen = screen,
		})
		if plugins_enabled then
			local textbox = new_text_widget("textbox")
			textbox.role = "plugin"
			table.insert(right_widgets, pl(textbox, plugin_palette.seg.ai))
		end
	end
end

-- The global screen table the theme captures at load time.
screen = { primary = nil }

local theme = dofile(theme_path)

-- Test helpers.
local function find_all(root, predicate, results)
	results = results or {}
	if predicate(root) then
		table.insert(results, root)
	end
	for _, child in ipairs(root.children or {}) do
		find_all(child, predicate, results)
	end
	return results
end

local function find(root, predicate)
	return find_all(root, predicate)[1]
end

local function by_role(role)
	return function(widget) return widget.role == role end
end

local function icon_of(path, color)
	return "recolor:" .. path .. ":" .. color
end

local function by_image(path, color)
	return function(widget)
		return widget.widget == "imagebox" and widget.image == icon_of(path, color)
	end
end

-- A gap is an empty base widget; anything else is a segment
-- whose first text role identifies it. The clock is a bare
-- textclock, so its kind identifies it.
local function entry_signature(entry)
	if entry.widget == "base" and #entry.children == 0 then
		return "gap"
	end
	for _, child in ipairs(entry:get_all_children()) do
		if child.role then
			return child.role
		end
		if child.widget == "textclock" then
			return "clock"
		end
	end
	return "unknown"
end

local function entry_by_signature(right, wanted)
	for _, entry in ipairs(right.children) do
		if entry_signature(entry) == wanted then
			return entry
		end
	end
	error("no right-side entry named " .. wanted)
end

-- The flattened right-side order: the tray (primary only), plugin
-- segments, a group gap, the built-in metrics, another group gap,
-- then the clock and the two controls.
local function expected_right(primary, with_plugins)
	local expected = {}
	if primary then
		expected[#expected + 1] = "systray"
	end
	if with_plugins then
		expected[#expected + 1] = "plugin"
	end
	if primary or with_plugins then
		expected[#expected + 1] = "gap"
	end
	for _, name in ipairs({ "volume", "mem", "cpu", "fs", "bat", "net" }) do
		expected[#expected + 1] = name
	end
	expected[#expected + 1] = "gap"
	for _, name in ipairs({ "clock", "logout", "layoutbox" }) do
		expected[#expected + 1] = name
	end
	return expected
end

-- The chevron path, recorded point by point.
local function trace(width, height)
	local ops = {}
	local cr = {}
	function cr.move_to(_, x, y) ops[#ops + 1] = { "move_to", x, y } end
	function cr.line_to(_, x, y) ops[#ops + 1] = { "line_to", x, y } end
	function cr.close_path(_) ops[#ops + 1] = { "close_path" } end
	theme.powerline_rl(cr, width, height)
	return ops
end

local function reset()
	plugins_enabled = false
	plugin_calls = {}
	lain_widgets, lain_args = {}, {}
	notifications, destroyed = {}, {}
	logout_args, power_mode_args, volumebar_args = nil, nil, nil
	mem_now, cpu_now, fs_now, bat_now, net_now = nil, nil, nil, nil, nil
	widget = nil
end

local function new_screen()
	return {
		index = 1,
		outputs = {},
		geometry = { width = 1920, height = 1080 },
		tags = {},
	}
end

local function build_bar(primary, with_plugins)
	reset()
	plugins_enabled = with_plugins
	local s = new_screen()
	screen.primary = primary and s or nil
	theme.at_screen_connect(s)
	return s
end

-- One scenario: the outer arrangement, the flattened right-side
-- order with its group gaps, and every spacing decision.
local function check_scenario(primary, with_plugins, name)
	local function expect(condition, message)
		assert(condition, name .. ": " .. message)
	end

	local s = build_bar(primary, with_plugins)
	local tree = s.mywibox.setup_spec

	-- The bar keeps its height and its outer arrangement: tags
	-- and prompt on the left, the tasklist filling the middle,
	-- the segments on the right.
	expect(s.mywibox.wibar_args.height == dpi(24), "bar height")
	expect(tree.layout == wibox.layout.align.horizontal, "outer layout")
	expect(#tree.children == 3, "outer arrangement")
	local left, middle, right = tree.children[1], tree.children[2], tree.children[3]
	expect(left.layout == wibox.layout.fixed.horizontal, "left layout")
	expect(#left.children == 2, "only tags and prompt on the left")
	expect(left.children[1] == s.mytaglist, "taglist comes first")
	expect(left.children[2] == s.mypromptbox, "prompt comes second")
	expect(middle.widget == "margin", "tasklist margin wrapper")
	expect(middle.left == dpi(12) and middle.right == dpi(12), "tasklist margins")
	expect(middle.children[1] == s.mytasklist, "tasklist fills the middle")
	expect(right.layout == wibox.layout.fixed.horizontal, "right layout")

	-- The flattened right-side order, with gaps only between
	-- logical groups.
	local expected = expected_right(primary, with_plugins)
	expect(#right.children == #expected, "right-side entry count")
	for index, wanted in ipairs(expected) do
		local entry = right.children[index]
		expect(entry_signature(entry) == wanted,
			string.format("right entry %d is %s, not %s",
				index, entry_signature(entry), wanted))
		if wanted == "gap" then
			expect(entry.widget == "base", "gap is a base widget")
			expect(entry.forced_width == dpi(6), "gap width")
			expect(entry.forced_height == 1, "gap height")
			expect(#entry.children == 0, "gap has no children")
		end
	end

	-- Plugins receive the original arrays and the segment API.
	local call = plugin_calls[1]
	expect(type(call.pl) == "function", "segment API handed to plugins")
	expect(call.left_widgets.layout == wibox.layout.fixed.horizontal, "original left array")
	expect(#call.left_widgets == 2, "left array contents")
	expect(call.left_widgets[1] == s.mytaglist, "taglist in the left array")
	expect(call.left_widgets[2] == s.mypromptbox, "prompt in the left array")
	expect(call.right_widgets.layout == wibox.layout.fixed.horizontal, "original right array")
	expect(#call.right_widgets == #expected, "right array holds every entry")
	expect(call.palette == palette, "palette handed to plugins")
	expect(call.screen == s, "screen handed to plugins")

	-- The segment API: symmetric padding, a plain-string
	-- background for legacy callers, a numeric padding override,
	-- and vertical centering by a real place container.
	local pl = call.pl
	local probe = new_text_widget("textbox")
	probe.role = "probe"
	local numeric = pl(probe, palette.seg.mem, 4)
	local legacy = pl(probe, "#aabbcc")
	local segment = pl(probe, palette.seg.mem)
	expect(numeric.children[1].children[1].left == dpi(4)
		and numeric.children[1].children[1].right == dpi(4), "numeric padding override")
	expect(legacy.bg == "#aabbcc" and legacy.fg == nil, "legacy string segment")
	expect(segment.bg == palette.seg.mem.bg, "segment background")
	expect(segment.fg == palette.seg.mem.fg, "segment foreground")
	expect(segment.shape == theme.powerline_rl, "segment shape")
	local placed = segment.children[1]
	expect(placed.widget == "place" and placed.valign == "center", "vertical centering")
	local padded = placed.children[1]
	expect(padded.widget == "margin"
		and padded.left == dpi(10) and padded.right == dpi(10), "symmetric segment padding")

	-- The segment font reaches text widgets wrapped inside.
	local probe_text = new_text_widget("textbox")
	probe_text.role = "probe-text"
	pl(wibox.widget({
		new_widget("imagebox"),
		probe_text,
		spacing = dpi(4),
		layout = wibox.layout.fixed.horizontal,
	}), palette.seg.mem)
	expect(probe_text.font == theme.widget_font, "segment font reaches wrapped text")

	-- Icon and text form a fixed row with a small gap, not an
	-- align layout that would stretch them.
	local mem_entry = entry_by_signature(right, "mem")
	local mem_group = find(mem_entry, function(widget)
		return widget.layout == wibox.layout.fixed.horizontal
	end)
	expect(mem_group.widget == "fixed.horizontal", "icon-text group layout")
	expect(mem_group.spacing == dpi(4), "icon-text spacing")
	expect(#mem_group.children == 2, "icon and text only")
	local mem_icon = mem_group.children[1]
	expect(mem_icon.widget == "imagebox", "icon comes first")
	expect(mem_icon.image == icon_of(theme.widget_mem, palette.seg.mem.icon), "memory icon")
	expect(mem_icon.forced_width == dpi(14) and mem_icon.forced_height == dpi(14),
		"icon size")
	expect(mem_group.children[2].role == "mem", "text comes second")

	-- The segment around the group centers and pads it.
	local mem_segment = find(mem_entry, function(widget)
		return widget.widget == "background"
	end)
	expect(mem_segment.children[1].widget == "place"
		and mem_segment.children[1].valign == "center", "segment centering")
	expect(mem_segment.children[1].children[1].left == dpi(10)
		and mem_segment.children[1].children[1].right == dpi(10), "segment padding")
	expect(mem_segment.bg == palette.seg.mem.bg, "memory segment background")
	expect(mem_segment.fg == palette.seg.mem.fg, "memory segment foreground")

	-- The battery group keeps the power mode after the charge,
	-- at the same spacing.
	local bat_entry = entry_by_signature(right, "bat")
	local bat_group = find(bat_entry, function(widget)
		return widget.layout == wibox.layout.fixed.horizontal
	end)
	expect(bat_group.spacing == dpi(4), "battery group spacing")
	expect(#bat_group.children == 3, "icon, charge and power mode")
	expect(bat_group.children[1].widget == "imagebox", "battery icon first")
	expect(bat_group.children[2].role == "bat", "charge second")
	expect(bat_group.children[3].role == "power-mode", "power mode last")
	expect(power_mode_args.icon_font == theme.widget_font, "power mode icon font")

	-- Fixed slots and centered text for every changing value.
	local function slot_check(role, width)
		local textbox = find(tree, by_role(role))
		expect(textbox.forced_width == dpi(width), role .. " slot width")
		expect(textbox.align == "center", role .. " slot alignment")
		return textbox
	end
	local cpu_textbox = slot_check("cpu", 28)
	local bat_textbox = slot_check("bat", 28)
	slot_check("net", 80)
	slot_check("mem", 40)
	slot_check("fs", 40)
	local clock_widget = find(tree, function(widget)
		return widget.widget == "textclock"
	end)
	expect(clock_widget.forced_width == dpi(36), "clock slot width")
	expect(clock_widget.align == "center", "clock slot alignment")
	expect(clock_widget.format == "%H:%M", "plain clock format")

	-- Values render without the old surrounding whitespace.
	cpu_now = { usage = 100 }
	lain_widgets.cpu.update()
	expect(cpu_textbox.text == "100%", "cpu text")

	mem_now = { used = 131072 }
	lain_widgets.mem.update()
	expect(find(tree, by_role("mem")).text == "128.0G", "memory text")

	fs_now = { ["/"] = { free = 128, units = "G" } }
	lain_widgets.fs.update()
	expect(find(tree, by_role("fs")).text == "128.0G", "filesystem text")

	net_now = { received = 2048, sent = 512 }
	lain_widgets.net.update()
	expect(find(tree, by_role("net")).text == "↓2.0M ↑512K", "network text")

	-- The battery shows AC while charging, the charge otherwise,
	-- and its segment and icon follow the charge level.
	local function bat_segment()
		return find(bat_entry, function(widget)
			return widget.widget == "background"
		end)
	end
	bat_now = { status = "Charging", ac_status = 1, perc = 100 }
	lain_widgets.bat.update()
	expect(bat_textbox.text == "AC", "battery AC text")
	expect(bat_segment().bg == palette.seg.bat.bg, "battery segment while charging")

	bat_now = { status = "Discharging", ac_status = 0, perc = 10 }
	lain_widgets.bat.update()
	expect(bat_textbox.text == "10%", "battery charge text")
	expect(bat_segment().bg == palette.seg.bat_low.bg, "low battery segment color")
	expect(bat_group.children[1].image == icon_of(
		theme.widget_battery_low, palette.seg.bat_low.icon), "low battery icon")

	bat_now = { status = "Discharging", ac_status = 0, perc = 3 }
	lain_widgets.bat.update()
	expect(bat_group.children[1].image == icon_of(
		theme.widget_battery_empty, palette.seg.bat_low.icon), "empty battery icon")

	-- The calendar still attaches to the clock, and the lain
	-- tooltips keep their colors and fonts.
	expect(lain_args.cal.attach_to[1] == clock_widget, "calendar attachment")
	expect(lain_args.fs.notification_preset.bg == theme.popup_bg, "fs tooltip background")
	expect(lain_args.fs.notification_preset.font == theme.font, "fs tooltip font")
	expect(lain_args.bat.notification_preset.font == "Monospace 10", "bat tooltip font")
	expect(lain_args.net.screen == s, "net screen")

	-- The volume bar keeps its click and scroll handling, in dpi.
	local volume_widget = find(tree, by_role("volume"))
	expect(volume_widget.signals["button::press"], "volume click and scroll")
	expect(volumebar_args.width == dpi(80), "volume width")
	expect(volumebar_args.margins == dpi(4), "volume margins")
	expect(volumebar_args.main_color == palette.seg.volume.icon, "volume color")

	-- Hover on the network segment still raises and clears its note.
	local net_textbox = find(tree, by_role("net"))
	expect(net_textbox.signals["mouse::enter"], "net hover entry")
	expect(net_textbox.signals["mouse::leave"], "net hover leave")
	net_textbox.signals["mouse::enter"][1]()
	expect(#notifications == 1 and notifications[1].args.title == "Network",
		"net tooltip")
	net_textbox.signals["mouse::leave"][1]()
	expect(#destroyed == 1, "net tooltip dismissed")

	-- The layoutbox icon matches the segment icons, and its
	-- buttons survive being wrapped.
	local layout_imagebox = s.mylayoutbox:get_children_by_id("imagebox")[1]
	expect(layout_imagebox.forced_width == dpi(14)
		and layout_imagebox.forced_height == dpi(14), "layoutbox icon size")
	expect(#s.mylayoutbox.buttons > 0, "layoutbox buttons survive")

	-- The logout control shares the layout segment, with its icon
	-- resized and its internal margin normalized, buttons intact.
	expect(logout_args.icon == icon_of(
		"/test-config/awesome-wm-widgets/logout-widget/power.svg",
		palette.seg.layout.icon), "logout icon color")
	local logout_entry = entry_by_signature(right, "logout")
	local logout_row = find(logout_entry, by_role("logout"))
	expect(#logout_row.buttons > 0, "logout buttons survive")
	expect(find(logout_entry, function(widget)
		return widget.widget == "margin" and widget.left == dpi(4)
	end), "logout internal margin normalized")
	local logout_iconbox = find(logout_entry, by_role("logout-icon"))
	expect(logout_iconbox.forced_width == dpi(14)
		and logout_iconbox.forced_height == dpi(14), "logout icon size")
	local logout_segment = find(logout_entry, function(widget)
		return widget.widget == "background"
	end)
	expect(logout_segment.bg == palette.seg.layout.bg, "logout segment palette")
	expect(logout_segment.fg == palette.seg.layout.fg, "logout segment foreground")
	local layout_segment = find(entry_by_signature(right, "layoutbox"), function(widget)
		return widget.widget == "background"
	end)
	expect(layout_segment.bg == palette.seg.layout.bg, "layout segment palette")

	-- Tags keep their padding and underline rules.
	local template = s.mytaglist.taglist_args.widget_template
	local text_margin = template[1][2]
	expect(text_margin.widget == wibox.container.margin, "tag text margin")
	expect(text_margin.left == dpi(9) and text_margin.right == dpi(9), "tag padding")
	local underline = template[1][3]
	expect(underline.id == "underline_role", "underline role")
	expect(underline.forced_height == dpi(2), "underline thickness")
	expect(underline.widget == wibox.container.background, "underline background")
	local marked = new_widget("background")
	local underline_self = {
		get_children_by_id = function() return { marked } end,
	}
	local function fake_tag(clients, selected)
		return { selected = selected, clients = function() return clients end }
	end
	template.create_callback(underline_self, fake_tag({ 1 }, false))
	expect(marked.bg == theme.taglist_underline, "occupied tag underline")
	template.create_callback(underline_self, fake_tag({ 1 }, true))
	expect(marked.bg == theme.taglist_fg_focus, "active tag underline")
	template.create_callback(underline_self, fake_tag({}, false))
	expect(marked.bg == "#00000000", "empty tag underline")

	-- Fonts are unchanged.
	expect(theme.font == "JetBrains Mono Nerd Font 10", "bar font unchanged")
	expect(theme.widget_font == "JetBrains Mono Nerd Font 8", "widget font unchanged")
	expect(find(tree, by_role("mem")).font == theme.widget_font, "wrapped text font")
end

-- The chevron depth is capped for compactness and bounded by tiny
-- shapes, and the orientation is unchanged.
local ops = trace(200, dpi(24))
local depth = dpi(9)
local function point(index)
	return ops[index][2], ops[index][3]
end
local x, y = point(1)
assert(x == depth and y == 0, "chevron depth is capped")
x, y = point(3)
assert(x == 200 - depth and y == dpi(24) / 2, "right chevron point")
x, y = point(6)
assert(x == 0 and y == dpi(24) / 2, "left chevron point keeps orientation")

ops = trace(16, dpi(24))
x = point(1)
assert(x == 8, "chevron bounded by the shape width")

ops = trace(200, 400)
x = point(1)
assert(x == depth, "chevron stays capped on tall shapes")

-- Composition and spacing, with and without the tray and plugins.
for _, scenario in ipairs({
	{ true, true, "primary with plugins" },
	{ true, false, "primary without plugins" },
	{ false, true, "secondary with plugins" },
	{ false, false, "secondary without plugins" },
}) do
	check_scenario(scenario[1], scenario[2], scenario[3])
end

print("powerarrow spacing tests passed")

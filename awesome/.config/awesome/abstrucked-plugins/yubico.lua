local awful = require("awful")
local wibox = require("wibox")
local gears = require("gears")
local naughty = require("naughty")
local math = math

local yubico = {}

local function notify(title, text)
	naughty.notify({ title = title, text = text })
end

local function shell_quote(value)
	return "'" .. tostring(value):gsub("'", "'\\''") .. "'"
end

local function command_error(stderr, fallback)
	local message = (stderr or ""):gsub("%s+$", "")
	return message ~= "" and message or fallback
end

function yubico.get_accounts(callback)
	awful.spawn.easy_async({ "ykman", "oath", "accounts", "list" }, function(stdout, stderr, reason, exitcode)
		if reason ~= "exit" or exitcode ~= 0 then
			local error_text = command_error(stderr, "Insert a YubiKey to access the account list")
			notify("YubiKey unavailable", error_text)
			callback(nil)
			return
		end

		local items = {}
		for line in stdout:gmatch("[^\r\n]+") do
			table.insert(items, line)
		end

		if #items == 0 then
			notify("No accounts", "No OATH accounts found on the YubiKey")
			callback(nil)
			return
		end

		callback(items)
	end)
end

local function clear_clipboard()
	awful.spawn.easy_async_with_shell(
		"if command -v xclip >/dev/null 2>&1; then printf '' | xclip -selection clipboard; "
			.. "elif command -v xsel >/dev/null 2>&1; then printf '' | xsel -ib; fi",
		function() end
	)
end

local function copy_code(code)
	local quoted_code = shell_quote(code)
	local command = string.format(
		"if command -v xclip >/dev/null 2>&1; then printf '%%s' %s | xclip -selection clipboard; "
			.. "elif command -v xsel >/dev/null 2>&1; then printf '%%s' %s | xsel -ib; else exit 127; fi",
		quoted_code,
		quoted_code
	)

	awful.spawn.easy_async_with_shell(command, function(_, stderr, reason, exitcode)
		if reason ~= "exit" or exitcode ~= 0 then
			notify("Clipboard error", command_error(stderr, "No supported clipboard utility was found"))
			return
		end

		notify("Clipboard", "Code ready; clipboard will be cleared in 30 seconds")
		gears.timer.start_new(30, function()
			clear_clipboard()
			return false
		end)
	end)
end

local function get_account_code(account)
	awful.spawn.easy_async({ "ykman", "oath", "accounts", "code", account }, function(stdout, stderr, reason, exitcode)
		if reason ~= "exit" or exitcode ~= 0 then
			notify("YubiKey error", command_error(stderr, "Could not retrieve the account code"))
			return
		end

		local code = stdout:match("(%d%d%d%d%d%d%d%d)%s*$") or stdout:match("(%d%d%d%d%d%d)%s*$")
		if not code then
			notify("YubiKey error", "Could not retrieve a six- or eight-digit code")
			return
		end

		copy_code(code)
	end)
end

local items = nil
local selected_index = 1
local filter = ""
local filtered_items = {}
local active_keygrabber = nil
local loading = false
local filter_widget = wibox.widget.textbox()

local list_widget = wibox.widget({
	layout = wibox.layout.fixed.vertical,
})

local function update_list()
	filter_widget:set_text("/ " .. filter)
	filtered_items = {}
	for _, item in ipairs(items or {}) do
		if filter == "" or item:lower():find(filter:lower(), 1, true) then
			table.insert(filtered_items, item)
		end
	end

	selected_index = math.max(1, math.min(selected_index, #filtered_items))
	list_widget:reset()
	for i, item in ipairs(filtered_items) do
		local text = (i == selected_index) and "> " .. item or "  " .. item
		list_widget:add(wibox.widget({
			text = text,
			widget = wibox.widget.textbox,
		}))
	end
end

local popup = awful.popup({
	widget = {
		{
			filter_widget,
			list_widget,
			layout = wibox.layout.fixed.vertical,
		},
		margins = 10,
		layout = wibox.container.margin,
	},
	border_color = "#666666",
	font_size = 18,
	border_width = 2,
	placement = awful.placement.centered,
	shape = gears.shape.rounded_rect,
	visible = false,
	ontop = true,
})

function yubico.show_list()
	if loading then
		return
	end
	if active_keygrabber then
		active_keygrabber:stop()
	end

	loading = true
	yubico.get_accounts(function(account_items)
		loading = false
		if not account_items then
			return
		end

		items = account_items
		filter = ""
		selected_index = 1
		update_list()
		popup.screen = awful.screen.focused()
		popup.visible = true

		local keygrabber_instance
		keygrabber_instance = awful.keygrabber({
			start_callback = function()
				popup.visible = true
			end,
			stop_callback = function()
				popup.visible = false
				if active_keygrabber == keygrabber_instance then
					active_keygrabber = nil
				end
			end,
			stop_event = "release",
			keypressed_callback = function(_, _, key, event)
				if event ~= "press" then
					return
				end

				if key == "Escape" then
					keygrabber_instance:stop()
				elseif key == "Return" then
					if selected_index > 0 and selected_index <= #filtered_items then
						keygrabber_instance:stop()
						get_account_code(filtered_items[selected_index])
					end
				elseif key == "BackSpace" then
					filter = filter:sub(1, -2)
					update_list()
				elseif (key == "Up" or key == "Down") and #filtered_items > 0 then
					if key == "Up" then
						selected_index = selected_index > 1 and selected_index - 1 or #filtered_items
					else
						selected_index = selected_index < #filtered_items and selected_index + 1 or 1
					end
					update_list()
				elseif #key == 1 and key:match("%g") then
					filter = filter .. key
					update_list()
				end
			end,
		})

		active_keygrabber = keygrabber_instance
		keygrabber_instance:start()
	end)
end

return yubico

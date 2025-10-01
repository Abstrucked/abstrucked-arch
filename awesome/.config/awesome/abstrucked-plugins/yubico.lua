local awful = require("awful")
local wibox = require("wibox")
local gears = require("gears")
local naughty = require("naughty")

local yubico = {}
local ERROR_NO_YUBIKEY = "ERROR: No YubiKey detected!"

local function isNull(item)
	if item == nil or item == "" then
		return true
	end
	return false
end

function yubico.getAccounts()
	local handle = io.popen("ykman oath accounts list")
	local result = ""
	if handle then
		result = handle:read("*a") or ""
		handle:close()
	end

	if isNull(result) or result:match(ERROR_NO_YUBIKEY) then
		naughty.notify({ title = "Yubikey not found", text = "Insert yubikey to access the account list" })
		return nil
	end

	local items = {}
	for line in result:gmatch("[^\r\n]+") do
		table.insert(items, line)
	end

	-- items is now a Lua array/table of file names
	for i, item in ipairs(items) do
		print(i, item)
	end

	-- Return nil if no accounts were found (empty table)
	if #items == 0 then
		naughty.notify({ title = "No accounts", text = "No OATH accounts found on the YubiKey" })
		return nil
	end

	return items
end

local function getAccountCode(account)
	local handle = io.popen("ykman oath accounts code " .. account)
	local accountData = ""
	if handle then
		accountData = handle:read("*a") or ""
		handle:close()
	end
	local code = accountData:match("(%d%d%d%d%d%d)[^%d]*$")
	if code then
		local cmd = string.format("echo -n '%s' | xclip -selection clipboard", code)
		awful.spawn.easy_async(cmd, function()
			-- Optional callback after copy
			naughty.notify({ title = "Clipboard", text = "Code ready" })
		end)
		os.execute(cmd)
	else
		naughty.notify({ title = "Error", text = "Could not retrieve code from YubiKey" })
	end
end

-- List items
local items = nil

local selected_index = 1

local filter = ""
local filtered_items = {}
local filter_widget = wibox.widget.textbox()

-- Create list widget
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

-- Create popup
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

-- Create and start a fresh keygrabber instance
function yubico.show_list()
	items = yubico.getAccounts()
	if items == nil or #items == 0 then
		return
	end
	filter = ""
	selected_index = 1
	update_list()

	popup.visible = true

	local grabber_ref -- placeholder for the grabber object

	-- Assign grabber_ref before defining keygrabber_instance
	local keygrabber_instance = awful.keygrabber({
		start_callback = function()
			popup.visible = true
		end,
		stop_callback = function()
			popup.visible = false
		end,
		stop_event = "release",
		keypressed_callback = function(self, modifiers, key, event)
			if event ~= "press" then
				return
			end
			if key == "Escape" then
				grabber_ref:stop()
			elseif key == "Return" then
				if selected_index > 0 and selected_index <= #filtered_items then
					grabber_ref:stop()
					getAccountCode(filtered_items[selected_index])
				end
			elseif key == "BackSpace" then
				filter = filter:sub(1, -2)
				update_list()
			elseif key == "Up" then
				if selected_index > 1 then
					selected_index = selected_index - 1
				else
					selected_index = #filtered_items
				end
				update_list()
			elseif key == "Down" then
				if selected_index < #filtered_items then
					selected_index = selected_index + 1
				else
					selected_index = 1
				end
				update_list()
			else
				-- For other keys, if it's a single character, append to filter
				if #key == 1 and key:match("%g") then -- printable characters
					filter = filter .. key
					update_list()
				end
			end
		end,
	})
	grabber_ref = keygrabber_instance -- Now assign it correctly
	keygrabber_instance:start()

	if popup.visible == false then
		keygrabber_instance:stop()
	end
end

return yubico

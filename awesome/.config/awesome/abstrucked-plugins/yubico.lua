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

-- Create list widget
local list_widget = wibox.widget({
	layout = wibox.layout.fixed.vertical,
})

local function update_list()
	list_widget:reset()
	if items then
		for i, item in ipairs(items) do
			local text = (i == selected_index) and "> " .. item or "  " .. item
			list_widget:add(wibox.widget({
				text = text,
				widget = wibox.widget.textbox,
			}))
		end
	end
end

-- Create popup
local popup = awful.popup({
	widget = {
		list_widget,
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

		keybindings = {
			{
				{},
				"Up",
				function()
					selected_index = (selected_index - 2) % #items + 1
					update_list()
				end,
			},
			{
				{},
				"Down",
				function()
					selected_index = (selected_index % #items) + 1
					update_list()
				end,
			},
			{
				{},
				"Return",
				function()
					naughty.notify({ title = "Selected", text = items[selected_index] })
					grabber_ref:stop()
					getAccountCode(items[selected_index])
				end,
			},
			{
				{},
				"Escape",
				function()
					grabber_ref:stop()
				end,
			},
		},
	})
	grabber_ref = keygrabber_instance -- Now assign it correctly
	keygrabber_instance:start()

	if popup.visible == false then
		keygrabber_instance:stop()
	end
end

return yubico

-- Headless regression test for Tide's production theme module.  It executes
-- real screen setup with small Awesome mocks and inspects the resulting trees.
local theme_path = assert(arg[1], "usage: lua test_tide.lua <theme.lua>")
local file = assert(io.open(theme_path, "r"))
local source = file:read("*a")
file:close()

assert(not source:find("build_dock", 1, true), "Tide must not retain a dock builder")
assert(not source:find("tide_dock", 1, true), "Tide must not retain dock references")
assert(not source:find('type = "dock"', 1, true), "Tide must not create dock popups")

local function object(properties)
    local value = properties or {}
    value.signals = {}
    function value:buttons(buttons) self.bound_buttons = buttons end
    function value:connect_signal(name, callback)
        self.signals[name] = self.signals[name] or {}
        table.insert(self.signals[name], callback)
    end
    function value:emit_signal(name, ...)
        for _, callback in ipairs(self.signals[name] or {}) do callback(...) end
    end
    function value:add(child)
        self.children = self.children or {}
        table.insert(self.children, child)
    end
    function value:setup(spec) self.setup_spec = spec end
    function value:get_all_children() return self.children or {} end
    value.get_children_by_id = function() return { object() } end
    function value:set_base_size(size) self.base_size = size end
    function value:set_screen(screen) self.screen = screen end
    return value
end

local popup_records, timer_records, titlebar_calls, shared_widget_calls = {}, {}, 0, 0
local function widget(spec)
    local value = object({ spec = spec })
    if type(spec) == "table" then
        for key, property in pairs(spec) do value[key] = property end
    end
    if value.widget == "graph" then
        value.values = {}
        function value:add_value(number, group)
            number = math.max(0, number)
            if not self.scale then number = math.min(self.max_value, number) end
            table.insert(self.values, { value = number, group = group })
            local limit = (self.width or 100) * (self.stack and 2 or 1)
            while #self.values > limit do table.remove(self.values, 1) end
        end
    end
    return value
end

local wibox = {
    layout = {
        fixed = { horizontal = function() return object() end, vertical = function() return object() end },
        align = {
            horizontal = function(left, middle, right) return object({ left = left, middle = middle, right = right }) end,
            vertical = function(top, middle, bottom) return object({ top = top, middle = middle, bottom = bottom }) end,
        },
        grid = "grid",
    },
    container = {
        background = function(child) return object({ children = { child } }) end,
        constraint = function(child) return object({ children = { child } }) end,
        margin = function(child) return object({ children = { child } }) end,
        place = function(child) return object({ children = { child } }) end,
    },
}
wibox.widget = setmetatable({
    textbox = "textbox", imagebox = "imagebox", progressbar = "progressbar", graph = "graph", separator = "separator",
    textclock = function() return object() end,
    systray = function() return object() end,
}, { __call = function(_, spec) return widget(spec) end })

local titlebar = setmetatable({
    widget = { titlewidget = function() return object() end },
    show = function() titlebar_calls = titlebar_calls + 1 end,
    hide = function() titlebar_calls = titlebar_calls + 1 end,
}, { __call = function()
    titlebar_calls = titlebar_calls + 1
    return object()
end })
local awful = {
    button = function(_, number, callback) return { number = number, callback = callback } end,
    layout = { suit = { floating = {} }, get = function() return {} end, getname = function() return "floating" end,
        inc = function() end },
    mouse = { client = { move = function() end, resize = function() end } },
    popup = function(args)
        local popup = object({ width = args.minimum_width or 260, height = 80 })
        for key, value in pairs(args) do popup[key] = value end
        table.insert(popup_records, popup)
        return popup
    end,
    screen = { focus = function() end },
    spawn = setmetatable({ easy_async = function(_, callback) callback("", "", "", 1) end }, {
        __call = function() end,
    }),
    tag = function(_, screen)
        screen.tags = { { screen = screen, selected = true, master_width_factor = 0 } }
    end,
    titlebar = titlebar,
    tooltip = function() end,
    util = { terminal = "xterm", tagnames = { "1" }, taglist_buttons = {}, tasklist_buttons = {},
        mymainmenu = { toggle = function() end } },
    widget = { prompt = function() return object() end },
    wibar = function(args) return object(args) end,
}
awful.widget.taglist = setmetatable({ filter = { all = function() return true end } }, {
    __call = function() return object() end,
})
awful.widget.tasklist = setmetatable({ filter = { focused = function() return true end } }, {
    __call = function() return object() end,
})

local screen_signals, tag_signals = {}, {}
local screen_api = { connect_signal = function(name, callback) screen_signals[name] = callback end }
local tag_api = { connect_signal = function(name, callback) tag_signals[name] = callback end }
local gears = {
    color = { recolor_image = function(path) return path end },
    filesystem = { get_themes_dir = function() return "/themes/" end },
    shape = { rounded_rect = function() end, rectangle = function() end, rounded_bar = function() end },
    string = { xml_escape = function(value) return value end },
    table = { join = function(...) return { ... } end, clone = function(value) return value end },
    timer = function(args)
        local timer = object({ args = args })
        timer.again = function() if args.callback then args.callback() end end
        function timer:start() self.started = true end
        function timer:stop() self.stopped = true end
        table.insert(timer_records, timer)
        if args.call_now and args.callback then args.callback() end
        return timer
    end,
    wallpaper = { maximized = function() end },
}
local naughty = { config = { defaults = {} } }
local extra_lain_samplers = 0
local modules = {
    awful = awful,
    gears = gears,
    ["gears.filesystem"] = gears.filesystem,
    lain = {
        util = { quake = function() return {} end },
        widget = {
            cal = function() return object() end,
            mem = function() extra_lain_samplers = extra_lain_samplers + 1; return object() end,
            net = function() extra_lain_samplers = extra_lain_samplers + 1; return object() end,
        },
    },
    naughty = naughty,
    wibox = wibox,
    ["beautiful.xresources"] = { apply_dpi = function(value) return value end },
    ["themes.colors"] = { bg = "#111111", surface = "#222222", fg = "#eeeeee", accent = "#00aaff", muted = "#888888" },
    ["themes.mono.style"] = { mix = function(first) return first end, on = function(first) return first end },
    ["themes.mono.icons"] = { get = function() return "icon" end },
    ["themes.mono.widgets"] = function()
        shared_widget_calls = shared_widget_calls + 1
        return { system = object(), network = object(), volume = object(), battery = object(), fs = object() }
    end,
    ["themes.tide.wallpaper"] = function() return "wallpaper" end,
    ["awesome-wm-widgets.run-shell-3.run-shell"] = { launch = function() end },
    ["awesome-wm-widgets.logout-widget.logout"] = { launch = function() end },
    plugins = function() end,
}
local environment = {
    require = function(name) return assert(modules[name], "unexpected module: " .. name) end,
    screen = screen_api,
    tag = tag_api,
    ipairs = ipairs,
    pairs = pairs,
    tonumber = tonumber,
    string = string,
    math = math,
    table = table,
}
setmetatable(environment, { __index = _G })
local legacy_load, legacy_setfenv = rawget(_G, "loadstring"), rawget(_G, "setfenv")
local loader = legacy_load or load
local chunk, err
if legacy_load then
    chunk, err = loader(source, "tide_theme")
    if chunk then legacy_setfenv(chunk, environment) end
else
    chunk, err = loader(source, "tide_theme", "t", environment)
end
assert(chunk, err)
local theme = chunk()

local function walk(value, visit, seen)
    if type(value) ~= "table" then return end
    seen = seen or {}
    if seen[value] then return end
    seen[value] = true
    visit(value)
    for key, child in pairs(value) do
        if key ~= "signals" and key ~= "spec" and type(child) == "table" then walk(child, visit, seen) end
    end
end

local function popup_graph(popup)
    local graph
    walk(popup.widget, function(value)
        if value.widget == "graph" then graph = value end
    end)
    assert(graph, "monitor popup must contain a graph")
    return graph
end

local function popup_has_text(popup, ...)
    local wanted = { ... }
    local found = false
    walk(popup.widget, function(value)
        for _, field in ipairs({ "text", "markup" }) do
            local candidate = value[field]
            if type(candidate) == "string" then
                local matches = true
                for _, fragment in ipairs(wanted) do
                    if not candidate:find(fragment, 1, true) then matches = false; break end
                end
                if matches then found = true end
            end
        end
    end)
    return found
end

local function popup_has_current_text(popup, wanted)
    local found = false
    walk(popup.widget, function(value)
        if value.text == wanted then found = true end
    end)
    return found
end

local function assert_finite(value, message)
    assert(type(value) == "number" and value == value and value ~= math.huge and value ~= -math.huge, message)
end

local function assert_in_workarea(monitors, area)
    local right_edge = monitors[1].x + monitors[1].width
    for _, popup in ipairs(monitors) do
        assert(popup.x >= area.x and popup.y >= area.y, "monitor must not start outside workarea")
        assert(popup.x + popup.width <= area.x + area.width, "monitor must not extend past right edge")
        assert(popup.y + popup.height <= area.y + area.height, "monitor must not extend past bottom edge")
        assert(popup.x + popup.width == right_edge, "monitor right edges must align")
    end
    for first = 1, #monitors do
        for second = first + 1, #monitors do
            local a, b = monitors[first], monitors[second]
            local overlaps = a.x < b.x + b.width and b.x < a.x + a.width
                and a.y < b.y + b.height and b.y < a.y + a.height
            assert(not overlaps, "desktop monitors must not overlap")
        end
    end
end

local function display_timers_since(index)
    local matches = {}
    for number = index + 1, #timer_records do
        local timer = timer_records[number]
        if timer.args.timeout == 2 and timer.args.autostart then table.insert(matches, timer) end
    end
    return matches
end

assert(theme.titlebars_enabled == false, "titlebars must be disabled")
assert(screen_signals.arrange == nil, "titlebar arrange listener must be removed")
assert(type(tag_signals["property::layout"]) == "function", "layout chip listener must remain")
assert(type(tag_signals["property::selected"]) == "function", "workspace chip listener must remain")
local client = object({ titlebar_top = function() return nil, 0 end })
assert(pcall(theme.titlebar_fun, client), "explicit titlebar requests must be harmless")
assert(titlebar_calls == 0, "explicit titlebar requests must not build titlebars")

local test_screen = object({
    clients = {},
    geometry = { x = 0, y = 0, width = 1920, height = 1080 },
    workarea = { x = 0, y = 0, width = 1920, height = 1080 },
})
local timers_before_screen = #timer_records
theme.at_screen_connect(test_screen)
assert(test_screen.tide_dock == nil, "screen setup must not create a dock")
assert(test_screen.mywibox and test_screen.mywibox.position == "top", "top status bar must remain")
assert(test_screen.tide_monitor and test_screen.tide_ram_monitor and test_screen.tide_network_monitor,
    "screen setup must expose CPU, RAM, and network monitors")
assert(type(test_screen.tide_monitors) == "table" and #test_screen.tide_monitors == 3,
    "screen setup must expose exactly three ordered monitors")
local monitors = test_screen.tide_monitors
assert(monitors[1] == test_screen.tide_monitor and monitors[2] == test_screen.tide_ram_monitor
    and monitors[3] == test_screen.tide_network_monitor, "monitor order must be CPU, RAM, network")
for _, popup in ipairs(monitors) do
    assert(popup.type == "desktop", "every monitor must be a desktop popup")
end
for _, popup in ipairs(popup_records) do assert(popup.type ~= "dock", "screen setup must not create a dock popup") end

local cpu_graph, ram_graph, network_graph = popup_graph(monitors[1]), popup_graph(monitors[2]), popup_graph(monitors[3])
assert(cpu_graph.max_value == 100 and ram_graph.max_value == 100, "CPU and RAM graphs must be bounded at 100")
assert(network_graph.stack == true and network_graph.scale == true and network_graph.max_value == 1,
    "network graph must be stacked and auto-scaled")
assert(type(network_graph.stack_colors) == "table" and network_graph.stack_colors[1] ~= network_graph.stack_colors[2],
    "network graph groups must use distinct colors")
assert(not popup_has_text(monitors[1], "nan") and not popup_has_text(monitors[2], "inf")
    and not popup_has_text(monitors[3], "nan"),
    "missing readings must use an em dash, never non-finite text")
assert(popup_has_text(monitors[1], "—") and popup_has_text(monitors[2], "—") and popup_has_text(monitors[3], "—"),
    "missing readings must render an em dash")

local display_timers = display_timers_since(timers_before_screen)
assert(#display_timers == 1, "one shared two-second display timer is required per screen")
local display_timer = display_timers[1]
local function refresh() display_timer.args.callback() end

environment.cpu_now = { usage = "17" }
environment.mem_now = { perc = "25", used = "2048", total = "8192" }
environment.net_now = { devices = { eth0 = { received = "999999999", sent = "999999999" } } }
refresh()
assert(cpu_graph.values[#cpu_graph.values].value == 17, "CPU strings must update the CPU graph")
assert(ram_graph.values[#ram_graph.values].value == 25, "RAM percentage strings must update the RAM graph")
assert(popup_has_text(monitors[2], "25%") and popup_has_text(monitors[2], "2.0")
    and popup_has_text(monitors[2], "8.0") and popup_has_text(monitors[2], "GiB"),
    "RAM label must include percentage and used/total GiB")
assert(#network_graph.values == 0, "first sample from a new interface must be suppressed")

environment.net_now = { devices = { eth0 = { received = "2048", sent = "512" } } }
refresh()
assert(#network_graph.values == 2 and network_graph.values[1].value == 2048 and network_graph.values[1].group == 1
    and network_graph.values[2].value == 512 and network_graph.values[2].group == 2,
    "network graph must add received/down and sent/up as separate groups")
assert(network_graph.max_value >= 2560,
    "stacked network graph scale must include the combined retained download and upload peak")
assert(popup_has_text(monitors[3], "DL") and popup_has_text(monitors[3], "UL")
    and popup_has_text(monitors[3], "2.0 MiB/s") and popup_has_text(monitors[3], "512 KiB/s"),
    "network label must keep distinct formatted download and upload rates")
refresh()
assert(#network_graph.values == 2, "unchanged network table must not append duplicate history")

environment.cpu_now = { usage = 150 }
environment.mem_now = { perc = -20, used = 10, total = 1024 }
environment.net_now = { devices = { eth0 = { received = -2, sent = -3 } } }
refresh()
assert(cpu_graph.values[#cpu_graph.values].value == 100 and ram_graph.values[#ram_graph.values].value == 0,
    "CPU and RAM samples must be clamped to 0..100")
assert(network_graph.values[#network_graph.values - 1].value == 0 and network_graph.values[#network_graph.values].value == 0,
    "negative network rates must clamp to zero")
assert(network_graph.values[1].value == 2048 and network_graph.values[2].value == 512
    and network_graph.max_value >= 2560,
    "smaller samples must not clip the older stacked peak while it remains in history")
environment.mem_now = { perc = 50, used = 10, total = 0 }
environment.cpu_now = { usage = -20 }
refresh()
assert(cpu_graph.values[#cpu_graph.values].value == 0, "CPU samples must clamp at zero")
assert(popup_has_current_text(monitors[2], "—"), "invalid memory totals must render an em dash")
assert(not popup_has_text(monitors[2], "nan") and not popup_has_text(monitors[2], "inf"),
    "invalid memory totals must not produce non-finite labels")

environment.net_now = { devices = {
    eth0 = { received = "1024", sent = "256" }, eth1 = { received = "999999999", sent = "999999999" },
} }
refresh()
assert(network_graph.values[#network_graph.values - 1].value == 1024
    and network_graph.values[#network_graph.values].value == 256,
    "a newly added interface spike must be excluded from established totals")
environment.net_now = { devices = { eth1 = { received = "64", sent = "32" } } }
refresh()
environment.net_now = { devices = {
    eth0 = { received = "999999999", sent = "999999999" }, eth1 = { received = "128", sent = "64" },
} }
refresh()
assert(network_graph.values[#network_graph.values - 1].value == 128
    and network_graph.values[#network_graph.values].value == 64,
    "a reconnected interface must be primed again before its spike is used")
for _ = 1, network_graph.width do
    environment.net_now = { devices = { eth1 = { received = "1", sent = "2" } } }
    refresh()
end
assert(network_graph.max_value == 3 and #network_graph.values == network_graph.width * 2,
    "network scale must shrink after its bounded history expires an old peak")
local values_before_empty_devices = #network_graph.values
environment.net_now = { devices = {} }
refresh()
assert(#network_graph.values == values_before_empty_devices and popup_has_current_text(monitors[3], "DL —")
    and popup_has_current_text(monitors[3], "UL —"), "empty network devices must report unavailable traffic")
environment.net_now = { devices = { eth0 = { received = "999999999", sent = "999999999" } } }
refresh()
environment.net_now = { devices = { eth0 = { received = "32", sent = "16" } } }
refresh()
environment.net_now = nil
environment.cpu_now = { usage = math.huge }
environment.mem_now = { perc = 0 / 0, used = math.huge, total = 8192 }
local values_before_invalid_metrics = #network_graph.values
local maximum_before_invalid_metrics = network_graph.max_value
refresh()
assert(popup_has_current_text(monitors[1], "CPU —") and popup_has_current_text(monitors[2], "—")
    and popup_has_current_text(monitors[3], "DL —") and popup_has_current_text(monitors[3], "UL —"),
    "missing or non-finite metrics must replace stale labels with unavailable readings")
environment.net_now = { devices = { eth0 = { received = "999999999", sent = "999999999" } } }
refresh()
assert(#network_graph.values == values_before_invalid_metrics and network_graph.max_value == maximum_before_invalid_metrics,
    "network returning after a missing snapshot must prime its interfaces again")
for _, sample in ipairs(cpu_graph.values) do
    assert(sample.value >= 0 and sample.value <= 100, "CPU history must remain bounded")
end
for _, sample in ipairs(ram_graph.values) do
    assert(sample.value >= 0 and sample.value <= 100, "RAM history must remain bounded")
end
for _, sample in ipairs(network_graph.values) do assert_finite(sample.value, "network history must be finite") end

assert_in_workarea(monitors, test_screen.workarea)
test_screen.workarea = { x = 0, y = 0, width = 320, height = 400 }
test_screen:emit_signal("property::workarea", test_screen)
assert_in_workarea(monitors, test_screen.workarea)
monitors[1].height = 120
monitors[1]:emit_signal("property::height", monitors[1])
assert_in_workarea(monitors, test_screen.workarea)
test_screen.workarea = { x = 100, y = 50, width = 340, height = 400 }
test_screen:emit_signal("property::workarea", test_screen)
monitors[1].width = 300
monitors[1]:emit_signal("property::width", monitors[1])
assert_in_workarea(monitors, test_screen.workarea)

assert(pcall(function() test_screen:emit_signal("arrange", test_screen) end), "normal arrange must be safe")
test_screen.clients = { { fullscreen = true, isvisible = function() return true end } }
test_screen:emit_signal("arrange", test_screen)
for _, popup in ipairs(monitors) do assert(popup.visible == false, "fullscreen must hide every monitor") end
test_screen.clients = { { fullscreen = true, isvisible = function() return false end } }
test_screen:emit_signal("arrange", test_screen)
for _, popup in ipairs(monitors) do assert(popup.visible == true, "invisible fullscreen client must not hide monitors") end
test_screen.clients = {}
test_screen:emit_signal("arrange", test_screen)
for _, popup in ipairs(monitors) do assert(popup.visible == true, "normal windows must restore every monitor") end

test_screen:emit_signal("removed", test_screen)
assert(display_timer.stopped == true, "screen removal must stop its display timer")

local second_screen = object({
    clients = {}, geometry = { x = 1920, y = 0, width = 800, height = 600 },
    workarea = { x = 1920, y = 0, width = 800, height = 600 },
})
theme.at_screen_connect(second_screen)
assert(shared_widget_calls == 1, "shared status widgets must not be rebuilt for another screen")
assert(extra_lain_samplers == 0, "desktop cards must reuse shared poller globals, not create lain samplers")
print("tide chrome and monitor tests passed")

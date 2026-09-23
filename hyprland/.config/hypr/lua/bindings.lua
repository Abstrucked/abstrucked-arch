-- Keybindings mirror ~/.config/awesome/rc.lua. Awesome is the blueprint: keys
-- must stay identical, only the action behind them is adapted to Hyprland.
-- Keep bindings.conf (legacy syntax) in step with this file.
--
-- Hyprland's Lua config has no legacy `hyprctl dispatch <name>`; scripts call
-- `hyprctl eval` with hl.dsp.* instead.

local mainMod = "SUPER"
local altMod = "ALT"
local terminal = "alacritty"
local layout_switcher = os.getenv("HOME") .. "/.local/bin/hypr-layout"
local monocle_cycler = os.getenv("HOME") .. "/.local/bin/hypr-monocle-cycle"

local function exec(keys, command, opts)
    hl.bind(keys, hl.dsp.exec_cmd(command), opts)
end

-- Screenshots, lock, and session menu.
exec(altMod .. " + P", "screenshot_1")
exec(altMod .. " + SHIFT + P", "screenshot_2")
-- Awesome's Alt+Ctrl+@ is Alt+Ctrl+Shift+2 on a US layout.
exec(altMod .. " + CTRL + SHIFT + 2", "pidof hyprlock || hyprlock")
exec(altMod .. " + CTRL + L", "hypr-power-menu session")

-- Help and tag browsing. Hyprland workspaces are global and fixed, so tags 1-9
-- map to workspaces 1-9.
exec(mainMod .. " + S", "hypr-keybinds")
exec(mainMod .. " + left", "hypr-workspace view previous")
exec(mainMod .. " + right", "hypr-workspace view next")
hl.bind(mainMod .. " + ESCAPE", hl.dsp.focus({ workspace = "previous" }))
exec(mainMod .. " + grave", "GTK_THEME=Adwaita:dark pcmanfm")
exec(mainMod .. " + SHIFT + grave", "pcmanfm")

-- Non-empty tag browsing (lain.util.tag_view_nonempty).
exec(altMod .. " + left", "hypr-workspace nonempty previous")
exec(altMod .. " + right", "hypr-workspace nonempty next")

-- Client focus by index and by direction.
exec(altMod .. " + J", monocle_cycler .. " next")
exec(altMod .. " + K", monocle_cycler .. " previous")
hl.bind(mainMod .. " + H", hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "down" }))
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }))
exec(mainMod .. " + W", "hypr-launcher combi")

-- Layout manipulation.
hl.bind(mainMod .. " + SHIFT + J", hl.dsp.window.swap({ next = true }))
hl.bind(mainMod .. " + SHIFT + K", hl.dsp.window.swap({ prev = true }))
hl.bind(mainMod .. " + CTRL + J", hl.dsp.focus({ monitor = "+1" }))
hl.bind(mainMod .. " + CTRL + K", hl.dsp.focus({ monitor = "-1" }))
-- Hotplug re-applies on its own (monitors.lua); this is the manual fallback.
exec(mainMod .. " + P", "display-detect apply")
hl.bind(mainMod .. " + U", hl.dsp.focus({ urgent_or_last = true }))
hl.bind(mainMod .. " + TAB", hl.dsp.focus({ last = true }))
hl.bind(mainMod .. " + SHIFT + TAB", hl.dsp.window.cycle_next({ next = true }))

-- Wibox toggle.
exec(mainMod .. " + B", "pkill -SIGUSR1 waybar")

-- Useless gaps (Alt+Ctrl+plus/minus; plus is Shift+equal, keypad also works).
exec(altMod .. " + CTRL + SHIFT + equal", "hypr-gaps +1")
exec(altMod .. " + CTRL + KP_ADD", "hypr-gaps +1")
exec(altMod .. " + CTRL + minus", "hypr-gaps -1")
exec(altMod .. " + CTRL + KP_SUBTRACT", "hypr-gaps -1")

-- Dynamic tagging. Special workspaces and swapping neighbours are the closest
-- Hyprland equivalents.
hl.bind(mainMod .. " + SHIFT + N", hl.dsp.workspace.toggle_special("dynamic"))
exec(mainMod .. " + SHIFT + R", "hypr-workspace rename")
exec(mainMod .. " + SHIFT + left", "hypr-workspace move previous")
exec(mainMod .. " + SHIFT + right", "hypr-workspace move next")
hl.bind(mainMod .. " + SHIFT + D", hl.dsp.workspace.toggle_special("dynamic"))

-- Standard programs, awesome reload/quit.
exec(mainMod .. " + RETURN", terminal)
exec(mainMod .. " + CTRL + R", "hyprctl reload")
hl.bind(mainMod .. " + SHIFT + Q", hl.dsp.exit())

-- Master/column layout tweaks.
hl.bind(altMod .. " + SHIFT + L", hl.dsp.layout("mfact +0.05"))
hl.bind(altMod .. " + SHIFT + H", hl.dsp.layout("mfact -0.05"))
hl.bind(mainMod .. " + SHIFT + H", hl.dsp.layout("addmaster"))
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.layout("removemaster"))
hl.bind(mainMod .. " + CTRL + H", hl.dsp.layout("orientationleft"))
hl.bind(mainMod .. " + CTRL + L", hl.dsp.layout("orientationright"))
exec(mainMod .. " + SPACE", layout_switcher .. " next")
exec(mainMod .. " + SHIFT + SPACE", layout_switcher .. " previous")

-- Restore minimized client, dropdown terminal.
exec(mainMod .. " + CTRL + N", "hypr-minimize restore")
hl.bind(mainMod .. " + Z", hl.dsp.workspace.toggle_special("quake"))

-- Widget popups and yubico.
exec(altMod .. " + C", "swaync-client -t")
exec(altMod .. " + H", "hypr-filesystem")
exec(altMod .. " + Y", "hypr-yubico")

-- Brightness, volume, and media keys. Hold-to-repeat for levels, and they keep
-- working on the lock screen.
local held = { locked = true, repeating = true }
local locked = { locked = true }
exec("XF86MonBrightnessUp", "brightnessctl set 10%+", held)
exec("XF86MonBrightnessDown", "brightnessctl set 10%-", held)
exec("XF86KbdBrightnessUp", "brightnessctl --device='*::kbd_backlight' set 10%+", held)
exec("XF86KbdBrightnessDown", "brightnessctl --device='*::kbd_backlight' set 10%-", held)
exec("XF86AudioLowerVolume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%-", held)
exec("XF86AudioRaiseVolume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+", held)
exec("XF86AudioMute", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle", locked)
exec("XF86AudioPlay", "playerctl play-pause", locked)
exec(altMod .. " + " .. mainMod .. " + down", "playerctl stop", locked)
exec("XF86AudioPrev", "playerctl previous", locked)
exec("XF86AudioNext", "playerctl next", locked)

-- Wayland equivalents of the xsel primary/clipboard bridges.
exec(mainMod .. " + C", "wl-paste --primary | wl-copy")
exec(mainMod .. " + V", "wl-paste | wl-copy --primary")

-- User programs and launchers.
exec(mainMod .. " + Q", "brave")
exec(mainMod .. " + D", "discord")
exec(mainMod .. " + A", "hypr-editor")
exec(mainMod .. " + SHIFT + W", terminal .. " -e nvim")
exec(mainMod .. " + X", "hypr-launcher run")
exec(mainMod .. " + R", "hypr-launcher run")
exec(mainMod .. " + SHIFT + B", "hypr-power-menu modes")
exec(mainMod .. " + SHIFT + O", "hypr-opacity toggle")

-- Client keys.
exec(altMod .. " + SHIFT + M", "hypr-magnify")
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen({ action = "toggle" }))
hl.bind(mainMod .. " + SHIFT + C", hl.dsp.window.close())
hl.bind(mainMod .. " + CTRL + SPACE", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + CTRL + RETURN", hl.dsp.layout("swapwithmaster"))
hl.bind(mainMod .. " + O", hl.dsp.window.move({ monitor = "+1" }))
hl.bind(mainMod .. " + T", hl.dsp.window.pin({ action = "toggle" }))
exec(mainMod .. " + N", "hypr-minimize")
hl.bind(mainMod .. " + M", hl.dsp.window.fullscreen({ action = "toggle", mode = "maximized" }))

-- Tags 1-9: view, toggle (approximated as view), move, move and follow.
for i = 1, 9 do
    local key = tostring(i)
    hl.bind(mainMod .. " + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + CTRL + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = false }))
    hl.bind(mainMod .. " + CTRL + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = true }))
end

-- Mouse: mod-drag to move, mod-right-drag to resize.
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

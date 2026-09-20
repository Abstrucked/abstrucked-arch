local mainMod = "SUPER"
local terminal = "alacritty"
local layout_switcher = os.getenv("HOME") .. "/.local/bin/hypr-layout"
local monocle_cycler = os.getenv("HOME") .. "/.local/bin/hypr-monocle-cycle"

local function exec(keys, command)
    hl.bind(keys, hl.dsp.exec_cmd(command))
end

-- Screenshots and session controls.
exec("ALT + P", "screenshot_1")
exec("ALT + SHIFT + P", "screenshot_2")
exec("ALT + CTRL + at", "hyprlock")
exec("ALT + CTRL + L", "hypr-power-menu session")

-- Help, workspace navigation, and file manager.
exec(mainMod .. " + S", "hypr-keybinds")
hl.bind(mainMod .. " + left", hl.dsp.focus({ workspace = "-1" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ workspace = "+1" }))
exec(mainMod .. " + ESCAPE", "hyprctl dispatch workspace previous")
exec(mainMod .. " + grave", "GTK_THEME=Adwaita:dark pcmanfm")
exec(mainMod .. " + SHIFT + grave", "pcmanfm")
hl.bind("ALT + " .. mainMod .. " + left", hl.dsp.focus({ workspace = "e-1" }))
hl.bind("ALT + " .. mainMod .. " + right", hl.dsp.focus({ workspace = "e+1" }))

-- Focus and movement. cyclenext is the closest equivalent to Awesome's
-- client-index bindings.
exec("ALT + J", monocle_cycler .. " next")
exec("ALT + K", monocle_cycler .. " previous")
hl.bind(mainMod .. " + H", hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + J", hl.dsp.focus({ direction = "down" }))
hl.bind(mainMod .. " + K", hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + L", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + J", hl.dsp.window.swap({ direction = "down" }))
hl.bind(mainMod .. " + SHIFT + K", hl.dsp.window.swap({ direction = "up" }))
hl.bind(mainMod .. " + CTRL + J", hl.dsp.focus({ monitor = "+1" }))
hl.bind(mainMod .. " + CTRL + K", hl.dsp.focus({ monitor = "-1" }))
hl.bind(mainMod .. " + U", hl.dsp.focus({ urgent_or_last = true }))
exec(mainMod .. " + TAB", "hyprctl dispatch focuscurrentorlast")
exec(mainMod .. " + SHIFT + TAB", "hyprctl dispatch cyclenext")

-- Bar and launcher controls.
exec(mainMod .. " + B", "pkill -SIGUSR1 waybar")
exec(mainMod .. " + W", "hypr-launcher combi")
exec(mainMod .. " + X", "hypr-launcher run")
exec(mainMod .. " + R", "hypr-launcher run")

-- Gap and layout controls.
exec("ALT + CTRL + SHIFT + equal", "hypr-gaps +1")
exec("ALT + CTRL + KP_ADD", "hypr-gaps +1")
exec("ALT + CTRL + minus", "hypr-gaps -1")
exec("ALT + CTRL + KP_SUBTRACT", "hypr-gaps -1")
hl.bind("ALT + SHIFT + H", hl.dsp.layout("mfact -0.05"))
hl.bind("ALT + SHIFT + L", hl.dsp.layout("mfact +0.05"))
hl.bind(mainMod .. " + SHIFT + H", hl.dsp.layout("addmaster"))
hl.bind(mainMod .. " + SHIFT + L", hl.dsp.layout("removemaster"))
hl.bind(mainMod .. " + CTRL + H", hl.dsp.layout("orientationleft"))
hl.bind(mainMod .. " + CTRL + L", hl.dsp.layout("orientationright"))
exec(mainMod .. " + SPACE", layout_switcher .. " next")
exec(mainMod .. " + SHIFT + SPACE", layout_switcher .. " previous")

-- Special workspaces are the closest practical replacement for dynamic tags.
hl.bind(mainMod .. " + SHIFT + N", hl.dsp.workspace.toggle_special("dynamic"))
exec(mainMod .. " + SHIFT + R", "hypr-workspace rename")
hl.bind(mainMod .. " + SHIFT + left", hl.dsp.workspace.move({ monitor = "-1" }))
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.workspace.move({ monitor = "+1" }))
hl.bind(mainMod .. " + SHIFT + D", hl.dsp.workspace.toggle_special("dynamic"))

-- Applications.
exec(mainMod .. " + RETURN", terminal)
exec(mainMod .. " + CTRL + R", "hyprctl reload")
hl.bind(mainMod .. " + SHIFT + C", hl.dsp.window.close())
exec(mainMod .. " + Q", "brave")
exec(mainMod .. " + D", "discord")
exec(mainMod .. " + A", "hypr-editor")
exec(mainMod .. " + SHIFT + W", terminal .. " -e nvim")
hl.bind(mainMod .. " + Z", hl.dsp.workspace.toggle_special("quake"))
exec(mainMod .. " + SHIFT + B", "hypr-power-menu modes")

-- Small system popups and Wayland clipboard equivalents.
exec("ALT + C", "swaync-client -t")
exec("ALT + H", "hypr-filesystem")
exec("ALT + Y", "hypr-launcher drun")
exec(mainMod .. " + C", "wl-paste --primary | wl-copy")
exec(mainMod .. " + V", "wl-paste | wl-copy --primary")

-- Client actions.
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen({ action = "toggle" }))
hl.bind(mainMod .. " + CTRL + SPACE", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + CTRL + RETURN", hl.dsp.layout("swapwithmaster"))
hl.bind(mainMod .. " + O", hl.dsp.window.move({ monitor = "+1" }))
hl.bind(mainMod .. " + T", hl.dsp.window.pin({ action = "toggle" }))
exec(mainMod .. " + N", "hypr-minimize")
hl.bind(mainMod .. " + M", hl.dsp.window.fullscreen({ action = "toggle", mode = "maximized" }))
hl.bind(mainMod .. " + CTRL + N", hl.dsp.workspace.toggle_special("minimized"))

-- Volume, brightness, and media keys.
exec("XF86MonBrightnessUp", "brightnessctl set 10%+")
exec("XF86MonBrightnessDown", "brightnessctl set 10%-")
exec("XF86KbdBrightnessUp", "brightnessctl --device='*::kbd_backlight' set 10%+")
exec("XF86KbdBrightnessDown", "brightnessctl --device='*::kbd_backlight' set 10%-")
exec("XF86AudioLowerVolume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%-")
exec("XF86AudioRaiseVolume", "wpctl set-volume @DEFAULT_AUDIO_SINK@ 2%+")
exec("XF86AudioMute", "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle")
exec("XF86AudioPlay", "playerctl play-pause")
exec("ALT + " .. mainMod .. " + down", "playerctl stop")
exec("XF86AudioPrev", "playerctl previous")
exec("XF86AudioNext", "playerctl next")

-- Workspaces 1 through 9. The Ctrl-number chords retain the old shape while
-- using Hyprland's fixed workspace model.
for i = 1, 9 do
    local key = tostring(i)
    hl.bind(mainMod .. " + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + CTRL + " .. key, hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = false }))
    hl.bind(mainMod .. " + CTRL + SHIFT + " .. key, hl.dsp.window.move({ workspace = i, follow = true }))
end

-- Mouse equivalents for Awesome's mod-drag behavior.
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(), { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

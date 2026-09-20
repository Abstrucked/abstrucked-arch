-- Keep toolkit behavior predictable for native Wayland and XWayland clients.
local home = os.getenv("HOME")
local path = os.getenv("PATH") or ""

if home then
    local local_bin = home .. "/.local/bin"
    if not path:find(local_bin, 1, true) then
        hl.env("PATH", local_bin .. ":" .. path)
    end
end

hl.env("XCURSOR_SIZE", "24")
hl.env("GDK_BACKEND", "wayland,x11")
hl.env("GTK_USE_PORTAL", "1")
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("QT_QPA_PLATFORM", "wayland;xcb")
hl.env("QT_WAYLAND_DISABLE_WINDOWDECORATION", "1")
hl.env("SDL_VIDEODRIVER", "wayland")
hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")
hl.env("XDG_CURRENT_DESKTOP", "Hyprland")
hl.env("XDG_SESSION_DESKTOP", "Hyprland")

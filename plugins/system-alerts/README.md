# system-alerts

Desktop notifications for disk and memory pressure. Starts
`os-assistant --watch-alerts` with the session (Awesome and Hyprland); the
watcher holds a lock, so restarts and reloads never run two. Popups are
styled by the Awesome theme's naughty mapping (critical stays until
dismissed, normal lasts 15 s, low 8 s) and by swaync under Hyprland.

    pluginctl enable system-alerts

Thresholds live in `~/.config/os-assistant/config.toml` under `[alerts]`.
Check the current levels with `os-assistant --check-alerts`.

{
    "layer": "top",
    "position": "top",
    "height": 24,
    "spacing": 0,
    "modules-left": [
        "hyprland/workspaces",
        "hyprland/window"
    ],
    "modules-center": [
        "clock"
    ],
    "modules-right": [
        "tray",
        "custom/notification",
        "pulseaudio",
        "memory",
        "cpu",
        "disk",
        "battery",
        "network",
        "custom/power"%%PLUGIN_MODULES%%
    ],
    "hyprland/workspaces": {
        "disable-scroll": true,
        "all-outputs": false,
        "format": "{name}",
        "persistent-workspaces": {
            "*": [1, 2, 3, 4, 5, 6, 7, 8, 9]
        }
    },
    "hyprland/window": {
        "format": "{}",
        "max-length": 80,
        "separate-outputs": true,
        "rewrite": {
            "(.*) [-—] Brave": "$1",
            "(.*) [-—] Discord": "$1"
        }
    },
    "clock": {
        "format": "{:%H:%M}",
        "tooltip-format": "<span font_family='JetBrains Mono Nerd Font'>{calendar}</span>",
        "calendar": {
            "mode": "month",
            "mode-mon-col": 3,
            "weeks-pos": "right",
            "on-scroll": 1,
            "on-click-right": "mode",
            "format": {
                "months": "<span color='{{accent}}'><b>{}</b></span>",
                "weekdays": "<span color='{{accent_alt}}'><b>{}</b></span>",
                "weeks": "<span color='{{ansi.bright.black}}'>{}</span>",
                "days": "<span color='{{fg}}'>{}</span>",
                "today": "<span color='{{bg}}' bgcolor='{{accent}}'><b>{}</b></span>"
            }
        }
    },
    "tray": {
        "icon-size": 16,
        "spacing": 6
    },
    "custom/notification": {
        "tooltip": false,
        "format": "{icon} {text}",
        "format-icons": {
            "none": "",
            "notification": "",
            "dnd-none": "",
            "dnd-notification": "",
            "inhibited-none": "",
            "inhibited-notification": ""
        },
        "return-type": "json",
        "exec": "swaync-client -swb",
        "on-click": "swaync-client -t -sw",
        "on-click-right": "swaync-client -d -sw",
        "restart-interval": 2
    },
    "pulseaudio": {
        "format": "󰕾 {volume}%",
        "format-muted": "󰖁",
        "format-bluetooth": "󰂯 {volume}%",
        "scroll-step": 2,
        "on-click": "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
        "on-click-right": "pavucontrol"
    },
    "memory": {
        "format": "󰍛 {used:0.1f}G",
        "states": {
            "warning": 70,
            "critical": 90
        }
    },
    "cpu": {
        "format": "󰻠 {usage}%",
        "states": {
            "warning": 70,
            "critical": 90
        }
    },
    "disk": {
        "path": "/",
        "format": "󰋊 {percentage_used}%",
        "states": {
            "warning": 80,
            "critical": 90
        },
        "tooltip-format": "{used} used of {total} on /"
    },
    "battery": {
        "states": {
            "warning": 30,
            "critical": 15
        },
        "format": "󰁹 {capacity}%",
        "format-charging": "󰂄 {capacity}%",
        "format-plugged": "󰂄 {capacity}%",
        "tooltip-format": "{time} remaining"
    },
    "network": {
        "format-wifi": "󰤨 {essid}",
        "format-ethernet": "󰈀 {ifname}",
        "format-disconnected": "󰤭",
        "tooltip-format": "{ifname}: {ipaddr}/{cidr}"
    },
    "custom/power": {
        "format": "",
        "tooltip": false,
        "on-click": "hypr-power-menu"
    }%%PLUGIN_DEFS%%
}

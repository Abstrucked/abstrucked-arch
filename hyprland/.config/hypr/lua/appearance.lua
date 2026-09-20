hl.config({
    general = {
        gaps_in = 4,
        gaps_out = 4,
        border_size = 0,
        col = {
            active_border = "rgba(fab387ff)",
            inactive_border = "rgba(89dcebff)",
        },
        layout = "dwindle",
        allow_tearing = false,
    },
    decoration = {
        rounding = 8,
        active_opacity = 1.0,
        inactive_opacity = 1.0,
        shadow = {
            enabled = false,
        },
        blur = {
            enabled = true,
            size = 3,
            passes = 2,
        },
    },
    animations = {
        enabled = true,
    },
    dwindle = {
        preserve_split = true,
        smart_split = true,
        smart_resizing = true,
    },
    master = {
        new_status = "master",
        mfact = 0.50,
    },
    misc = {
        disable_hyprland_logo = true,
        disable_splash_rendering = true,
        focus_on_activate = true,
    },
    xwayland = {
        force_zero_scaling = true,
    },
})

hl.curve("easeOut", {
    type = "bezier",
    points = {{0.05, 0.9}, {0.1, 1.05}},
})

hl.animation({ leaf = "windows", enabled = true, speed = 4, bezier = "easeOut" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 4, bezier = "easeOut", style = "popin 80%" })
hl.animation({ leaf = "border", enabled = true, speed = 4, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 4, bezier = "default" })
hl.animation({ leaf = "workspaces", enabled = false, speed = 4, bezier = "easeOut" })

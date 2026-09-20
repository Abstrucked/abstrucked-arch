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
        -- picom's active-opacity and inactive-opacity in the AwesomeWM
        -- session. Toggle at runtime with hypr-opacity.
        active_opacity = 0.95,
        inactive_opacity = 0.75,
        fullscreen_opacity = 1.0,
        shadow = {
            enabled = false,
        },
        blur = {
            enabled = false,
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

-- Linear, to match picom's constant opacity step per fade-delta tick in the
-- AwesomeWM session.
hl.curve("picomFade", {
    type = "bezier",
    points = {{0, 0}, {1, 1}},
})

hl.animation({ leaf = "windows", enabled = true, speed = 4, bezier = "easeOut" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 4, bezier = "easeOut", style = "popin 80%" })
hl.animation({ leaf = "border", enabled = true, speed = 4, bezier = "default" })
hl.animation({ leaf = "fade", enabled = true, speed = 4, bezier = "default" })
-- Workspace switching crossfades like picom does on tag switch. Speeds are
-- picom's fade-in-step 0.028 and fade-out-step 0.03 at fade-delta 10ms, which
-- come to 360ms in and 340ms out.
hl.animation({ leaf = "workspaces", enabled = true, speed = 3.6, bezier = "picomFade", style = "fade" })
hl.animation({ leaf = "workspacesOut", enabled = true, speed = 3.4, bezier = "picomFade", style = "fade" })

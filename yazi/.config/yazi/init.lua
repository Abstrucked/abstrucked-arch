-- Plugins are declared in package.toml; `ya pkg install` fetches them.

require("full-border"):setup {
	type = ui.Border.ROUNDED,
}

require("git"):setup {
	-- Order of the status signs in the linemode
	order = 1500,
}

-- Record every directory visited in zoxide's database, so the built-in `Z`
-- jump learns from browsing in Yazi too.
require("zoxide"):setup {
	update_db = true,
}

-- Colours below are ANSI names, never hex: the terminal maps them to the
-- palette themectl renders, so they follow palette switches.

-- user@host before the path in the header.
Header:children_add(function()
	if ya.target_family() ~= "unix" then
		return ""
	end
	return ui.Span(ya.user_name() .. "@" .. ya.host_name() .. ":"):fg("blue")
end, 500, Header.LEFT)

-- owner:group in the status bar, before the permissions.
Status:children_add(function()
	local h = cx.active.current.hovered
	if not h or ya.target_family() ~= "unix" then
		return ""
	end

	return ui.Line {
		ui.Span(ya.user_name(h.cha.uid) or tostring(h.cha.uid)):fg("magenta"),
		":",
		ui.Span(ya.group_name(h.cha.gid) or tostring(h.cha.gid)):fg("magenta"),
		" ",
	}
end, 500, Status.RIGHT)

-- Default linemode (yazi.toml): size, then the modified time. Today's files
-- show the time of day, everything else the date, e.g. "31K  Oct 13".
-- git.yazi's signs are added after this through Linemode:children_add.
function Linemode:size_mtime()
	local time = math.floor(self._file.cha.mtime or 0)
	if time == 0 then
		time = ""
	elseif os.date("%Y-%m-%d", time) == os.date("%Y-%m-%d") then
		time = os.date("%H:%M", time)
	elseif os.date("%Y", time) == os.date("%Y") then
		time = os.date("%b %d", time)
	else
		time = os.date("%b %d  %Y", time)
	end

	local size = self._file:size()
	return ui.Line {
		ui.Span(size and ya.readable_size(size) or "-"):fg("cyan"),
		ui.Span("  " .. time):fg("blue"),
	}
end

-- Powerlevel10k-style git header.
require("githead"):setup {
	show_numbers = true,
	branch_prefix = "on",
	branch_symbol = " ",
	branch_borders = "()",
	branch_color = "blue",
	remote_branch_color = "bright magenta",
	tag_color = "magenta",
	commit_color = "bright magenta",
	behind_remote_color = "bright magenta",
	ahead_remote_color = "bright magenta",
	stashes_color = "bright magenta",
	state_color = "red",
	staged_color = "green",
	unstaged_color = "yellow",
	untracked_color = "cyan",
}

-- Relative line numbers (with the absolute number on the hovered row).
require("relative-motions"):setup {
	show_numbers = "relative_absolute",
	show_motion = true,
}

require("duckdb"):setup()

require("mediainfo"):setup()

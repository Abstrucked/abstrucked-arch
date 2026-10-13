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

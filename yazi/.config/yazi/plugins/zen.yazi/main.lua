--- @since 26.8.15
--- @sync entry

-- zen.yazi: toggle a distraction-free layout. Bind with `plugin zen`; there is
-- no setup call and no argument.
--
-- Zen hides the parent column, widens the preview (current:preview becomes
-- about 3:5 at the default ratio), gives the status bar's row to the file list
-- and skips the frame full-border.yazi draws. The header is left alone.
--
-- The layout functions are wrapped once, on the first toggle, and delegate to
-- whatever was installed before (full-border's Tab.build, for one) while Zen
-- is off, so Normal is untouched. The state lives in this module's upvalues,
-- which is enough for one session; the sync entry shares them with rendering.

local active = false
local installed = false

local function wrap_root()
	local old_layout, old_build = Root.layout, Root.build

	Root.layout = function(self, ...)
		if not active then
			return old_layout(self, ...)
		end
		-- Same split as Root:layout, with no row for the status bar.
		self._chunks = ui.Layout()
			:direction(ui.Layout.VERTICAL)
			:constraints({
				ui.Constraint.Length(1),
				ui.Constraint.Length(Tabs.height()),
				ui.Constraint.Fill(1),
				ui.Constraint.Length(0),
			})
			:split(self._area)
	end

	Root.build = function(self, ...)
		old_build(self, ...)
		if not active then
			return
		end
		local children = {}
		for _, child in ipairs(self._children) do
			if child._id ~= "status" then
				children[#children + 1] = child
			end
		end
		self._children = children
	end
end

local function wrap_tab()
	local old_layout, old_build = Tab.layout, Tab.build

	Tab.layout = function(self, ...)
		if not active then
			return old_layout(self, ...)
		end
		-- Scale current:preview by 4:5 so the default 3:4 becomes 3:5, while
		-- toggle-pane's min/max values (written to rt.mgr.ratio) still apply.
		local r = rt.mgr.ratio
		local cur, pre = r[2] * 4, r[3] * 5
		local all = math.max(cur + pre, 1)
		self._chunks = ui.Layout()
			:direction(ui.Layout.HORIZONTAL)
			:constraints({
				ui.Constraint.Length(0),
				ui.Constraint.Ratio(cur, all),
				ui.Constraint.Ratio(pre, all),
			})
			:split(self._area)
	end

	-- Zen builds the children itself (Tab:build of Yazi 26.9.1, without any
	-- padding): the wrapped build may be full-border's, which pads the chunks
	-- and adds the frame before delegating, and that cannot be undone.
	Tab.build = function(self, ...)
		if not active then
			return old_build(self, ...)
		end
		local c = self._chunks
		local p = c[2].w > 0 and 0 or 1
		self._children = {
			Parent:new(c[1]:pad(ui.Pad(0, p, 0, 1)), self._tab),
			Current:new(c[2]:pad(ui.Pad.x(1)), self._tab),
			Preview:new(c[3]:pad(ui.Pad(0, 1, 0, p)), self._tab),
			Rails:new(c, self._tab),
			Markers:new(c, self._tab),
		}
	end
end

local function entry()
	if not installed then
		wrap_root()
		wrap_tab()
		installed = true
	end
	active = not active
	ya.emit("app:resize", {})
end

return { entry = entry }

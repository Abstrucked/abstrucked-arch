-- ~/.config/nvim/lua/utils/terminal.lua
local M = {}

function M.toggle_terminal(id, opts)
  local float = { position = "float" }
  local right = { position = "right", size = 40 }
  local bottom = { position = "bottom", size = 15 }
  if id == 1 then
    Snacks.terminal.toggle(
      nil,
      vim.tbl_deep_extend("force", {
        env = { TERM_ID = tostring(id) },
        win = float,
      }, opts or {})
    )
  end

  if id == 2 then
    Snacks.terminal.toggle(
      nil,
      vim.tbl_deep_extend("force", {
        env = { TERM_ID = tostring(id) },
        win = right,
      }, opts or {})
    )
  end
end

return M

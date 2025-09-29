-- Keymaps are automatically loaded on the VeryLazy event
-- Default keymaps that are always set: https://github.com/LazyVim/LazyVim/blob/main/lua/lazyvim/config/keymaps.lua
-- Add any additional keymaps here
local map = LazyVim.safe_keymap_set

-- floating terminal
map("n", "<leader>1", function()
  Snacks.terminal(nil, { win = { position = "float" }, env = { TERM_ID = "1" } })
end, { desc = "Terminal (float)" })
map("t", "<leader>1", function()
  Snacks.terminal.toggle(nil, { position = "float", env = { TERM_ID = "1" } })
end)

-- floating terminal
map("n", "<leader>2", function()
  Snacks.terminal(nil, { win = { position = "right" }, env = { TERM_ID = "2" } })
end, { desc = "Terminal (right)" })
map("t", "<leader>2", function()
  Snacks.terminal.toggle(nil, { position = "right", env = { TERM_ID = "2" } })
end)

local tokyo_night = {
  "folke/tokyonight.nvim",
  lazy = false,
  priority = 1000,
  opts = {},
}

local nightfly = { "bluz71/vim-nightfly-colors", name = "nightfly", lazy = false, priority = 1000 }

return {
  tokyo_night,
  nightfly,
}

return {
  "allaman/emoji.nvim",
  version = "1.0.0",
  dependencies = {
    "nvim-lua/plenary.nvim",
    "hrsh7th/nvim-cmp", -- for cmp emoji completion
    "nvim-telescope/telescope.nvim",
  },
  opts = {
    enable_cmp_integration = true,
  },
  config = function(_, opts)
    require("emoji").setup(opts)

    -- ✅ Ensure telescope is loaded and extension added *right now*
    local has_telescope, telescope = pcall(require, "telescope")
    if has_telescope then
      telescope.load_extension("emoji")
    end

    -- ⌨️ Bind the emoji picker to <leader>se
    vim.keymap.set("n", "<leader>se", function()
      require("telescope").extensions.emoji.emoji()
    end, { desc = "[S]earch [E]moji" })
  end,
}

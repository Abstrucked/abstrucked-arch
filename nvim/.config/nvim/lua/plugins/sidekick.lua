return {
  {
    "folke/sidekick.nvim",
    optional = true,
    opts = {
      cli = {
        tools = {
          opencode = {
            -- Load keys from pass and start a server that inherits them,
            -- including when Neovim was started without nvim-launcher.
            cmd = { vim.fn.expand("~/.local/bin/opencode-launcher") },
          },
        },
      },
    },
  },
}

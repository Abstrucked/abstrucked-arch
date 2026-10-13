return {
  "ravitemer/mcphub.nvim",
  dependencies = {
    "nvim-lua/plenary.nvim", -- Required for Job and HTTP requests
  },
  lazy = true,
  cmd = { "MCPHub" },
  -- Keep the executable in Neovim's data directory instead of installing globally.
  -- Bump this pinned version deliberately after verifying a release.
  build = 'npm install --prefix "$HOME/.local/share/nvim/mcphub" mcp-hub@4.2.1',
  config = function()
    -- Upstream defaults auto_approve to false; enabling it can approve MCP tool
    -- calls that execute commands, access files, or use the network. Opt in only
    -- explicitly with MCPHUB_AUTO_APPROVE=1 or MCPHUB_AUTO_APPROVE=true.
    local auto_approve = vim.env.MCPHUB_AUTO_APPROVE
    require("mcphub").setup({
      -- Required options
      port = 3784, -- Port for MCP Hub server
      config = vim.fn.expand("~/mcpservers.json"), -- Absolute path to config file
      auto_approve = auto_approve == "1" or auto_approve == "true",
      cmd = vim.fn.expand("~/.local/share/nvim/mcphub/node_modules/.bin/mcp-hub"),
      extensions = {
        avante = {
          make_slash_commands = true, -- make /slash commands from MCP server prompts
        },
      },
      -- Optional options
      on_ready = function(hub)
        -- Called when hub is ready
      end,
      on_error = function(err)
        -- Called on errors
      end,
      shutdown_delay = 0, -- Wait 0ms before shutting down server after last client exits
      log = {
        level = vim.log.levels.WARN,
        to_file = false,
        file_path = nil,
        prefix = "MCPHub",
      },
    })
  end,
}

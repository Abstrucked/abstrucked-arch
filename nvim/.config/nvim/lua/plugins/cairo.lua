local opts = {
  settings = {
    cairo = {
      -- Cairo-specific LSP settings
      diagnostics = {
        enable = true,
        level = "error",
      },
    },
  },
  diagnostics = {
    virtual_text = false, -- Disable virtual text
    underline = true,
  },
}
-- devMode: true for local development or fals for production
local devMode = true

if devMode then
  return {
    {

      dir = "~/_dev/cairo.nvim",
      opts = opts,
    },
  }
else
  return {
    {
      "Abstrucked/cairo.nvim",
      opts = opts,
    },
  }
end

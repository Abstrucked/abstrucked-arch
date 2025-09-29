return {
  "nvim-treesitter/nvim-treesitter",
  opts = function(_, opts)
    opts.ensure_installed = opts.ensure_installed or {}
    -- If a maintained grammar exists, e.g. "cairo":
    -- table.insert(opts.ensure_installed, "cairo")
    return opts
  end,
}

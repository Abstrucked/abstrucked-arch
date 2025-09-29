return {
  "danymat/neogen",
  dev = true,
  dir = "~/_dev/neogen", -- Full path to your local clone
  config = function()
    require("neogen").setup({
      -- your config here
      languages = {
        solidity = require("neogen.configurations.solidity"),
      },
    })
  end,
}

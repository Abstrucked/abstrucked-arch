return {
  "danymat/neogen",
  config = function()
    require("neogen").setup({
      -- your config here
      languages = {
        solidity = require("neogen.configurations.solidity"),
      },
    })
  end,
}

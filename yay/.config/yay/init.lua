-- yay v13 init.lua. Scans every AUR package with aurscan before it is built.
-- Static rules only (AURSCAN_RULES_ONLY=1): nothing is sent to any model or
-- cloud service. Install with install/setup-aurscan.sh --apply.
-- The markers below match aurscan's own, so `aurscan --uninstall-yay-hook`
-- still recognises this block.
-- >>> aurscan begin (managed block; do not edit by hand)
-- aurscan: scan each AUR package (PKGBUILD + downloaded sources) before install.
yay.create_autocmd("AURPostDownload", {
  desc = "aurscan pre-build malware scan (rules only)",
  callback = function(event)
    local aurscan = "/usr/bin/aurscan"
    -- Lua 5.1 returns a number from os.execute, 5.2+ returns true/nil.
    local function succeeded(result) return result == 0 or result == true end
    local function shq(s) return "'" .. (tostring(s):gsub("'", "'\\''")) .. "'" end

    -- Fail closed: without the scanner nothing may be built.
    if not succeeded(os.execute("test -x " .. shq(aurscan))) then
      yay.abort("aurscan is not installed; run install/setup-aurscan.sh --apply or unstow the yay package")
      return
    end

    local cmd = "AURSCAN_RULES_ONLY=1 " .. aurscan .. " --prebuild " .. shq(event.data.dir)
    if not succeeded(os.execute(cmd)) then
      os.execute("notify-send -a os-assistant -u normal 'AUR scan blocked' " .. shq(event.match) .. " >/dev/null 2>&1")
      yay.abort(event.match .. ": blocked by aurscan")
    end
  end,
})
-- <<< aurscan end

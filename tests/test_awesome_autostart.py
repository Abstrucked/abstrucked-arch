#!/usr/bin/env python3
"""Regression coverage for Awesome's XDG autostart sentinel ordering."""

import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "awesome/.config/awesome/rc.lua"


def main():
    source = RC.read_text()
    match = re.search(r"awful\.spawn\.with_shell\(\[=\[(.*?)\]=\]\)", source, re.S)
    assert match, "could not find the XDG autostart shell block"
    script = match.group(1)
    assert "dex's default search order is $XDG_CONFIG_HOME first, then XDG_CONFIG_DIRS" in script
    assert "so user entries override or hide (Hidden=true) system ones." in script
    assert script.index("dex --environment Awesome --autostart") < script.index("xrdb -merge")

    with tempfile.TemporaryDirectory() as temporary:
        bindir = Path(temporary) / "bin"
        bindir.mkdir()
        merged = Path(temporary) / "merged"
        dex = bindir / "dex"
        dex.write_text("#!/bin/sh\nexit 23\n")
        dex.chmod(0o755)
        xrdb = bindir / "xrdb"
        xrdb.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -query ]; then exit 0; fi\n"
            f"cat >> {str(merged)!r}\n"
        )
        xrdb.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = f"{bindir}:{env['PATH']}"
        result = subprocess.run(["bash", "-c", script], env=env, check=False)
        assert result.returncode == 23, f"failed dex exit status was lost: {result.returncode}"
        assert not merged.exists() or "awesome.started:true" not in merged.read_text(), (
            "failed dex invocation must not publish the sentinel"
        )
    print("Awesome autostart sentinel tests passed")


if __name__ == "__main__":
    main()

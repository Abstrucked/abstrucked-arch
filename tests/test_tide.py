"""Headless regression coverage for Tide's desktop chrome and metric cards."""
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "awesome/.config/awesome/themes/tide/theme.lua"
TEST = ROOT / "tests/test_tide.lua"


def run_tide_test(theme):
    return subprocess.run(
        ["lua", str(TEST), str(theme)],
        capture_output=True,
        text=True,
        timeout=60,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
    )


def test_tide_has_no_dock_or_titlebars_and_retains_desktop_furniture():
    result = run_tide_test(THEME)
    assert result.returncode == 0, result.stderr
    assert "tide chrome and monitor tests passed" in result.stdout


def test_tide_chrome_test_rejects_reenabled_titlebars():
    original = THEME.read_text()
    disabled = "theme.titlebars_enabled = false"
    assert disabled in original, "update the fixture when titlebar configuration changes"
    temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="tide-regression-", dir=temp_root) as directory:
        changed_theme = Path(directory) / "theme.lua"
        changed_theme.write_text(original.replace(disabled, "theme.titlebars_enabled = true", 1))
        result = run_tide_test(changed_theme)
    assert result.returncode != 0
    assert "titlebars must be disabled" in result.stderr


def test_tide_chrome_test_rejects_reintroduced_dock_popup():
    original = THEME.read_text()
    anchor = "function theme.at_screen_connect(s)\n"
    assert original.count(anchor) == 1
    # Different quoting avoids the source guard, exercising the real screen
    # setup and recorded popup types rather than only matching its text.
    dock = "    awful.popup({ screen = s, type = 'dock' })\n"
    temp_root = "/tmp/opencode" if Path("/tmp/opencode").is_dir() else None
    with tempfile.TemporaryDirectory(prefix="tide-regression-", dir=temp_root) as directory:
        changed_theme = Path(directory) / "theme.lua"
        changed_theme.write_text(original.replace(anchor, anchor + dock, 1))
        result = run_tide_test(changed_theme)
    assert result.returncode != 0
    assert "screen setup must not create a dock popup" in result.stderr

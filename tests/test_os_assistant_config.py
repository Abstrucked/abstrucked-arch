"""Adversarial regression tests for os_assistant.config (Config / load_config).

Every filesystem touch is confined to pytest temporary directories. HOME and
XDG_CONFIG_HOME are mocked per test so no real user configuration is ever read
and no file outside the sandbox can influence a result. No network or model
calls are made.
"""

from dataclasses import FrozenInstanceError
import os
from pathlib import Path
import sys

import pytest

_PKG = Path(__file__).resolve().parents[1] / "os-assistant" / ".local" / "share" / "os-assistant"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from os_assistant.config import (
    ALLOWED_MODELS,
    DEFAULT_MODEL,
    Config,
    default_config_path,
    load_config,
    normalized_root,
)
from os_assistant.contracts import ConfigurationError


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Mock HOME/XDG so the real user configuration can never be consulted."""
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    home.mkdir()
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


def write_config(tmp_path, text, name="config.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Immutability and defaults
# ---------------------------------------------------------------------------

def test_config_is_frozen():
    cfg = Config()
    with pytest.raises(FrozenInstanceError):
        cfg.actions_enabled = True
    with pytest.raises(FrozenInstanceError):
        cfg.allowed_roots = ("/etc",)
    with pytest.raises(FrozenInstanceError):
        cfg.host = "http://evil.example:11434"
    with pytest.raises(FrozenInstanceError):
        cfg.bash_enabled = True
    with pytest.raises(FrozenInstanceError):
        cfg.bash_roots = ("/etc",)
    with pytest.raises(FrozenInstanceError):
        cfg.bash_allow_writes = True


def test_config_defaults_grant_no_access():
    cfg = Config()
    assert cfg.allowed_roots == ()
    assert cfg.actions_enabled is False
    assert cfg.apps == ()
    assert cfg.themes_enabled is False
    assert cfg.bash_enabled is False
    assert cfg.bash_roots == ()
    assert cfg.bash_allow_writes is False
    assert cfg.usage_entries == 100000
    assert cfg.usage_seconds == 10
    assert cfg.usage_depth == 64


def test_config_defaults_are_sane():
    cfg = Config()
    assert cfg.model == DEFAULT_MODEL
    assert cfg.host == "http://127.0.0.1:11434"
    assert 2048 <= cfg.context <= 16384
    assert 5 <= cfg.model_timeout <= 300
    assert cfg.max_output_tokens == 768
    assert 1 <= cfg.max_steps <= 10
    assert 1 <= cfg.tool_timeout <= 30
    assert 1 <= cfg.scan_entries <= 10000
    assert 1 <= cfg.scan_seconds <= 10
    assert 1 <= cfg.scan_depth <= 16
    assert cfg.usage_entries == 100000
    assert cfg.usage_seconds == 10
    assert cfg.usage_depth == 64


@pytest.mark.parametrize("value", ["true", "1", '"desktop_status"', '["unknown"]', '["desktop_status", "desktop_status"]', '[false]'])
def test_status_allowlist_types_and_values_are_strict(tmp_path, value):
    path = write_config(tmp_path, f"[status]\nenabled = {value}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_status_allowlist_can_be_empty_without_enabling_actions_or_roots(tmp_path):
    config = load_config(write_config(tmp_path, "[status]\nenabled = []\n"))
    assert config.status_enabled == () and not config.actions_enabled and not config.allowed_roots


# ---------------------------------------------------------------------------
# Default config path and missing configuration
# ---------------------------------------------------------------------------

def test_default_config_path_uses_xdg_config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert default_config_path() == tmp_path / "xdg" / "os-assistant" / "config.toml"


def test_default_config_path_falls_back_to_home_dot_config(tmp_path, monkeypatch, isolated_home):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert default_config_path() == isolated_home / ".config" / "os-assistant" / "config.toml"


def test_absent_default_config_returns_defaults(tmp_path):
    # XDG_CONFIG_HOME points at an empty sandbox: no config file exists there.
    assert load_config() == Config()


def test_default_config_file_is_read(tmp_path):
    path = default_config_path()
    path.parent.mkdir(parents=True)
    path.write_text("[limits]\nmax_steps = 2\n", encoding="utf-8")
    cfg = load_config()
    assert cfg.max_steps == 2
    assert cfg.allowed_roots == ()


def test_explicit_missing_config_raises():
    with pytest.raises(ConfigurationError) as excinfo:
        load_config(Path("/nonexistent-sandbox/os-assistant/config.toml"))
    assert "does not exist" in str(excinfo.value)
    assert excinfo.value.exit_code == 2


def test_explicit_missing_config_raises_even_when_default_exists():
    path = default_config_path()
    path.parent.mkdir(parents=True)
    path.write_text("[limits]\nmax_steps = 2\n", encoding="utf-8")
    with pytest.raises(ConfigurationError):
        load_config(Path("/nonexistent-sandbox/os-assistant/config.toml"))


def test_invalid_toml_raises(tmp_path):
    path = write_config(tmp_path, "this is [[[ not toml")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_oversized_config_raises(tmp_path):
    path = write_config(tmp_path, "# padding\n" * 8000)  # well over 65536 bytes
    assert path.stat().st_size > 65536
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_config_path_that_is_a_directory_raises(tmp_path):
    with pytest.raises(ConfigurationError):
        load_config(tmp_path)


def test_fifo_config_is_rejected_without_blocking(tmp_path):
    path = tmp_path / "settings.pipe"
    os.mkfifo(path)
    with pytest.raises(ConfigurationError, match="regular TOML"):
        load_config(path)


def test_non_utf8_config_raises(tmp_path):
    path = tmp_path / "config.toml"
    path.write_bytes(b"[model]\nname = \"\xff\xfe\"\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_empty_config_file_returns_defaults(tmp_path):
    path = write_config(tmp_path, "")
    assert load_config(path) == Config()


def test_load_config_accepts_positional_and_keyword_arguments(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    path = write_config(tmp_path, "")
    assert load_config(path, (str(root),)).allowed_roots == (str(root),)
    assert load_config(path=path, extra_roots=(str(root),)).allowed_roots == (str(root),)


# ---------------------------------------------------------------------------
# Host: HTTP loopback literal IP:port only
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("host", [
    "http://127.0.0.1:11434",
    "http://127.0.0.1:8080",
    "http://127.0.0.2:11434",
    "http://[::1]:11434",
])
def test_valid_loopback_hosts_accepted(tmp_path, host):
    path = write_config(tmp_path, f'[model]\nhost = "{host}"\n')
    assert load_config(path).host == host


def test_host_trailing_slash_normalized(tmp_path):
    path = write_config(tmp_path, '[model]\nhost = "http://127.0.0.1:11434/"\n')
    assert load_config(path).host == "http://127.0.0.1:11434"


@pytest.mark.parametrize("host", [
    "http://8.8.8.8:11434",              # remote IP
    "http://192.168.1.10:11434",         # LAN IP
    "http://10.0.0.5:11434",             # private IP
    "http://localhost:11434",            # name, not a literal loopback IP
    "http://ollama.internal:11434",      # remote name
    "http://2130706433:11434",           # decimal-encoded IP smuggle
    "http://user:pass@127.0.0.1:11434",  # embedded credentials
    "http://user@127.0.0.1:11434",       # embedded user
    "http://127.0.0.1:11434/?url=http://evil",  # query redirect
    "http://127.0.0.1:11434/#frag",      # fragment
    "http://127.0.0.1:11434/proxy",      # path redirect
    "http://127.0.0.1:11434//evil",      # double-slash path
    "http://127.0.0.1:11434/../../etc",  # path traversal
    "https://127.0.0.1:11434",           # non-http scheme
    "file:///etc/passwd",                # file scheme
    "http://127.0.0.1",                  # no port
    "http://127.0.0.1:0",                # port zero
    "http://127.0.0.1:99999",            # port out of range
    "127.0.0.1:11434",                   # no scheme
    "",                                  # empty
])
def test_rejected_hosts(tmp_path, host):
    path = write_config(tmp_path, f'[model]\nhost = "{host}"\n')
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("literal", ["11434", "true", "1.5"])
def test_host_non_string_types_rejected(tmp_path, literal):
    path = write_config(tmp_path, f"[model]\nhost = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


# ---------------------------------------------------------------------------
# Model section fields
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    f'"{DEFAULT_MODEL}"',
])
def test_model_name_valid_accepted(tmp_path, name):
    path = write_config(tmp_path, f"[model]\nname = {name}\n")
    assert load_config(path).model == DEFAULT_MODEL


@pytest.mark.parametrize("name", [m for m in ALLOWED_MODELS if m != DEFAULT_MODEL])
def test_allowlisted_non_default_model_accepted(tmp_path, name):
    path = write_config(tmp_path, f'[model]\nname = "{name}"\n')
    assert load_config(path).model == name


def test_unknown_model_rejected_listing_allowed_names(tmp_path):
    path = write_config(tmp_path, '[model]\nname = "mistral:7b"\n')
    with pytest.raises(ConfigurationError) as exc:
        load_config(path)
    assert all(m in str(exc.value) for m in ALLOWED_MODELS)


@pytest.mark.parametrize("name", [
    '""',
    '"a b"',
    '"a\\tb"',
    f'"{ "a" * 129 }"',
    "123",
    "true",
])
def test_model_name_invalid_rejected(tmp_path, name):
    path = write_config(tmp_path, f"[model]\nname = {name}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("name", [
    '"qwen3.5:2b"',
    '"qwen3.5:2b-q4_K_M:latest"',
    '"openbmb/minicpm5-2b"',              # alias without the exact tag
    '"openbmb/minicpm5-2b:q4_K_M"',       # unsupported MiniCPM tag variant
    '"minicpm5-2b:latest"',               # unprefixed alias
    '"openbmb/MiniCPM5-2B:latest"',       # wrong case
    '"gpt-4o"',
    '"openai/gpt-4o"',                    # cloud namespaced name
    '"llama3"',
    f'"{ "a" * 128 }"',
])
def test_model_substitutions_rejected(tmp_path, name):
    # Only exact allowlisted tags may run; aliases, tag variants and cloud
    # names are refused.
    path = write_config(tmp_path, f"[model]\nname = {name}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_keep_alive_invalid_rejected(tmp_path):
    for literal in ('"2h"', "2", '""', "true"):
        path = write_config(tmp_path, f"[model]\nkeep_alive = {literal}\n")
        with pytest.raises(ConfigurationError):
            load_config(path)


def test_keep_alive_valid_accepted(tmp_path):
    for value in ("0", "30s", "1m", "2m", "5m", "10m"):
        path = write_config(tmp_path, f'[model]\nkeep_alive = "{value}"\n')
        assert load_config(path).keep_alive == value


# ---------------------------------------------------------------------------
# Strict numeric types and ranges (bools are not integers)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section,key,literal", [
    ("model", "context", "true"),
    ("model", "context", "false"),
    ("model", "context", "4096.0"),
    ("model", "context", '"4096"'),
    ("model", "timeout", "true"),
    ("model", "max_output_tokens", "true"),
    ("model", "max_output_tokens", "512.0"),
    ("model", "max_output_tokens", '"512"'),
    ("model", "timeout", "120.0"),
    ("limits", "max_steps", "true"),
    ("limits", "max_steps", "5.0"),
    ("limits", "tool_timeout", "false"),
    ("limits", "scan_entries", "true"),
    ("limits", "scan_seconds", "3.0"),
    ("limits", "scan_depth", '"8"'),
    ("limits", "usage_entries", "true"),
    ("limits", "usage_entries", "100000.0"),
    ("limits", "usage_entries", '"100000"'),
    ("limits", "usage_seconds", "false"),
    ("limits", "usage_seconds", "10.0"),
    ("limits", "usage_depth", "true"),
    ("limits", "usage_depth", '"64"'),
])
def test_integer_fields_reject_wrong_types(tmp_path, section, key, literal):
    path = write_config(tmp_path, f"[{section}]\n{key} = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("section,key,literal", [
    ("model", "context", "2047"),
    ("model", "context", "16385"),
    ("model", "context", "-1"),
    ("model", "context", "0"),
    ("model", "timeout", "4"),
    ("model", "max_output_tokens", "255"),
    ("model", "max_output_tokens", "1025"),
    ("model", "timeout", "301"),
    ("model", "timeout", "-5"),
    ("limits", "max_steps", "0"),
    ("limits", "max_steps", "11"),
    ("limits", "tool_timeout", "0"),
    ("limits", "tool_timeout", "31"),
    ("limits", "scan_entries", "0"),
    ("limits", "scan_entries", "10001"),
    ("limits", "scan_seconds", "0"),
    ("limits", "scan_seconds", "11"),
    ("limits", "scan_depth", "0"),
    ("limits", "scan_depth", "17"),
    ("limits", "usage_entries", "0"),
    ("limits", "usage_entries", "1000001"),
    ("limits", "usage_seconds", "0"),
    ("limits", "usage_seconds", "31"),
    ("limits", "usage_depth", "0"),
    ("limits", "usage_depth", "129"),
])
def test_integer_fields_reject_out_of_range(tmp_path, section, key, literal):
    path = write_config(tmp_path, f"[{section}]\n{key} = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("section,key,low,high", [
    ("model", "context", 2048, 16384),
    ("model", "timeout", 5, 300),
    ("model", "max_output_tokens", 256, 1024),
    ("limits", "max_steps", 1, 10),
    ("limits", "tool_timeout", 1, 30),
    ("limits", "scan_entries", 1, 10000),
    ("limits", "scan_seconds", 1, 10),
    ("limits", "scan_depth", 1, 16),
    ("limits", "usage_entries", 1, 1000000),
    ("limits", "usage_seconds", 1, 30),
    ("limits", "usage_depth", 1, 128),
])
def test_integer_fields_accept_boundaries(tmp_path, section, key, low, high):
    for value in (low, high):
        path = write_config(tmp_path, f"[{section}]\n{key} = {value}\n")
        cfg = load_config(path)
        assert isinstance(getattr(cfg, {"context": "context", "timeout": "model_timeout",
                                       "max_output_tokens": "max_output_tokens",
                                       "max_steps": "max_steps", "tool_timeout": "tool_timeout",
                                        "scan_entries": "scan_entries", "scan_seconds": "scan_seconds",
                                        "scan_depth": "scan_depth", "usage_entries": "usage_entries",
                                        "usage_seconds": "usage_seconds", "usage_depth": "usage_depth"}[key]), int)


def test_usage_budgets_are_independent_from_snapshot_scan_budgets(tmp_path):
    path = write_config(
        tmp_path,
        "[limits]\nscan_entries = 1\nscan_seconds = 1\nscan_depth = 1\n"
        "usage_entries = 1000000\nusage_seconds = 30\nusage_depth = 128\n",
    )
    cfg = load_config(path)
    assert (cfg.scan_entries, cfg.scan_seconds, cfg.scan_depth) == (1, 1, 1)
    assert (cfg.usage_entries, cfg.usage_seconds, cfg.usage_depth) == (1000000, 30, 128)
    assert cfg.allowed_roots == ()
    assert cfg.bash_roots == ()
    assert cfg.actions_enabled is False
    assert cfg.bash_enabled is False


def test_usage_limits_reject_unknown_keys(tmp_path):
    path = write_config(tmp_path, "[limits]\nusage_unknown = 1\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


# ---------------------------------------------------------------------------
# Unknown sections and keys
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "unknown_section = 1\n",
    "[network]\nbind = \"0.0.0.0\"\n",
    '[model]\nname = "x"\n[plugins]\nfoo = 1\n',
])
def test_unknown_top_level_keys_rejected(tmp_path, text):
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("text", [
    '[model]\nstealth = true\n',
    '[model]\nname = "x"\napi_key = "leak"\n',
    "[paths]\ndeny = [\"/etc\"]\n",
    "[actions]\nauto_approve = true\n",
    "[limits]\nmax_tokens = 100\n",
    "model = 3\n",
    'paths = "nope"\n',
])
def test_invalid_sections_rejected(tmp_path, text):
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigurationError):
        load_config(path)


# ---------------------------------------------------------------------------
# allowed_roots: pathlib normalization, no '..'
# ---------------------------------------------------------------------------

def test_normalized_root_accepts_absolute_and_home(isolated_home):
    assert normalized_root("/mnt/data") == "/mnt/data"
    assert normalized_root("/mnt/data/") == "/mnt/data"
    result = normalized_root("~/Documents")
    assert result == str(isolated_home / "Documents")
    assert Path(result).is_absolute()


@pytest.mark.parametrize("value", [
    "",
    "relative/path",
    "docs",
    "/a/../b",
    "/a/./..",
    "../etc",
    "~/../escape",
    "/tmp/with\x00nul",
    "/tmp/with\nnewline",
    "/tmp/with\x1besc",
    "/tmp/with\x7fdel",
    "/tmp/with\u202ebidi",
    "~unknown-user/Downloads",
    5,
    None,
    b"/bytes",
])
def test_normalized_root_rejects_dangerous_values(value):
    with pytest.raises(ConfigurationError):
        normalized_root(value)


@pytest.mark.parametrize("literal", ['"/a"', "5", "[1]", "[true]", '[[]]'])
def test_allowed_roots_must_be_list_of_paths(tmp_path, literal):
    path = write_config(tmp_path, f"[paths]\nallowed_roots = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_allowed_roots_rejects_traversal_entries(tmp_path):
    for literal in ('["/a/../b"]', '["rel"]', '[""]', '["~/../x"]'):
        path = write_config(tmp_path, f"[paths]\nallowed_roots = {literal}\n")
        with pytest.raises(ConfigurationError):
            load_config(path)


def test_allowed_roots_normalized_and_deduplicated(tmp_path, isolated_home):
    path = write_config(
        tmp_path,
        '[paths]\nallowed_roots = ["/mnt/data/", "/mnt/data", "~/Documents"]\n',
    )
    cfg = load_config(path)
    assert cfg.allowed_roots == ("/mnt/data", str(isolated_home / "Documents"))


def test_extra_roots_merged_and_deduplicated(tmp_path, isolated_home):
    path = write_config(tmp_path, '[paths]\nallowed_roots = ["~/Documents"]\n')
    cfg = load_config(path, (str(isolated_home / "Documents"), str(tmp_path)))
    assert cfg.allowed_roots == (str(isolated_home / "Documents"), str(tmp_path))


def test_extra_roots_must_be_valid(tmp_path):
    path = write_config(tmp_path, "")
    with pytest.raises(ConfigurationError):
        load_config(path, ("relative/root",))
    with pytest.raises(ConfigurationError):
        load_config(path, ("/a/../b",))


def test_too_many_roots_rejected(tmp_path):
    sixteen = ", ".join(f'"/mnt/r{i}"' for i in range(16))
    seventeen = ", ".join(f'"/mnt/r{i}"' for i in range(17))
    ok = write_config(tmp_path, f"[paths]\nallowed_roots = [{sixteen}]\n")
    assert len(load_config(ok).allowed_roots) == 16
    bad = write_config(tmp_path, f"[paths]\nallowed_roots = [{seventeen}]\n", name="bad.toml")
    with pytest.raises(ConfigurationError):
        load_config(bad)


def test_extra_roots_over_limit_rejected(tmp_path):
    path = write_config(tmp_path, "")
    extra = tuple(f"/mnt/r{i}" for i in range(17))
    with pytest.raises(ConfigurationError):
        load_config(path, extra)


# ---------------------------------------------------------------------------
# Actions: disabled by default, strict types, fixed absolute executables
# ---------------------------------------------------------------------------

def test_actions_disabled_by_default_even_with_apps(tmp_path):
    path = write_config(tmp_path, '[actions]\napps = { "editor" = "/usr/bin/editor" }\n')
    cfg = load_config(path)
    assert cfg.actions_enabled is False


@pytest.mark.parametrize("literal", ['"true"', '"yes"', "1", "0", "0.0"])
def test_actions_enabled_must_be_bool(tmp_path, literal):
    path = write_config(tmp_path, f"[actions]\nenabled = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("literal", ["true", "false"])
def test_actions_enabled_bool_accepted(tmp_path, literal):
    path = write_config(tmp_path, f"[actions]\nenabled = {literal}\n")
    assert load_config(path).actions_enabled is (literal == "true")


@pytest.mark.parametrize("literal", ["[]", '"dict"', "3"])
def test_apps_must_be_table(tmp_path, literal):
    path = write_config(tmp_path, f"[actions]\napps = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("alias", ['"my.app"', '"my app"', '"sh -c"', '""', '"ümlaut"', '"a/b"', '"bad!"', '"3.14"'])
def test_app_alias_validation(tmp_path, alias):
    path = write_config(tmp_path, f'[actions]\napps = {{ {alias} = "/usr/bin/prog" }}\n')
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("executable", ['"prog"', '"./prog"', '""'])
def test_app_executable_must_be_absolute(tmp_path, executable):
    path = write_config(tmp_path, f'[actions]\napps = {{ "prog" = {executable} }}\n')
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_apps_bounded_and_sorted(tmp_path):
    apps = ", ".join(f'"app{i}" = "/usr/bin/app{i}"' for i in range(17))
    path = write_config(tmp_path, f"[actions]\napps = {{ {apps} }}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)
    ok = write_config(
        tmp_path,
        '[actions]\napps = { "zed" = "/usr/bin/zed", "alpha" = "/usr/bin/alpha" }\n',
        name="ok.toml",
    )
    assert load_config(ok).apps == (("alpha", "/usr/bin/alpha"), ("zed", "/usr/bin/zed"))


# ---------------------------------------------------------------------------
# [bash]: opt-in content reads in explicit roots, independent of all other grants
# ---------------------------------------------------------------------------

def test_bash_defaults_stay_off_and_rootless():
    cfg = Config()
    assert (cfg.bash_enabled, cfg.bash_roots, cfg.bash_allow_writes) == (False, (), False)


def test_absent_bash_section_stays_disabled(tmp_path):
    cfg = load_config(write_config(tmp_path, "[limits]\nmax_steps = 2\n"))
    assert (cfg.bash_enabled, cfg.bash_roots, cfg.bash_allow_writes) == (False, (), False)


@pytest.mark.parametrize("literal", ["3", '"nope"', "[]", "true", "0.5"])
def test_bash_section_must_be_table(tmp_path, literal):
    path = write_config(tmp_path, f"bash = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("key", ["enabled", "allow_writes"])
@pytest.mark.parametrize("literal", ['"true"', '"yes"', "1", "0", "0.0", "[]", "{}"])
def test_bash_booleans_are_strict_types(tmp_path, key, literal):
    path = write_config(tmp_path, f"[bash]\n{key} = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("literal", ["true", "false"])
def test_bash_booleans_accepted_verbatim(tmp_path, literal):
    path = write_config(tmp_path, f"[bash]\nenabled = {literal}\nallow_writes = {literal}\n")
    cfg = load_config(path)
    assert cfg.bash_enabled is (literal == "true")
    assert cfg.bash_allow_writes is (literal == "true")


def test_bash_enabled_with_empty_roots_is_allowed_but_grants_nothing(tmp_path):
    cfg = load_config(write_config(tmp_path, "[bash]\nenabled = true\n"))
    assert cfg.bash_enabled is True
    assert cfg.bash_roots == ()


def test_bash_allow_writes_alone_does_not_enable_bash(tmp_path):
    cfg = load_config(write_config(tmp_path, "[bash]\nallow_writes = true\n"))
    assert cfg.bash_enabled is False
    assert cfg.bash_allow_writes is True


@pytest.mark.parametrize("text", [
    '[bash]\nroot = ["/mnt/data"]\n',
    "[bash]\nallow_root = true\n",
    "[bash]\ninherit_allowed_roots = true\n",
    '[bash]\ncommands = ["ls"]\n',
    "[bash]\nauto_approve = true\n",
    '[bash]\nenabled = true\nprotected = []\n',
    '[bash]\nallowed_root = "/mnt/data"\n',
    '[bash]\nread_only = true\n',
])
def test_bash_unknown_keys_rejected(tmp_path, text):
    path = write_config(tmp_path, text)
    with pytest.raises(ConfigurationError):
        load_config(path)


@pytest.mark.parametrize("literal", ['"/mnt/data"', "5", "true", "[1]", "[true]", "[[]]", '["/mnt/data", 3]'])
def test_bash_allowed_roots_must_be_list_of_paths(tmp_path, literal):
    path = write_config(tmp_path, f"[bash]\nallowed_roots = {literal}\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_bash_allowed_roots_rejects_traversal_entries(tmp_path):
    for literal in ('["/a/../b"]', '["rel"]', '[""]', '["~/../x"]', '["~unknown-user/Downloads"]'):
        path = write_config(tmp_path, f"[bash]\nallowed_roots = {literal}\n")
        with pytest.raises(ConfigurationError):
            load_config(path)


def test_bash_roots_normalized_and_deduplicated(tmp_path, isolated_home):
    path = write_config(
        tmp_path,
        '[bash]\nallowed_roots = ["/mnt/data/", "/mnt/data", "~/Notes"]\n',
    )
    cfg = load_config(path)
    assert cfg.bash_roots == ("/mnt/data", str(isolated_home / "Notes"))


def test_bash_roots_at_most_sixteen(tmp_path):
    sixteen = ", ".join(f'"/mnt/r{i}"' for i in range(16))
    seventeen = ", ".join(f'"/mnt/r{i}"' for i in range(17))
    ok = write_config(tmp_path, f"[bash]\nallowed_roots = [{sixteen}]\n")
    assert len(load_config(ok).bash_roots) == 16
    bad = write_config(tmp_path, f"[bash]\nallowed_roots = [{seventeen}]\n", name="bad.toml")
    with pytest.raises(ConfigurationError):
        load_config(bad)


def test_bash_roots_deduplicate_before_the_limit(tmp_path):
    # 17 raw entries that normalize down to 16 distinct roots stay valid.
    entries = [f'"/mnt/r{i}"' for i in range(16)] + ['"/mnt/r15/"']
    path = write_config(tmp_path, f"[bash]\nallowed_roots = [{', '.join(entries)}]\n")
    assert len(load_config(path).bash_roots) == 16


def test_bash_opt_ins_do_not_enable_actions_or_metadata_roots(tmp_path):
    text = (
        '[actions]\napps = { "editor" = "/usr/bin/editor" }\n'
        "[themes]\nenabled = false\n"
        '[bash]\nenabled = true\nallowed_roots = ["/mnt/data"]\nallow_writes = true\n'
    )
    cfg = load_config(write_config(tmp_path, text))
    assert cfg.bash_enabled is True
    assert cfg.bash_roots == ("/mnt/data",)
    assert cfg.bash_allow_writes is True
    assert cfg.actions_enabled is False
    assert cfg.allowed_roots == ()
    assert cfg.themes_enabled is False


def test_actions_enabled_does_not_imply_bash_access(tmp_path):
    cfg = load_config(write_config(tmp_path, "[actions]\nenabled = true\n"))
    assert cfg.actions_enabled is True
    assert cfg.bash_enabled is False
    assert cfg.bash_roots == ()
    assert cfg.bash_allow_writes is False


def test_paths_allowed_roots_do_not_become_bash_roots(tmp_path):
    path = write_config(tmp_path, '[paths]\nallowed_roots = ["/mnt/data"]\n')
    cfg = load_config(path)
    assert cfg.allowed_roots == ("/mnt/data",)
    assert cfg.bash_roots == ()


def test_extra_roots_never_become_bash_roots(tmp_path, isolated_home):
    extra = (str(tmp_path / "extra"), str(isolated_home / "Documents"))
    path = write_config(tmp_path, '[bash]\nenabled = true\nallowed_roots = ["~/Notes"]\n')
    cfg = load_config(path, extra)
    assert cfg.allowed_roots == extra
    assert cfg.bash_roots == (str(isolated_home / "Notes"),)
    assert all(root not in cfg.bash_roots for root in extra)


def test_extra_roots_do_not_populate_empty_bash_roots(tmp_path):
    extra = (str(tmp_path / "extra"),)
    cfg = load_config(write_config(tmp_path, "[bash]\nenabled = true\n"), extra)
    assert cfg.allowed_roots == extra
    assert cfg.bash_roots == ()


def test_extra_roots_still_validate_independently_of_bash(tmp_path):
    path = write_config(tmp_path, '[bash]\nenabled = true\nallowed_roots = ["/mnt/data"]\n')
    with pytest.raises(ConfigurationError):
        load_config(path, ("relative/root",))


def test_bash_allow_writes_is_recorded_but_actions_are_not_forced(tmp_path):
    # The loader records opt-ins only; the runner enforces actions.enabled and
    # the typed 'yes' gate for every mutating command.
    cfg = load_config(
        write_config(tmp_path, '[bash]\nenabled = true\nallowed_roots = ["/mnt/data"]\nallow_writes = true\n')
    )
    assert cfg.bash_allow_writes is True
    assert cfg.actions_enabled is False


def test_configuration_error_exit_code():
    assert ConfigurationError.exit_code == 2
    assert issubclass(ConfigurationError, Exception)


# --- [web_search] section ---------------------------------------------------

def test_web_search_defaults_off(tmp_path):
    cfg = load_config(write_config(tmp_path, ""))
    assert cfg.web_search_enabled is False
    assert cfg.web_search_host == "http://127.0.0.1:8888"
    assert cfg.web_search_timeout == 10


def test_web_search_section_accepted(tmp_path):
    cfg = load_config(write_config(tmp_path, '[web_search]\nenabled = true\nhost = "http://127.0.0.1:9000/"\ntimeout = 30\n'))
    assert (cfg.web_search_enabled, cfg.web_search_host, cfg.web_search_timeout) == (True, "http://127.0.0.1:9000", 30)


def test_web_search_unknown_key_rejected(tmp_path):
    with pytest.raises(ConfigurationError):
        load_config(write_config(tmp_path, "[web_search]\nextra = 1\n"))


@pytest.mark.parametrize("literal", ['"yes"', "1", "[true]"])
def test_web_search_enabled_must_be_bool(tmp_path, literal):
    with pytest.raises(ConfigurationError, match="web_search.enabled"):
        load_config(write_config(tmp_path, f"[web_search]\nenabled = {literal}\n"))


@pytest.mark.parametrize("host", [
    "http://example.com:8888", "https://127.0.0.1:8888", "http://localhost:8888",
    "http://192.168.1.2:8888", "http://127.0.0.1", "http://127.0.0.1:8888/x",
])
def test_web_search_bad_hosts_rejected(tmp_path, host):
    with pytest.raises(ConfigurationError, match="SearXNG host"):
        load_config(write_config(tmp_path, f'[web_search]\nhost = "{host}"\n'))


@pytest.mark.parametrize("value,ok", [(0, False), (1, True), (30, True), (31, False), ('"5"', False), (True, False)])
def test_web_search_timeout_range(tmp_path, value, ok):
    path = write_config(tmp_path, f"[web_search]\ntimeout = {str(value).lower() if value is True else value}\n")
    if ok:
        assert load_config(path).web_search_timeout == value
    else:
        with pytest.raises(ConfigurationError):
            load_config(path)

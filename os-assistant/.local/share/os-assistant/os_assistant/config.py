"""Explicit local settings; defaults never grant arbitrary-file or action access."""

from dataclasses import dataclass
import ipaddress
import os
from pathlib import Path
import stat
import tomllib
import unicodedata
from urllib.parse import urlsplit

from .contracts import ConfigurationError


DEFAULT_MODEL = "qwen3:4b-instruct-2507-q4_K_M"
ALLOWED_MODELS = (
    DEFAULT_MODEL,
    "openbmb/minicpm5-2b:latest",
    "qwen3.5:2b-q4_K_M",
    "llama3.2:3b",
    "granite4:3b",
    "phi4-mini:3.8b",
)


def model_not_allowed_message(name: str) -> str:
    return (f"Model {name!r} is not allowed; cloud models and silent substitutions are forbidden. "
            f"Allowed local models: {', '.join(ALLOWED_MODELS)}.")
STATUS_TOOLS = ("desktop_status", "power_status", "plugin_status", "display_status", "dotfiles_status",
                "alerts_status")


@dataclass(frozen=True)
class Config:
    model: str = DEFAULT_MODEL
    host: str = "http://127.0.0.1:11434"
    context: int = 8192
    keep_alive: str = "2m"
    model_timeout: int = 180
    max_output_tokens: int = 768
    max_steps: int = 6
    allowed_roots: tuple[str, ...] = ()
    actions_enabled: bool = False
    apps: tuple[tuple[str, str], ...] = ()
    themes_enabled: bool = False
    theme_timeout: int = 120
    status_enabled: tuple[str, ...] = STATUS_TOOLS
    tool_timeout: int = 5
    scan_entries: int = 3000
    scan_seconds: int = 3
    scan_depth: int = 8
    bash_enabled: bool = False
    bash_roots: tuple[str, ...] = ()
    bash_allow_writes: bool = False
    usage_entries: int = 100000
    usage_seconds: int = 10
    usage_depth: int = 64
    web_search_enabled: bool = False
    web_search_host: str = "http://127.0.0.1:8888"
    web_search_timeout: int = 10
    alerts_interval: int = 60
    alerts_disk_paths: tuple[str, ...] = ("/",)
    alerts_disk_warning: int = 90
    alerts_disk_critical: int = 95
    alerts_memory_warning: int = 85
    alerts_memory_critical: int = 95
    alerts_repeat_minutes: int = 60


def default_config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "os-assistant/config.toml"


def normalized_root(value: str) -> str:
    if not isinstance(value, str) or not value or any(unicodedata.category(c).startswith("C") for c in value):
        raise ConfigurationError("Approved folders must be nonempty paths without control characters.")
    if value.startswith("~") and value != "~" and not value.startswith("~/"):
        raise ConfigurationError("Only your own ~/... folder shorthand is supported.")
    try:
        path = Path(value).expanduser()
    except RuntimeError:
        raise ConfigurationError("Cannot determine your home folder.") from None
    if not path.is_absolute() or ".." in path.parts:
        raise ConfigurationError("Approved folders must be absolute (or ~/...) and cannot contain '..'.")
    return str(path)


def _integer(value: object, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ConfigurationError(f"{name} must be an integer between {low} and {high}.")
    return value


def validate_host(host: object, label: str = "Ollama host") -> str:
    if not isinstance(host, str) or any(c.isspace() or unicodedata.category(c).startswith("C") for c in host):
        raise ConfigurationError(f"{label} cannot contain whitespace or control characters.")
    try:
        parts = urlsplit(host)
        loopback = ipaddress.ip_address(parts.hostname or "").is_loopback
        valid = (parts.scheme == "http" and loopback and parts.port is not None and 1 <= parts.port <= 65535
                 and not parts.username and not parts.password and not parts.query
                 and not parts.fragment and parts.path in ("", "/"))
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise ConfigurationError(f"{label} must be an HTTP loopback IP with a port; remote hosts are forbidden.")
    return str(host).rstrip("/")


def load_config(path: Path | None = None, extra_roots: tuple[str, ...] = ()) -> Config:
    explicit = path is not None
    path = path or default_config_path()
    try:
        # Follow trusted Stow links, but reject pipes/devices without blocking on open.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ConfigurationError("Configuration must be a regular TOML file.")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(65537)
        finally:
            os.close(fd)
        if len(raw) > 65536:
            raise ConfigurationError("Configuration is too large.")
        data = tomllib.loads(raw.decode("utf-8"))
    except FileNotFoundError:
        if explicit:
            raise ConfigurationError("Requested configuration file does not exist.") from None
        data = {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise ConfigurationError("Cannot read a valid TOML configuration.") from None

    allowed = {"model", "paths", "actions", "themes", "status", "limits", "bash", "web_search", "alerts"}
    if data.keys() - allowed:
        raise ConfigurationError("Unknown configuration section.")
    sections = {}
    fields = {
        "model": {"name", "host", "context", "keep_alive", "timeout", "max_output_tokens"},
        "paths": {"allowed_roots"},
        "actions": {"enabled", "apps"},
        "themes": {"enabled", "timeout"},
        "status": {"enabled"},
        "limits": {
            "max_steps", "tool_timeout", "scan_entries", "scan_seconds", "scan_depth",
            "usage_entries", "usage_seconds", "usage_depth",
        },
        "bash": {"enabled", "allowed_roots", "allow_writes"},
        "web_search": {"enabled", "host", "timeout"},
        "alerts": {"interval", "disk_paths", "disk_warning_percent", "disk_critical_percent",
                   "memory_warning_percent", "memory_critical_percent", "repeat_minutes"},
    }
    for name, keys in fields.items():
        section = data.get(name, {})
        if not isinstance(section, dict) or section.keys() - keys:
            raise ConfigurationError(f"Invalid {name} configuration section.")
        sections[name] = section
    model, paths, actions, limits = (sections[n] for n in ("model", "paths", "actions", "limits"))
    themes = sections["themes"]
    status_enabled = sections["status"].get("enabled", list(STATUS_TOOLS))
    if (not isinstance(status_enabled, list) or len(status_enabled) > len(STATUS_TOOLS)
            or any(not isinstance(name, str) or name not in STATUS_TOOLS for name in status_enabled)
            or len(set(status_enabled)) != len(status_enabled)):
        raise ConfigurationError("status.enabled must list unique supported status tool names.")
    host = validate_host(model.get("host", Config.host))
    name = model.get("name", DEFAULT_MODEL)
    if not isinstance(name, str) or not name or len(name) > 128 or any(c.isspace() for c in name):
        raise ConfigurationError("Invalid local model name.")
    if name not in ALLOWED_MODELS:
        raise ConfigurationError(model_not_allowed_message(name))
    keep_alive = model.get("keep_alive", "2m")
    if keep_alive not in ("0", "30s", "1m", "2m", "5m", "10m"):
        raise ConfigurationError("keep_alive must be 0, 30s, 1m, 2m, 5m, or 10m.")
    roots = paths.get("allowed_roots", [])
    if not isinstance(roots, list):
        raise ConfigurationError("allowed_roots must be a list of paths.")
    roots = tuple(dict.fromkeys(normalized_root(r) for r in [*roots, *extra_roots]))
    if len(roots) > 16:
        raise ConfigurationError("At most 16 folders may be approved.")
    bash = sections["bash"]
    bash_enabled = bash.get("enabled", False)
    bash_allow_writes = bash.get("allow_writes", False)
    if type(bash_enabled) is not bool or type(bash_allow_writes) is not bool:
        raise ConfigurationError("bash.enabled and bash.allow_writes must be booleans.")
    bash_paths = bash.get("allowed_roots", [])
    if not isinstance(bash_paths, list):
        raise ConfigurationError("bash.allowed_roots must be a list of paths.")
    # Deliberately separate from paths.allowed_roots and --allow-root extra_roots:
    # those authorize metadata scans only and never grant Bash content access.
    bash_roots = tuple(dict.fromkeys(normalized_root(r) for r in bash_paths))
    if len(bash_roots) > 16:
        raise ConfigurationError("At most 16 Bash folders may be approved.")
    web = sections["web_search"]
    web_enabled = web.get("enabled", False)
    if type(web_enabled) is not bool:
        raise ConfigurationError("web_search.enabled must be a boolean.")
    web_host = validate_host(web.get("host", Config.web_search_host), label="SearXNG host")
    alerts = sections["alerts"]
    alert_paths = alerts.get("disk_paths", ["/"])
    if not isinstance(alert_paths, list):
        raise ConfigurationError("alerts.disk_paths must be a list of paths.")
    alert_paths = tuple(dict.fromkeys(normalized_root(r) for r in alert_paths))
    if not 1 <= len(alert_paths) <= 8:
        raise ConfigurationError("alerts.disk_paths must list 1 to 8 paths.")
    disk_warning = _integer(alerts.get("disk_warning_percent", 90), "disk_warning_percent", 50, 99)
    disk_critical = _integer(alerts.get("disk_critical_percent", 95), "disk_critical_percent", 51, 100)
    memory_warning = _integer(alerts.get("memory_warning_percent", 85), "memory_warning_percent", 50, 99)
    memory_critical = _integer(alerts.get("memory_critical_percent", 95), "memory_critical_percent", 51, 100)
    if disk_critical <= disk_warning or memory_critical <= memory_warning:
        raise ConfigurationError("Critical alert percentages must be higher than their warning percentages.")
    enabled = actions.get("enabled", False)
    apps = actions.get("apps", {})
    if type(enabled) is not bool or not isinstance(apps, dict) or len(apps) > 16:
        raise ConfigurationError("Invalid actions configuration.")
    themes_enabled = themes.get("enabled", False)
    if type(themes_enabled) is not bool:
        raise ConfigurationError("themes.enabled must be a boolean.")
    for alias, executable in apps.items():
        if (not isinstance(alias, str) or not 1 <= len(alias) <= 64 or not alias.isascii()
                or not alias.replace("-", "").isalnum() or not isinstance(executable, str)
                or not executable.isascii() or len(executable) > 1024
                or any(unicodedata.category(c).startswith("C") for c in executable)
                or not Path(executable).is_absolute()):
            raise ConfigurationError("App aliases must name fixed absolute executable paths.")
    return Config(
        model=name, host=host.rstrip("/"), keep_alive=keep_alive,
        context=_integer(model.get("context", 8192), "context", 2048, 16384),
        model_timeout=_integer(model.get("timeout", 180), "model timeout", 5, 300),
        max_output_tokens=_integer(model.get("max_output_tokens", 768), "max_output_tokens", 256, 1024),
        allowed_roots=roots, actions_enabled=enabled, apps=tuple(sorted(apps.items())),
        themes_enabled=themes_enabled,
        theme_timeout=_integer(themes.get("timeout", 120), "theme timeout", 10, 180),
        status_enabled=tuple(status_enabled),
        max_steps=_integer(limits.get("max_steps", 6), "max_steps", 1, 10),
        tool_timeout=_integer(limits.get("tool_timeout", 5), "tool_timeout", 1, 30),
        scan_entries=_integer(limits.get("scan_entries", 3000), "scan_entries", 1, 10000),
        scan_seconds=_integer(limits.get("scan_seconds", 3), "scan_seconds", 1, 10),
        scan_depth=_integer(limits.get("scan_depth", 8), "scan_depth", 1, 16),
        usage_entries=_integer(limits.get("usage_entries", 100000), "usage_entries", 1, 1000000),
        usage_seconds=_integer(limits.get("usage_seconds", 10), "usage_seconds", 1, 30),
        usage_depth=_integer(limits.get("usage_depth", 64), "usage_depth", 1, 128),
        bash_enabled=bash_enabled, bash_roots=bash_roots, bash_allow_writes=bash_allow_writes,
        web_search_enabled=web_enabled, web_search_host=web_host,
        web_search_timeout=_integer(web.get("timeout", 10), "web_search timeout", 1, 30),
        alerts_interval=_integer(alerts.get("interval", 60), "alerts interval", 15, 3600),
        alerts_disk_paths=alert_paths, alerts_disk_warning=disk_warning, alerts_disk_critical=disk_critical,
        alerts_memory_warning=memory_warning, alerts_memory_critical=memory_critical,
        alerts_repeat_minutes=_integer(alerts.get("repeat_minutes", 60), "repeat_minutes", 0, 1440),
    )

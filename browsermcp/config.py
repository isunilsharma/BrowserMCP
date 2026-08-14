import fnmatch
import os
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, Field

CONFIG_DIR = Path(os.path.expanduser("~/.browsermcp"))
CONFIG_FILE = CONFIG_DIR / "config.toml"
RUNS_DIR = CONFIG_DIR / "runs"


class Settings(BaseModel):
    chrome_port: int = 9222
    allowed_hosts: list[str] = Field(
        default_factory=lambda: [
            # Corporate-owned domains. These are placeholders — replace them
            # with your own domains in ~/.browsermcp/config.toml before use,
            # otherwise every internal host will be rejected by the gate.
            "*.example.com",
            "*.example.net",
            "*.example.org",
            # Microsoft 365 services hosted on Microsoft's cloud but accessed
            # via the corporate Entra ID tenant SSO (Power BI, Outlook, Teams, SharePoint, etc.)
            "*.powerbi.com",
            "app.powerbi.com",
            "*.microsoftonline.com",
            "login.microsoftonline.com",
            "*.office.com",
            "*.sharepoint.com",
            # Outlook web — Microsoft consolidated mail UI lives at
            # outlook.cloud.microsoft and outlook.office.com (both reach the
            # same mailbox via Entra ID SSO).
            "outlook.cloud.microsoft",
            "*.cloud.microsoft",
            "*.outlook.com",
            "outlook.office.com",
        ]
    )
    log_retention_days: int = 30
    max_tool_calls_per_run: int = 50
    # Phase 5 telemetry — opt-in only. Even when True, the v0 sink writes
    # locally to ~/.browsermcp/telemetry.jsonl; a real backend requires
    # separate IT/InfoSec review (see docs/security.md §4).
    telemetry_opt_in: bool = False
    telemetry_endpoint: str | None = None


def load_settings() -> Settings:
    """Load Settings from ~/.browsermcp/config.toml, falling back to defaults."""
    if CONFIG_FILE.exists():
        with CONFIG_FILE.open("rb") as fh:
            data = tomllib.load(fh)
        return Settings(**data)
    return Settings()


def ensure_dirs() -> None:
    """Create the config and runs directories if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def host_allowed(url: str, settings: Settings) -> bool:
    """Return True when url's host matches one of settings.allowed_hosts."""
    host = urlparse(url).hostname or ""
    return any(fnmatch.fnmatch(host, pattern) for pattern in settings.allowed_hosts)

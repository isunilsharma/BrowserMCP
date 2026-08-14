"""Keep BrowserMCP-tracked tabs' sessions warm by reading them periodically.

Run via launchd (macOS) every 30 minutes. Reads ~/.browsermcp/keepalive.toml:

  [[urls]]
  pattern = "powerbi.example.com"
  description = "Power BI"

  [[urls]]
  pattern = "confluence.example.com"

For each pattern, attaches to Chrome, finds a matching tab, calls read_page
(to keep the cookies + session tokens warm), and logs the result.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib

from browsermcp.config import host_allowed, load_settings
from browsermcp.tools.chrome import chrome_attach, chrome_find_or_open_window
from browsermcp.tools.reading import read_page


CONFIG = Path(os.path.expanduser("~/.browsermcp/keepalive.toml"))


def _looks_like_url(pattern: str) -> bool:
    """A pattern is URL-shaped if it has a scheme; allow bare hostnames too."""
    return pattern.startswith(("http://", "https://"))


def _pattern_allowed(pattern: str) -> bool:
    """Check a keepalive pattern against the allowlist before opening any tab.

    Two pattern forms are accepted from the config:
      • full URL ('https://powerbi.example.com/...') — passed straight to host_allowed
      • bare hostname ('confluence.example.com') — wrapped as 'https://<host>/' first
    Anything else (e.g. shell glob, regex) is rejected with a clear log line.
    """
    settings = load_settings()
    if _looks_like_url(pattern):
        return host_allowed(pattern, settings)
    # Bare-host form: build a synthetic URL just for the allowlist check.
    if "/" in pattern or " " in pattern or pattern.startswith("."):
        return False
    return host_allowed(f"https://{pattern}/", settings)


async def main() -> int:
    if not CONFIG.exists():
        print(f"No keepalive config at {CONFIG} — nothing to do.", file=sys.stderr)
        return 0
    with CONFIG.open("rb") as f:
        cfg = tomllib.load(f)
    urls = cfg.get("urls", [])
    if not urls:
        print("No URLs configured.", file=sys.stderr)
        return 0
    await chrome_attach()
    for entry in urls:
        pattern = entry.get("pattern")
        if not pattern:
            continue
        # CRITICAL: validate against the allowlist BEFORE chrome_find_or_open_window,
        # which would happily navigate a new tab to any URL the config provides.
        if not _pattern_allowed(pattern):
            print(
                f"  ⚠ {pattern}: not in allowlist (browsermcp.config.allowed_hosts) — skip",
                file=sys.stderr,
            )
            continue
        try:
            window = await chrome_find_or_open_window(url_pattern=pattern)
            page = await read_page(viewport_only=True, window_id=window.window_id)
            if "sign in" in (page.title or "").lower():
                print(f"  ⚠ {pattern}: signed out — skip", file=sys.stderr)
            else:
                print(f"  ✓ {pattern}: warm ({page.title[:60]!r})", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ {pattern}: {type(e).__name__}: {str(e)[:120]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

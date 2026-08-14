"""Shared helpers for the e2e smoke-test suite.

These tests are EXCLUDED from default pytest runs (see the `e2e` marker in
pyproject.toml). Engineers invoke them manually before releases via:

    pytest -m e2e tests/e2e/

They assume:
  - A Chrome is already running locally with `--remote-debugging-port=9222`.
  - That Chrome has signed-in sessions for the internal SaaS targets
    (Power BI, Confluence, Jira). The harness does not log anyone in.
  - The corporate VPN / network is reachable so the internal
    hosts resolve. The `reachable()` helper here lets each test skip
    cleanly when it isn't, rather than failing on a network error that
    would only confuse the engineer running the suite from a coffee shop.

This conftest deliberately does NOT pull in the browser_page / fixture_site
fixtures from tests/integration/conftest.py — e2e tests drive the public
MCP tool surface directly (chrome_attach, chrome_find_or_open_window,
navigate) the same way a teammate would from Claude Code.
"""
from __future__ import annotations

import socket
from urllib.parse import urlparse


def reachable(url_or_host: str, timeout_s: float = 3.0) -> bool:
    """Return True if a TCP connection to (host, port) succeeds within timeout_s.

    Accepts either a full URL ("https://confluence.example.com") or a bare
    host ("confluence.example.com"). If a URL is passed, port is inferred
    from the scheme (443 for https, 80 for http) unless explicit.

    Tests use this via:
        if not reachable("https://confluence.example.com"):
            pytest.skip("confluence.example.com unreachable")

    A 3-second budget is generous for an intra-corp host on VPN and tight
    enough to fail fast on a laptop that's off-network.
    """
    parsed = urlparse(url_or_host if "://" in url_or_host else f"//{url_or_host}", scheme="https")
    host = parsed.hostname or url_or_host
    port = parsed.port or (80 if parsed.scheme == "http" else 443)
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            return True
    except OSError:
        return False

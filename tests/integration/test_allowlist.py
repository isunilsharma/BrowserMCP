"""Allow-list gate: navigate() must reject hosts that aren't explicitly allowed.

This is the highest-stakes security guarantee BrowserMCP makes — every browser
action funnels through navigate() at some point, and a permissive default would
let a skill quietly point a teammate's SSO'd Chrome at an attacker-controlled
URL. We assert both halves of the contract:

  - default Settings (which omit localhost) → ValueError
  - settings with localhost added → no ValueError
"""
from __future__ import annotations

import pytest

from browsermcp import state as state_mod
from browsermcp.config import Settings
from browsermcp.tools import navigate


pytestmark = pytest.mark.integration


async def test_navigate_rejects_unlisted_host(
    fixture_site: str,
    browser_page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without localhost on the allow-list, navigate() raises ValueError.

    We don't even need a real browser here for the rejection path — the
    allow-list check happens before the Page is touched — but we keep the
    fixture so the assertion that NO navigation happened is meaningful.
    """
    # Force the default-shaped allow-list (corporate domains only); the
    # test fixture site at 127.0.0.1 is intentionally NOT in this list.
    restricted = Settings(allowed_hosts=["*.example.com", "*.example.net"])
    monkeypatch.setattr(
        "browsermcp.tools.navigation.load_settings", lambda: restricted
    )

    await state_mod.register_window("test-allow", browser_page)

    # Capture URL before the rejected call so we can assert below that
    # navigate() really didn't move the browser anywhere.
    before_url = await browser_page.evaluate("() => window.location.href")

    with pytest.raises(ValueError, match="not on the allowed-hosts list"):
        await navigate(f"{fixture_site}/form", window_id="test-allow")

    after_url = await browser_page.evaluate("() => window.location.href")
    # Equality — not just startswith — to confirm the page didn't even
    # partially load before the gate fired.
    assert before_url == after_url


async def test_navigate_allows_listed_host(
    fixture_site: str,
    browser_page,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With localhost on the allow-list, navigate() succeeds end-to-end.

    Complements the rejection test: proves the gate is actually toggled by
    the allow-list (i.e. it's not just broken-closed for all hosts).
    """
    permissive = Settings(allowed_hosts=["127.0.0.1", "localhost"])
    monkeypatch.setattr(
        "browsermcp.tools.navigation.load_settings", lambda: permissive
    )

    await state_mod.register_window("test-allow-ok", browser_page)
    result = await navigate(f"{fixture_site}/form", window_id="test-allow-ok")

    # Flask returns "Contact" as the form-page title; any non-empty value
    # tells us navigation completed and the title was successfully read
    # back, which transitively confirms the Page is alive.
    assert result.title
    assert "/form" in result.url

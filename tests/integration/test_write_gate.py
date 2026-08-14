"""Two-phase confirmation gate: write/destructive actions need confirmed=True.

CLAUDE.md treats this as a load-bearing contract — bulk Jira updates,
"Submit" / "Delete" / "Approve" clicks all flow through click() and
type_text() with confirm_intent="write" or "destructive". Skipping the
confirm step must surface as ok=False with a clear note, NOT a silent
"oh well, I'll click it anyway".

We verify both halves of the two-phase pattern:
  1. confirm_intent="write", confirmed=False → ok=False, notes mention
     "confirmation_required", and the DOM is unchanged.
  2. confirm_intent="write", confirmed=True → ok=True, the click goes
     through, and the response page renders as expected.
"""
from __future__ import annotations

import pytest

from browsermcp import state as state_mod
from browsermcp.config import Settings
from browsermcp.tools import click, navigate, type_text


pytestmark = pytest.mark.integration


@pytest.fixture
def _allow_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    test_settings = Settings(allowed_hosts=["127.0.0.1", "localhost"])
    monkeypatch.setattr(
        "browsermcp.tools.navigation.load_settings", lambda: test_settings
    )


async def test_write_click_blocked_without_confirmation(
    fixture_site: str,
    browser_page,
    _allow_localhost: None,
) -> None:
    """A write-intent click without confirmed=True returns ok=False, no DOM change."""
    await state_mod.register_window("test-gate", browser_page)
    await navigate(f"{fixture_site}/form", window_id="test-gate")

    # Snapshot the URL so we can later prove the form was NOT submitted.
    # Going by URL (rather than body text) avoids any timing-of-paint trap.
    before_url = await browser_page.evaluate("() => window.location.href")

    result = await click(
        description="Submit",
        window_id="test-gate",
        confirm_intent="write",
        confirmed=False,
    )

    assert result.ok is False
    assert result.notes is not None
    # The note contract is part of the public API — skills branch on this
    # string to know they need to ask the user for permission and retry.
    assert "confirmation_required" in result.notes

    after_url = await browser_page.evaluate("() => window.location.href")
    assert before_url == after_url, (
        "click() with confirmed=False must NOT actually click the element"
    )


async def test_write_click_succeeds_with_confirmation(
    fixture_site: str,
    browser_page,
    _allow_localhost: None,
) -> None:
    """The same write-intent click with confirmed=True goes through."""
    await state_mod.register_window("test-gate-ok", browser_page)
    await navigate(f"{fixture_site}/form", window_id="test-gate-ok")

    # The form needs some content to round-trip — type_text with no
    # confirm_intent is a read-equivalent (it's not a sensitive field).
    await type_text(field="Email", text="ok@example.com", window_id="test-gate-ok")
    await type_text(field="Message", text="confirmed write", window_id="test-gate-ok")

    result = await click(
        description="Submit",
        window_id="test-gate-ok",
        confirm_intent="write",
        confirmed=True,
    )

    assert result.ok is True
    # No "confirmation_required" should appear on the success path — be
    # strict about this so we catch any regression that leaks the gate
    # message into the success response.
    if result.notes is not None:
        assert "confirmation_required" not in result.notes

    body_text = await browser_page.evaluate(
        "() => document.body ? document.body.innerText : ''"
    )
    assert "Thanks for your message" in body_text


async def test_sensitive_field_type_blocked_without_confirmation(
    fixture_site: str,
    browser_page,
    _allow_localhost: None,
) -> None:
    """type_text into a sensitive-named field requires confirmed=True too.

    The interaction layer inspects the `field` argument for sensitive-name
    patterns (password/pin/secret/token/...) and forces confirmation even
    when the caller passes confirm_intent="read". Belt-and-braces against
    a skill that says "type the password into Username" by accident.
    """
    await state_mod.register_window("test-gate-sens", browser_page)
    await navigate(f"{fixture_site}/login", window_id="test-gate-sens")

    # "password" isn't an actual field on /login (it only has username),
    # but the gate is keyed off the field NAME passed to type_text, not
    # off the page DOM. So this exercises the gate without needing a
    # real password input to exist. It should bail out before resolving
    # any element.
    result = await type_text(
        field="password",
        text="hunter2",
        window_id="test-gate-sens",
        confirmed=False,
    )

    assert result.ok is False
    assert result.chars_typed == 0
    assert result.notes is not None
    assert "confirmation_required" in result.notes

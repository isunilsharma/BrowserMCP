"""End-to-end smoke test: navigate → type_text → click → assert response.

Proves the MCP primitives compose into a real form submission against a local
Flask fixture. If this test passes, the wiring from
   tools.navigation.navigate → tools.interaction.type_text → tools.interaction.click
is intact for the happy-path "fill out a form" case that ~every team skill
will eventually need.
"""
from __future__ import annotations

import pytest

from browsermcp import state as state_mod
from browsermcp.config import Settings
from browsermcp.tools import click, navigate, type_text


pytestmark = pytest.mark.integration


@pytest.fixture
def _allow_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Temporarily widen the allow-list to include 127.0.0.1.

    navigate() blocks anything not on the configured allow-list; the
    production list doesn't include localhost (rightly so). We patch
    load_settings inside the navigation module so the override only
    affects this test.
    """
    test_settings = Settings(allowed_hosts=["127.0.0.1", "localhost"])

    def _patched_load_settings() -> Settings:
        return test_settings

    monkeypatch.setattr(
        "browsermcp.tools.navigation.load_settings", _patched_load_settings
    )


async def test_form_fill_round_trips_payload(
    fixture_site: str,
    browser_page,  # browser_use / Playwright Page from conftest
    _allow_localhost: None,
) -> None:
    """Filling the contact form yields the 'Thanks for your message' page.

    We assert on the full echo: the response page renders the email and
    message values back into the DOM, so this also verifies that type_text
    actually delivered the right characters (not just that something was
    typed and a button was clicked).
    """
    # Register the freshly-opened Page so navigate() / click() / type_text()
    # can resolve it via the get_page() lookup the tools use internally.
    await state_mod.register_window("test-form", browser_page)

    nav = await navigate(f"{fixture_site}/form", window_id="test-form")
    assert nav.title  # any non-empty title is fine — Flask returns "Contact"

    typed_email = await type_text(
        field="Email",
        text="qa@example.com",
        window_id="test-form",
    )
    assert typed_email.ok is True
    assert typed_email.chars_typed == len("qa@example.com")

    typed_message = await type_text(
        field="Message",
        text="hello from the integration suite",
        window_id="test-form",
    )
    assert typed_message.ok is True

    submitted = await click(description="Submit", window_id="test-form")
    assert submitted.ok is True

    # After the POST, the response page should be on screen. We read the
    # body text via the Page's evaluate() — same surface tools.reading uses.
    body_text = await browser_page.evaluate(
        "() => document.body ? document.body.innerText : ''"
    )
    assert "Thanks for your message" in body_text
    # Echo round-trip: confirms type_text really did deliver the payload.
    assert "qa@example.com" in body_text
    assert "hello from the integration suite" in body_text

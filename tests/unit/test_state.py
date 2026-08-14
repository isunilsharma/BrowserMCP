"""Tests for the cached CDP browser handle in browsermcp.state.

The scenario these pin down: the user quits and reopens Chrome mid-session.
The cached handle's websocket is dead, but it stayed in _state and every later
primitive failed with "Target page, context or browser has been closed" until
the whole MCP server was restarted.
"""

from __future__ import annotations

import pytest

from browsermcp import state


class FakeBrowser:
    """Stand-in for a Playwright Browser over CDP."""

    def __init__(self, connected: bool = True):
        self._connected = connected
        self.closed = False

    def is_connected(self) -> bool:
        return self._connected

    async def close(self) -> None:
        self.closed = True


class FakePlaywright:
    def __init__(self):
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def clean_state():
    """Each test owns the module-level state; restore it afterwards."""
    original = dict(state._state)
    state._state.update(
        browser=None, context=None, playwright=None, windows={}, recording_session=None
    )
    yield
    state._state.clear()
    state._state.update(original)


@pytest.fixture
def attach_recorder(monkeypatch):
    """Replace the real CDP attach with a counter, returning fresh handles."""
    calls: list[int] = []

    async def fake_attach(port: int):
        calls.append(port)
        browser = FakeBrowser()
        state._state["playwright"] = FakePlaywright()
        return browser

    monkeypatch.setattr(state, "_attach_via_playwright", fake_attach)
    return calls


async def test_live_handle_is_reused(attach_recorder):
    first = await state.get_or_attach(9222)
    second = await state.get_or_attach(9222)

    assert first is second
    assert len(attach_recorder) == 1, "a live handle must not trigger a re-attach"


async def test_dead_handle_triggers_reattach(attach_recorder):
    """The regression: Chrome restarted, so the cached websocket is dead."""
    original = await state.get_or_attach(9222)
    original._connected = False

    replacement = await state.get_or_attach(9222)

    assert replacement is not original
    assert replacement.is_connected()
    assert len(attach_recorder) == 2


async def test_force_replaces_a_live_handle(attach_recorder):
    original = await state.get_or_attach(9222)

    replacement = await state.get_or_attach(9222, force=True)

    assert replacement is not original
    assert len(attach_recorder) == 2


async def test_reattach_clears_connection_scoped_state(attach_recorder):
    """Windows and recording sessions hold Pages bound to the dead connection."""
    browser = await state.get_or_attach(9222)
    await state.register_window("w-1", object())
    await state.set_recording_session({"anchor": "w-1", "events": []})
    state._state["context"] = object()

    browser._connected = False
    await state.get_or_attach(9222)

    assert state._state["windows"] == {}
    assert state._state["recording_session"] is None
    assert state._state["context"] is None
    with pytest.raises(KeyError):
        await state.get_page("w-1")


async def test_reattach_stops_the_old_driver(attach_recorder):
    browser = await state.get_or_attach(9222)
    playwright = state._state["playwright"]

    browser._connected = False
    await state.get_or_attach(9222)

    assert playwright.stopped, "the old playwright driver process should be stopped"


async def test_reattach_never_closes_the_users_browser(attach_recorder):
    """We attach to Chrome we did not launch — tearing down must not quit it."""
    browser = await state.get_or_attach(9222)
    browser._connected = False

    await state.get_or_attach(9222)

    assert not browser.closed


async def test_teardown_failures_do_not_block_reattach(attach_recorder):
    """The connection is already presumed dead; stop() raising is expected."""

    async def boom():
        raise RuntimeError("driver already gone")

    browser = await state.get_or_attach(9222)
    browser._connected = False
    state._state["playwright"].stop = boom

    replacement = await state.get_or_attach(9222)

    assert replacement is not browser
    assert replacement.is_connected()


async def test_probe_raising_counts_as_dead(attach_recorder):
    browser = await state.get_or_attach(9222)

    def boom():
        raise RuntimeError("connection closed")

    browser.is_connected = boom

    replacement = await state.get_or_attach(9222)
    assert replacement is not browser


def test_handles_without_a_probe_are_assumed_live():
    """An unrecognised handle must behave exactly as it did before the check."""

    class Opaque:
        pass

    assert state._is_live(Opaque()) is True


def test_connected_attribute_is_honoured():
    class BrowserUseStyle:
        connected = False

    assert state._is_live(BrowserUseStyle()) is False

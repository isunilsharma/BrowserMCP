"""Shared fixtures for the integration test suite.

Two pieces of infrastructure live here:

1. `fixture_site` — a Flask app from tests/fixtures/site/app.py running on a
   random local port in a daemon thread for the duration of the test session.
   Tests get the base URL (e.g. `http://127.0.0.1:54321`) so they can compose
   their own paths.

2. `browser_page` — a real browser_use Page connected to a Chrome already
   running with `--remote-debugging-port=9222`. We deliberately do NOT spawn
   Chrome ourselves: the whole point of BrowserMCP is attaching to a teammate's
   real session. If no debug-Chrome is reachable the fixture skips the test.

Tests are slow (real browser) — every test that uses `browser_page` should also
carry `@pytest.mark.integration` so the fast unit-only run can filter them out.
"""
from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover - type-checker only
    from flask import Flask


def _find_free_port() -> int:
    """Ask the OS for an unused TCP port.

    Bind to port 0, read back what the kernel assigned, then close. There's a
    tiny race window before Flask binds — fine for a local test harness, not
    fine for anything load-bearing.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout_s: float = 5.0) -> None:
    """Block until something is accepting TCP on (host, port).

    Flask's dev server takes ~100ms to come up; polling beats sleeping a fixed
    amount of time because slow CI boxes can run several times longer.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"Fixture site never came up on {host}:{port} within {timeout_s}s")


@pytest.fixture(scope="session")
def fixture_site() -> Iterator[str]:
    """Run the Flask fixture app on a random localhost port for the whole session.

    Yields the base URL (e.g. `http://127.0.0.1:54321`). Tests build their own
    paths off this — keeps each test focused on its own route and avoids
    port-collision flakiness when xdist runs them in parallel.
    """
    pytest.importorskip("flask", reason="Flask is needed for the integration fixture site")
    from tests.fixtures.site.app import create_app

    app: Flask = create_app()
    port = _find_free_port()

    # Daemon thread → dies with the test process; no explicit shutdown needed.
    # Werkzeug's dev server is fine for fixtures and side-steps the
    # production-server import dance.
    def _run() -> None:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, daemon=True, name="fixture-site")
    thread.start()
    _wait_for_port("127.0.0.1", port)

    yield f"http://127.0.0.1:{port}"
    # Nothing to tear down — daemon thread + werkzeug dev server exit with
    # the test process. (werkzeug has no clean programmatic shutdown that
    # works across versions; for a fixture this is the pragmatic choice.)


@pytest.fixture
async def browser_page() -> AsyncIterator[object]:
    """Yield a fresh browser_use Page attached to the user's running Chrome.

    Skips the test cleanly if no Chrome is reachable on the debug port. This is
    the same path the real MCP server uses (state.get_or_attach) so we're
    actually exercising the integration surface, not a mock.
    """
    from browsermcp.config import load_settings
    from browsermcp.state import _state, get_or_attach

    settings = load_settings()
    port = settings.chrome_port

    # Probe the port before we even import Playwright — gives a much
    # friendlier skip message than letting connect_over_cdp time out.
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            pass
    except OSError:
        pytest.skip(
            f"No Chrome with --remote-debugging-port={port} reachable; "
            "start Chrome with `--remote-debugging-port=9222` to run integration tests"
        )

    browser = await get_or_attach(port)

    # Reuse whatever context already exists on the attached browser. The
    # integration tests open and close their own tabs via chrome_new_window
    # if they need isolation; we don't want to mutate the user's profile here.
    context = _state.get("context")
    if context is None and hasattr(browser, "contexts") and browser.contexts:
        context = browser.contexts[0]

    if context is None:
        pytest.skip("Attached browser has no usable context")

    page = await context.new_page()
    try:
        yield page
    finally:
        # Best-effort cleanup. If the test crashed Playwright the close call
        # may itself raise — swallow that so it doesn't mask the real error.
        try:
            await page.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _reset_browser_state() -> Iterator[None]:
    """Reset browsermcp.state between tests so stale handles don't wedge them.

    Two failure modes this guards against:

    1. Window registrations leak across tests — a stale `windows[id]` entry can
       wedge a later `get_page()` call in confusing ways.
    2. The cached `browser` and `context` handles are bound to the event loop
       that created them. pytest-asyncio gives each test a fresh event loop, so
       reusing the cached handles makes `context.new_page()` await a WebSocket
       on a dead loop — hangs until pytest-timeout fires. Nulling them forces
       `get_or_attach` to re-attach on the new loop, which is ~200 ms.
    """
    from browsermcp import state as state_mod

    saved_windows = dict(state_mod._state.get("windows", {}))
    state_mod._state["windows"] = {}
    state_mod._state["browser"] = None
    state_mod._state["context"] = None

    yield

    state_mod._state["windows"] = saved_windows

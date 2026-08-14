import asyncio
from typing import Any

_state: dict[str, Any] = {
    "browser": None,
    "context": None,
    # The async_playwright() driver handle backing "browser". Kept so a
    # re-attach can stop the old driver instead of leaking its node process.
    "playwright": None,
    "windows": {},
    # Active recording session: set by recording_capture.start_recording_session(),
    # cleared by stop_recording_session(). Holds the anchor window_id, all
    # currently-tracked page objects, and accumulated events across all tabs.
    "recording_session": None,
}
_lock = asyncio.Lock()


async def get_or_attach(port: int, timeout_s: float = 10.0, force: bool = False):
    """Attach to a running Chrome over CDP and cache the browser handle.

    Playwright is the primary path. browser-use 0.13.2's CDP client has a
    WebSocket-stability regression with Chrome 149+, so we use Playwright
    (a stable, mature CDP client) directly. Set BROWSERMCP_USE_BROWSER_USE=1 in
    the environment to force the browser-use path for testing.

    The cached handle is health-checked before it is handed back. When the user
    quits and reopens Chrome, the CDP websocket dies but the handle stays in
    _state; returning it made every later primitive fail with a confusing
    "Target page, context or browser has been closed" until the whole MCP server
    was restarted. A dead handle is now discarded and re-attached transparently.
    Pass force=True to discard a handle that still looks live.

    Raises stdlib TimeoutError if the attach doesn't complete within timeout_s.
    A hung attach blocks every other primitive, so the bound here is the
    most load-bearing one in the system.

    Set BROWSERMCP_DEBUG_CDP=1 to surface raw CDP traffic on stderr — useful
    when chasing a hang past the TimeoutError diagnostics.
    """
    import os

    if os.environ.get("BROWSERMCP_DEBUG_CDP") == "1":
        # Playwright's CDP client reads DEBUG via the `debug` lib at first log,
        # so setdefault before async_playwright().start() is enough to enable it
        # without clobbering a teammate's pre-set DEBUG value.
        os.environ.setdefault("DEBUG", "pw:protocol")

    async with _lock:
        if _state["browser"] is not None:
            if not force and _is_live(_state["browser"]):
                return _state["browser"]
            await _discard_browser_locked()

        if os.environ.get("BROWSERMCP_USE_BROWSER_USE") == "1":
            attach_coro = _attach_via_browser_use(port)
        else:
            attach_coro = _attach_via_playwright(port)

        try:
            browser = await asyncio.wait_for(attach_coro, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(
                f"CDP attach to 127.0.0.1:{port} did not complete within {timeout_s}s"
            ) from exc

        _state["browser"] = browser
        return browser


def _is_live(browser) -> bool:
    """Best-effort check that a cached browser handle still has a live connection.

    Playwright exposes a synchronous is_connected() that tracks the CDP
    websocket, which is exactly the signal we need: it flips to False when
    Chrome exits. We deliberately do not issue a CDP round-trip here — this
    runs on the hot path of every primitive, and a hung probe would reintroduce
    the very stall the timeout in get_or_attach exists to prevent.

    Anything we cannot interrogate is assumed live, so an unrecognised handle
    behaves exactly as it did before this check existed.
    """
    probe = getattr(browser, "is_connected", None)
    if callable(probe):
        try:
            result = probe()
        except Exception:
            return False
        # browser-use may expose this as a coroutine function; we can't await on
        # a sync path, so fall through to the attribute check below.
        if not asyncio.iscoroutine(result):
            return bool(result)
        result.close()

    connected = getattr(browser, "connected", None)
    if isinstance(connected, bool):
        return connected
    return True


async def _discard_browser_locked() -> None:
    """Drop the cached browser and everything scoped to its connection.

    Callers must already hold _lock. Registered windows hold Page objects bound
    to the dead connection, so they go too — otherwise get_page(window_id) would
    hand back a handle that raises on first use. Same for a recording session,
    whose tracked pages are equally dead; its buffered events cannot outlive the
    connection they were captured on.

    Note we deliberately do NOT call browser.close(). We attach to Chrome we did
    not launch, and over a CDP connection close() is not reliably a mere
    disconnect — quitting the user's real browser mid-session is a far worse
    outcome than a tidy teardown is worth. Stopping the driver drops the
    connection and reclaims the process that actually holds resources.
    """
    playwright = _state["playwright"]

    _state["browser"] = None
    _state["context"] = None
    _state["playwright"] = None
    _state["windows"] = {}
    _state["recording_session"] = None

    # Best-effort: the connection is already presumed dead, so a failure here is
    # expected and must not mask the re-attach that follows.
    if playwright is not None:
        try:
            await playwright.stop()
        except Exception:
            pass


async def _attach_via_browser_use(port: int):
    try:
        from browser_use import Browser
    except ImportError:
        return None

    browser = Browser(cdp_url=f"http://127.0.0.1:{port}")
    if hasattr(browser, "start"):
        await browser.start()
    elif hasattr(browser, "connect"):
        await browser.connect()
    return browser


async def _attach_via_playwright(port: int):
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    _state["playwright"] = pw
    browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    _state["context"] = browser.contexts[0] if browser.contexts else await browser.new_context()
    return browser


async def get_page(window_id: str | None = None):
    """Return the registered window's Page, or the most recently active one."""
    async with _lock:
        if window_id is not None:
            page = _state["windows"].get(window_id)
            if page is None:
                raise KeyError(f"window_id {window_id!r} is not registered")
            return page

        browser = _state["browser"]
        if browser is None:
            raise RuntimeError("Browser not attached; call chrome_attach first")

        context = _state["context"]
        if context is None and hasattr(browser, "contexts") and browser.contexts:
            context = browser.contexts[0]
            _state["context"] = context

        if context is not None and getattr(context, "pages", None):
            open_pages = [p for p in context.pages if not p.is_closed()]
            if open_pages:
                return open_pages[-1]

        if hasattr(browser, "get_current_page"):
            page = await browser.get_current_page()
            if page is None:
                raise RuntimeError("No active page; call chrome_new_window first")
            return page

        raise RuntimeError("No active page available")


async def register_window(window_id: str, page) -> None:
    """Track a freshly opened window under window_id."""
    async with _lock:
        _state["windows"][window_id] = page


async def unregister_window(window_id: str) -> None:
    """Forget a previously registered window."""
    async with _lock:
        _state["windows"].pop(window_id, None)


async def get_recording_session() -> dict | None:
    """Return the active recording session dict, or None if not recording."""
    async with _lock:
        return _state["recording_session"]


async def set_recording_session(session: dict | None) -> None:
    """Store or clear the active recording session."""
    async with _lock:
        _state["recording_session"] = session

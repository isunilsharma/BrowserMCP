import asyncio
from typing import Any

_state: dict[str, Any] = {
    "browser": None,
    "context": None,
    "windows": {},
    # Active recording session: set by recording_capture.start_recording_session(),
    # cleared by stop_recording_session(). Holds the anchor window_id, all
    # currently-tracked page objects, and accumulated events across all tabs.
    "recording_session": None,
}
_lock = asyncio.Lock()


async def get_or_attach(port: int, timeout_s: float = 10.0):
    """Attach to a running Chrome over CDP and cache the browser handle.

    Playwright is the primary path. browser-use 0.13.2's CDP client has a
    WebSocket-stability regression with Chrome 149+, so we use Playwright
    (a stable, mature CDP client) directly. Set BROWSERMCP_USE_BROWSER_USE=1 in
    the environment to force the browser-use path for testing.

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
            return _state["browser"]

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

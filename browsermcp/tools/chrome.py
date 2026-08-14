"""Primitives for attaching to and managing windows in a local Chrome via CDP."""

from __future__ import annotations

import asyncio
import fnmatch
import uuid

from ..models import AttachResult, WindowRef
from ..state import (
    get_or_attach,
    get_page,
    register_window,
    unregister_window,
)


async def chrome_attach(port: int = 9222) -> AttachResult:
    """Attach to a running Chrome over CDP at the given debug port."""
    browser = await get_or_attach(port)

    profile_name = _profile_name(browser)
    context_id = _context_id(browser)
    pages_open = await _count_pages(browser)

    return AttachResult(
        profile_name=profile_name,
        context_id=context_id,
        pages_open=pages_open,
    )


async def chrome_new_window() -> WindowRef:
    """Open a new top-level browser window and register it for later use."""
    browser = await get_or_attach(_default_port())
    page = await _open_new_window(browser)
    window_id = f"w-{uuid.uuid4().hex[:8]}"
    await register_window(window_id, page)
    return WindowRef(window_id=window_id)


async def chrome_find_or_open_window(url_pattern: str) -> WindowRef:
    """Find an existing browser tab whose URL matches url_pattern, registering and
    returning it. If no tab matches, open a fresh window instead.

    Matching is permissive: a tab matches when url_pattern appears as a substring
    in the tab's URL, or when fnmatch glob-matches it. This is the right primitive
    for "use the already-signed-in Power BI tab" — Single-Page Apps like Power BI
    keep their session tokens in sessionStorage, which is per-window, so reusing
    the existing signed-in window avoids forcing a fresh SSO bootstrap.
    """
    browser = await get_or_attach(_default_port())
    pages = await _list_all_pages(browser)
    for page in pages:
        url = await _page_url(page)
        if not url:
            continue
        if url_pattern in url or fnmatch.fnmatch(url, url_pattern):
            window_id = f"w-{uuid.uuid4().hex[:8]}"
            await register_window(window_id, page)
            return WindowRef(window_id=window_id)
    new_page = await _open_new_window(browser)
    window_id = f"w-{uuid.uuid4().hex[:8]}"
    await register_window(window_id, new_page)
    return WindowRef(window_id=window_id)


async def chrome_close_window(window_id: str) -> None:
    """Close a previously opened window and forget its registration."""
    page = await get_page(window_id)
    browser = await get_or_attach(_default_port())
    await _close_page(browser, page)
    await unregister_window(window_id)


def _default_port() -> int:
    from ..config import load_settings

    return load_settings().chrome_port


def _profile_name(browser) -> str:
    profile = getattr(browser, "browser_profile", None)
    if profile is not None:
        user_data_dir = getattr(profile, "user_data_dir", None)
        if user_data_dir:
            return str(user_data_dir).rsplit("/", 1)[-1]
        name = getattr(profile, "name", None)
        if name:
            return str(name)
    return "default"


def _context_id(browser) -> str:
    for attr in ("id", "_id", "session_id"):
        value = getattr(browser, attr, None)
        if value:
            return str(value)
    contexts = getattr(browser, "contexts", None)
    if contexts:
        first = contexts[0]
        for attr in ("id", "_id"):
            value = getattr(first, attr, None)
            if value:
                return str(value)
    return "default"


async def _count_pages(browser) -> int:
    if hasattr(browser, "get_pages"):
        pages = await browser.get_pages()
        return len(pages)
    if hasattr(browser, "get_tabs"):
        tabs = await browser.get_tabs()
        return len(tabs)
    contexts = getattr(browser, "contexts", None)
    if contexts:
        return sum(len(getattr(ctx, "pages", []) or []) for ctx in contexts)
    return 0


async def _open_new_window(browser):
    if hasattr(browser, "_cdp_create_new_page"):
        target_id = await browser._cdp_create_new_page(
            url="about:blank", new_window=True
        )
        try:
            from browser_use.actor.page import Page as Target
        except ImportError as e:
            raise ImportError(
                "browser_use not installed - run 'uv sync'"
            ) from e
        return Target(browser, target_id)
    if hasattr(browser, "new_page"):
        return await browser.new_page()
    contexts = getattr(browser, "contexts", None)
    if contexts:
        context = contexts[0]
        if hasattr(context, "new_page"):
            return await context.new_page()
    raise RuntimeError("Browser does not expose a way to open a new window")


async def _close_page(browser, page) -> None:
    if hasattr(browser, "close_page"):
        await browser.close_page(page)
        return
    if hasattr(page, "close"):
        await page.close()
        return
    raise RuntimeError("Page object does not support close()")


async def _list_all_pages(browser) -> list:
    """Return every page/tab the browser currently knows about."""
    if hasattr(browser, "get_pages"):
        return list(await browser.get_pages())
    if hasattr(browser, "get_tabs"):
        return list(await browser.get_tabs())
    contexts = getattr(browser, "contexts", None)
    if contexts:
        return [p for ctx in contexts for p in (getattr(ctx, "pages", []) or [])]
    return []


async def _page_url(page) -> str:
    """Read a page's current URL, handling both browser_use and Playwright Pages."""
    if hasattr(page, "get_url"):
        return await page.get_url() or ""
    url_attr = getattr(page, "url", None)
    if callable(url_attr):
        result = url_attr()
        if asyncio.iscoroutine(result):
            return (await result) or ""
        return result or ""
    if isinstance(url_attr, str):
        return url_attr
    return ""

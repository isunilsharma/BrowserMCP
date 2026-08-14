from __future__ import annotations

import asyncio
import time
from typing import Literal

from ..config import host_allowed, load_settings
from ..models import NavigateResult, ScrollResult
from ..state import get_page

try:
    from playwright.async_api import TimeoutError as _PlaywrightTimeoutError
except ImportError:  # pragma: no cover - playwright is in [project.dependencies]
    _PlaywrightTimeoutError = asyncio.TimeoutError


def _require_browser_use() -> None:
    try:
        import browser_use  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "browser_use not installed - run 'uv sync'"
        ) from exc


async def navigate(
    url: str,
    window_id: str | None = None,
    timeout_s: float = 15.0,
) -> NavigateResult:
    """Navigate the active or named window to url after host allow-list check.

    Raises stdlib TimeoutError with the page's readyState + current URL in the
    message if goto doesn't complete within timeout_s. The outer asyncio.wait_for
    is a backstop: under Chrome 149+ we've observed page.goto's own timeout fail
    to fire when the CDP Page.navigate command never resolves.
    """
    _require_browser_use()
    settings = load_settings()
    if not host_allowed(url, settings):
        raise ValueError(
            f"URL {url!r} is not on the allowed-hosts list; "
            f"allowed patterns: {settings.allowed_hosts}"
        )

    page = await get_page(window_id)
    started_at = time.monotonic()

    try:
        if hasattr(page, "goto"):
            await asyncio.wait_for(
                page.goto(
                    url,
                    timeout=int(timeout_s * 1000),
                    wait_until="domcontentloaded",
                ),
                timeout=timeout_s + 2.0,
            )
        elif hasattr(page, "navigate"):
            await asyncio.wait_for(page.navigate(url), timeout=timeout_s)
        else:
            raise RuntimeError("Page object has no goto/navigate method")
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        diagnostic = await _navigate_diagnostic(page)
        raise TimeoutError(
            f"navigate to {url!r} did not complete within {timeout_s}s "
            f"(elapsed={elapsed_ms}ms); {diagnostic}"
        ) from exc

    title = await _page_title(page)
    final_url = await _page_url(page)
    return NavigateResult(title=title, url=final_url)


async def _navigate_diagnostic(page) -> str:
    """Best-effort capture of readyState + URL for a TimeoutError message.

    Each probe is bounded so a hung page can't swallow the original error.
    """
    try:
        url = await asyncio.wait_for(_page_url(page), timeout=1.0)
    except Exception:
        url = "<unknown>"
    try:
        ready = await asyncio.wait_for(
            _evaluate(page, "() => document.readyState"),
            timeout=1.0,
        )
    except Exception:
        ready = "<unknown>"
    return f"readyState={ready!r}, current url={url!r}"


async def wait_for(
    condition: str,
    timeout_s: int = 30,
    window_id: str | None = None,
) -> None:
    """Wait for a load-state keyword, selector, or substring in the page text."""
    page = await get_page(window_id)

    load_states = {"load", "domcontentloaded", "networkidle"}
    if condition in load_states:
        await _wait_for_load_state(page, condition, timeout_s)
        return

    if _looks_like_selector(condition):
        await _wait_for_selector(page, condition, timeout_s)
        return

    await _wait_for_text(page, condition, timeout_s)


async def scroll(
    direction: Literal["up", "down", "top", "bottom"],
    amount: int = 500,
    window_id: str | None = None,
) -> ScrollResult:
    """Scroll the page in the given direction by amount pixels (or to an edge)."""
    page = await get_page(window_id)

    if direction == "up":
        delta = -amount
        await _evaluate(page, "(d) => window.scrollBy(0, d)", delta)
        pixels = amount
    elif direction == "down":
        delta = amount
        await _evaluate(page, "(d) => window.scrollBy(0, d)", delta)
        pixels = amount
    elif direction == "top":
        await _evaluate(page, "() => window.scrollTo(0, 0)")
        pixels = 0
    elif direction == "bottom":
        await _evaluate(page, "() => window.scrollTo(0, document.body.scrollHeight)")
        pixels = 0
    else:
        raise ValueError(f"Unknown scroll direction: {direction!r}")

    return ScrollResult(direction=direction, pixels=pixels)


async def _page_title(page) -> str:
    if hasattr(page, "get_title"):
        return await page.get_title()
    title_attr = getattr(page, "title", None)
    if callable(title_attr):
        result = title_attr()
        if asyncio.iscoroutine(result):
            return await result
        return result or ""
    return ""


async def _page_url(page) -> str:
    if hasattr(page, "get_url"):
        return await page.get_url()
    url_attr = getattr(page, "url", None)
    if callable(url_attr):
        result = url_attr()
        if asyncio.iscoroutine(result):
            return await result
        return result or ""
    if isinstance(url_attr, str):
        return url_attr
    return ""


def _looks_like_selector(condition: str) -> bool:
    stripped = condition.strip()
    if not stripped:
        return False
    return stripped[0] in {"#", ".", "[", ":"} or stripped.startswith(("//", "xpath="))


async def _wait_for_load_state(page, state: str, timeout_s: int) -> None:
    """Poll document.readyState until it matches the requested load state."""
    # browser_use Page has no wait_for_load_state; poll readyState instead.
    # 'load' / 'networkidle' -> wait for 'complete'; 'domcontentloaded' -> 'interactive' or 'complete'.
    targets = {"complete"} if state in {"load", "networkidle"} else {"interactive", "complete"}
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        ready = await _evaluate(page, "() => document.readyState")
        if ready in targets:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for load state {state!r} after {timeout_s}s")


async def _wait_for_selector(page, selector: str, timeout_s: int) -> None:
    """Poll the DOM via page.evaluate until the selector matches at least one element."""
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        # Return a primitive boolean (evaluate stringifies it) rather than a DOM node.
        found = await _evaluate(
            page,
            "(sel) => !!document.querySelector(sel)",
            selector,
        )
        # evaluate() returns strings: 'True'/'False' from str(bool) or 'true'/'false' from json.dumps.
        if str(found).lower() in {"true", "1"}:
            return
        await asyncio.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for selector {selector!r} after {timeout_s}s")


async def _wait_for_text(page, needle: str, timeout_s: int) -> None:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        text = await _page_text(page)
        if needle in text:
            return
        await asyncio.sleep(0.25)
    raise TimeoutError(f"Timed out waiting for {needle!r} after {timeout_s}s")


async def _page_text(page) -> str:
    """Return document.body.innerText via page.evaluate (browser_use has no .content())."""
    if hasattr(page, "evaluate"):
        return await page.evaluate(
            "() => document.body ? document.body.innerText : ''"
        )
    return ""


async def _evaluate(page, script: str, *args):
    """Evaluate a JS arrow-function string on the page; passes args through to evaluate()."""
    if hasattr(page, "evaluate"):
        return await page.evaluate(script, *args)
    raise RuntimeError("Page object has no evaluate method")

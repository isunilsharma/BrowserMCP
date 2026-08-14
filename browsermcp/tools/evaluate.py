from __future__ import annotations

import asyncio
from typing import Any, Literal

from ..models import EvaluateResult
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


_SERIALIZABLE = (str, int, float, bool, type(None))


def _coerce(value: Any, depth: int = 0) -> Any:
    """Best-effort coercion of Playwright's evaluate() output into JSON-safe values.

    Playwright already returns Python-native primitives for JS scalars, dicts for
    JS objects, and lists for JS arrays. This wrapper caps recursion depth and
    stringifies anything that slips through (e.g., JSHandle for un-serializable
    values like DOM nodes).
    """
    if depth > 8:
        return repr(value)[:500]
    if isinstance(value, _SERIALIZABLE):
        return value
    if isinstance(value, dict):
        return {str(k): _coerce(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce(v, depth + 1) for v in value]
    return repr(value)[:500]


async def _resolve_target(page: Any, frame: str | None):
    if not frame:
        return page
    if hasattr(page, "wait_for_selector"):
        element = await page.wait_for_selector(frame, timeout=5000)
        if element is not None and hasattr(element, "content_frame"):
            content = await element.content_frame()
            if content is not None:
                return content
    return page


async def page_evaluate(
    js: str,
    window_id: str | None = None,
    frame: str | None = None,
    confirm_intent: Literal["read", "write", "destructive"] = "read",
    confirmed: bool = False,
    timeout_s: float = 10.0,
) -> EvaluateResult:
    """Evaluate a JavaScript expression against the active page (or a frame) and return its result.

    The js argument must be a JS EXPRESSION (arrow function or bare expression),
    not a statement — Playwright's evaluate() will implicitly return the value.
    Example valid inputs:
        "() => window.location.href"
        "1 + 2"
        "() => Array.from(document.querySelectorAll('a')).map(a => a.href)"

    For write or destructive intents (any code that mutates DOM, navigates,
    posts data, etc.), the caller must pass confirmed=True. This is a strong
    primitive — anything JS can do, this can do — so gating writes matches the
    click/type_text pattern.

    When frame is provided, the expression evaluates inside that iframe's
    content frame instead of the top-level page.

    Raises stdlib TimeoutError if evaluation doesn't complete within timeout_s.
    """
    if confirm_intent in ("write", "destructive") and not confirmed:
        return EvaluateResult(
            ok=False,
            result=None,
            notes=(
                f"confirmation_required: this is a {confirm_intent} action; "
                "caller must re-invoke with confirmed=True"
            ),
        )

    _require_browser_use()
    page = await get_page(window_id)

    try:
        target = await asyncio.wait_for(_resolve_target(page, frame), timeout=timeout_s)
        raw = await asyncio.wait_for(target.evaluate(js), timeout=timeout_s)
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"page_evaluate did not complete within {timeout_s}s"
        ) from exc

    return EvaluateResult(ok=True, result=_coerce(raw), notes=None)


__all__ = ["page_evaluate"]

from __future__ import annotations

import asyncio
from typing import Literal

from ..models import ClickResult, TypeResult
from ..redact import SENSITIVE_FIELD_RE as _SENSITIVE_FIELD_RE
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


async def click(
    description: str,
    window_id: str | None = None,
    confirm_intent: Literal["read", "write", "destructive"] = "read",
    confirmed: bool = False,
    timeout_s: float = 10.0,
    force: bool = False,
    frame: str | None = None,
    real_mouse: bool = False,
) -> ClickResult:
    """Click the element best matching description by accessible name, role, or label.

    For write/destructive intents, the caller must pass confirmed=True to actually
    perform the click. Otherwise, no click is performed and the result indicates
    that confirmation is required.

    Raises stdlib TimeoutError if the click doesn't resolve within timeout_s.
    """
    if confirm_intent in ("write", "destructive") and not confirmed:
        return ClickResult(
            description=description,
            ok=False,
            notes=(
                f"confirmation_required: this is a {confirm_intent} action; "
                "caller must re-invoke with confirmed=True"
            ),
        )

    _require_browser_use()
    page = await get_page(window_id)

    handler = _resolve_handler(page)
    try:
        notes = await asyncio.wait_for(
            handler.click(description, timeout_s=timeout_s, force=force, frame=frame, real_mouse=real_mouse),
            timeout=timeout_s + 2.0,
        )
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"click on {description!r} did not complete within {timeout_s}s"
        ) from exc
    return ClickResult(description=description, ok=True, notes=notes)


async def type_text(
    field: str,
    text: str,
    window_id: str | None = None,
    confirm_intent: Literal["read", "write", "destructive"] = "read",
    confirmed: bool = False,
    timeout_s: float = 10.0,
    frame: str | None = None,
) -> TypeResult:
    """Focus the form field matching field and type text into it.

    For sensitive fields (password/pin/secret) and write/destructive intents, the
    caller must pass confirmed=True. Otherwise no input is performed and the
    result indicates that confirmation is required.

    Raises stdlib TimeoutError if the type doesn't resolve within timeout_s.
    """
    is_sensitive = bool(_SENSITIVE_FIELD_RE.search(field))
    needs_confirmation = is_sensitive or confirm_intent in ("write", "destructive")

    if needs_confirmation and not confirmed:
        effective_intent = confirm_intent if confirm_intent != "read" else "write"
        reason = "sensitive field" if is_sensitive else f"{effective_intent} action"
        return TypeResult(
            field=field,
            chars_typed=0,
            ok=False,
            notes=(
                f"confirmation_required: this is a {effective_intent} action ({reason}); "
                "caller must re-invoke with confirmed=True"
            ),
        )

    _require_browser_use()
    page = await get_page(window_id)

    handler = _resolve_handler(page)
    try:
        await asyncio.wait_for(
            handler.type_text(field, text, timeout_s=timeout_s, frame=frame),
            timeout=timeout_s + 2.0,
        )
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"type_text into {field!r} did not complete within {timeout_s}s"
        ) from exc
    return TypeResult(field=field, chars_typed=len(text), ok=True)


def _resolve_handler(page) -> "_Handler":
    if _looks_like_playwright(page):
        return _PlaywrightHandler(page)
    return _BrowserUseHandler(page)


def _looks_like_playwright(page) -> bool:
    return all(hasattr(page, attr) for attr in ("get_by_role", "get_by_label", "get_by_text"))


class _Handler:
    async def click(
        self,
        description: str,
        timeout_s: float = 10.0,
        force: bool = False,
        frame: str | None = None,
        real_mouse: bool = False,
    ) -> str | None:
        raise NotImplementedError

    async def type_text(
        self,
        field: str,
        text: str,
        timeout_s: float = 10.0,
        frame: str | None = None,
    ) -> None:
        raise NotImplementedError


class _PlaywrightHandler(_Handler):
    def __init__(self, page) -> None:
        self._page = page

    async def click(
        self,
        description: str,
        timeout_s: float = 10.0,
        force: bool = False,
        frame: str | None = None,
        real_mouse: bool = False,
    ) -> str | None:
        locator, note = await self._best_locator(description, for_input=False, frame=frame)
        url_before = self._page.url
        try:
            sig_before = await self._page.evaluate(
                "() => (document.title || '') + '||' + ((document.querySelector('h1') && document.querySelector('h1').innerText) || '')"
            )
        except Exception:
            sig_before = ""
        if real_mouse:
            try:
                await locator.scroll_into_view_if_needed(timeout=int(timeout_s * 1000))
            except Exception:
                pass
            box = await locator.bounding_box()
            if box is None:
                raise RuntimeError(
                    f"Could not resolve bounding box for {description!r} — element may not be laid out"
                )
            x = box["x"] + box["width"] / 2
            y = box["y"] + box["height"] / 2
            await self._page.mouse.click(x, y)
            note = f"{note} (real_mouse @ {int(x)},{int(y)})"
        else:
            await locator.click(timeout=int(timeout_s * 1000), force=force)
        try:
            await self._page.wait_for_function(
                "([u, s]) => location.href !== u || ((document.title || '') + '||' + ((document.querySelector('h1') && document.querySelector('h1').innerText) || '')) !== s",
                arg=[url_before, sig_before],
                timeout=1500,
            )
            return note
        except _PlaywrightTimeoutError:
            return f"{note} (warning: no state change detected)"

    async def type_text(
        self,
        field: str,
        text: str,
        timeout_s: float = 10.0,
        frame: str | None = None,
    ) -> None:
        locator, _ = await self._best_locator(field, for_input=True, frame=frame)
        timeout_ms = int(timeout_s * 1000)
        if hasattr(locator, "fill"):
            await locator.fill(text, timeout=timeout_ms)
        else:
            await locator.click(timeout=timeout_ms)
            await self._page.keyboard.type(text)

    async def _best_locator(
        self,
        description: str,
        for_input: bool,
        frame: str | None = None,
    ):
        root = self._page.frame_locator(frame) if frame else self._page

        candidates: list[tuple[str, object]] = []
        if for_input:
            candidates.append(("get_by_label", root.get_by_label(description, exact=False)))
            candidates.append(
                (
                    "get_by_role(textbox)",
                    root.get_by_role("textbox", name=description),
                )
            )
            candidates.append(
                (
                    "get_by_placeholder",
                    root.get_by_placeholder(description),
                )
            )
        else:
            for role in ("link", "menuitem", "treeitem", "tab", "button", "option", "checkbox", "radio"):
                candidates.append(
                    (f"get_by_role({role})", root.get_by_role(role, name=description))
                )
            candidates.append(("get_by_label", root.get_by_label(description, exact=False)))
            candidates.append(("get_by_text", root.get_by_text(description, exact=False)))

        last_error: Exception | None = None
        for note, locator in candidates:
            try:
                count = await locator.count()
            except Exception as exc:
                last_error = exc
                continue
            if count == 0:
                continue
            for i in range(count):
                candidate = locator.nth(i)
                try:
                    if await candidate.is_visible():
                        return candidate, note
                except Exception:
                    continue
            # no visible match for this role; continue to next candidate

        if last_error is not None:
            raise RuntimeError(
                f"No element matched {description!r}; last locator error: {last_error}"
            )
        raise RuntimeError(f"No visible element matched {description!r}")


class _BrowserUseHandler(_Handler):
    def __init__(self, page) -> None:
        self._page = page

    async def click(
        self,
        description: str,
        timeout_s: float = 10.0,
        force: bool = False,
        frame: str | None = None,
        real_mouse: bool = False,
    ) -> str | None:
        # browser-use path: force/frame/real_mouse not supported here; kwargs
        # accepted for signature compat with _PlaywrightHandler.
        element, note = await self._resolve_element(description, for_input=False)
        await element.click()
        return note

    async def type_text(
        self,
        field: str,
        text: str,
        timeout_s: float = 10.0,
        frame: str | None = None,
    ) -> None:
        element, _ = await self._resolve_element(field, for_input=True)
        if hasattr(element, "fill"):
            await element.fill(text)
            return
        if hasattr(element, "focus"):
            await element.focus()
        if hasattr(self._page, "keyboard"):
            await self._page.keyboard.type(text)
            return
        raise RuntimeError("browser_use element does not support text input")

    async def _resolve_element(self, description: str, for_input: bool):
        selectors = _candidate_selectors(description, for_input=for_input)

        if hasattr(self._page, "get_elements_by_css_selector"):
            for note, selector in selectors:
                elements = await self._page.get_elements_by_css_selector(selector)
                if elements:
                    return elements[0], note

        raise RuntimeError(
            f"Could not resolve element matching {description!r} via browser_use page"
        )


def _candidate_selectors(description: str, for_input: bool) -> list[tuple[str, str]]:
    safe = description.replace('"', '\\"')
    if for_input:
        return [
            ("input[aria-label]", f'input[aria-label*="{safe}" i]'),
            ("input[name]", f'input[name*="{safe}" i]'),
            ("input[placeholder]", f'input[placeholder*="{safe}" i]'),
            ("textarea[aria-label]", f'textarea[aria-label*="{safe}" i]'),
        ]
    return [
        ("[aria-label]", f'[aria-label*="{safe}" i]'),
        ("button[name]", f'button[name*="{safe}" i]'),
        ("a[title]", f'a[title*="{safe}" i]'),
    ]


__all__ = ["click", "type_text"]

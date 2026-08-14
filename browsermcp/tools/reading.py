from __future__ import annotations

import asyncio
import base64
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import browser_use  # noqa: F401

    _BROWSER_USE_IMPORT_ERROR: ImportError | None = None
except ImportError as exc:  # pragma: no cover
    _BROWSER_USE_IMPORT_ERROR = ImportError(
        "browser_use not installed -- run 'uv sync'"
    )
    _BROWSER_USE_IMPORT_ERROR.__cause__ = exc

try:
    from playwright.async_api import TimeoutError as _PlaywrightTimeoutError
except ImportError:  # pragma: no cover - playwright is in [project.dependencies]
    _PlaywrightTimeoutError = asyncio.TimeoutError

from ..config import RUNS_DIR, ensure_dirs
from ..models import BBox, Element, PageReadResult, ScreenshotResult
from ..state import get_page


def _require_browser_use() -> None:
    if _BROWSER_USE_IMPORT_ERROR is not None:
        raise _BROWSER_USE_IMPORT_ERROR


SCREENSHOT_DIR = RUNS_DIR / "screenshots"


async def read_page(
    viewport_only: bool = True,
    window_id: str | None = None,
    timeout_s: float = 10.0,
    frame: str | None = None,
) -> PageReadResult:
    """Read the active page: title, url, visible text, interactable elements, a11y tree.

    When frame is provided (a CSS selector for an iframe element), reads target
    that iframe's content document instead of the top-level page. Required for
    Power BI / embedded reports whose content lives inside <iframe>.

    Raises stdlib TimeoutError if the read doesn't complete within timeout_s.
    """
    _require_browser_use()
    page = await get_page(window_id)
    try:
        target = await asyncio.wait_for(_resolve_read_target(page, frame), timeout=timeout_s)
        return await asyncio.wait_for(_read_page_impl(target), timeout=timeout_s)
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"read_page did not complete within {timeout_s}s"
        ) from exc


async def _read_page_impl(page: Any) -> PageReadResult:
    title = await _get_title(page)
    url = await _get_url(page)
    text = await _get_visible_text(page)
    tree = await _get_accessibility_tree(page)
    elements = _elements_from_tree(tree)
    links = await _get_links(page)
    return PageReadResult(
        title=title,
        url=url,
        text=text,
        elements=elements,
        accessibility_tree=tree,
        links=links,
    )


async def _get_links(page: Any) -> list[dict]:
    """Return a list of {text, href} for every anchor on the page.

    Trims whitespace, drops empty-text/empty-href entries, dedupes by (text, href).
    For SPA nav discovery (e.g., Power BI Apps), href-based navigate() is far more
    reliable than clicking through the app's custom router.
    """
    if not hasattr(page, "evaluate"):
        return []
    try:
        raw = await page.evaluate(
            "() => Array.from(document.querySelectorAll('a')).map(a => ({text: (a.innerText || a.textContent || '').trim().slice(0, 200), href: a.href || ''})).filter(x => x.text && x.href)"
        )
    except Exception:
        return []
    seen = set()
    out: list[dict] = []
    for item in raw or []:
        key = (item.get("text", ""), item.get("href", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": item.get("text", ""), "href": item.get("href", "")})
    return out


async def _resolve_read_target(page: Any, frame: str | None):
    """If frame selector is provided, return the iframe's content Frame; else the page."""
    if not frame:
        return page
    if hasattr(page, "wait_for_selector"):
        element = await page.wait_for_selector(frame, timeout=5000)
        if element is not None and hasattr(element, "content_frame"):
            content = await element.content_frame()
            if content is not None:
                return content
    return page


async def screenshot(
    full_page: bool = False,
    window_id: str | None = None,
    timeout_s: float = 30.0,
) -> ScreenshotResult:
    """Save a PNG screenshot of the active page and return its absolute path.

    Raises stdlib TimeoutError if capture doesn't complete within timeout_s.
    Full-page captures of long pages can take >10s, so the default here is
    higher than the other read primitives.
    """
    _require_browser_use()
    page = await get_page(window_id)

    ensure_dirs()
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    path = SCREENSHOT_DIR / f"{timestamp}.png"

    try:
        await asyncio.wait_for(
            _capture_screenshot(page, path, full_page), timeout=timeout_s
        )
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"screenshot did not complete within {timeout_s}s"
        ) from exc

    return ScreenshotResult(path=str(path.resolve()))


async def _get_title(page: Any) -> str:
    # browser_use Page: async method get_title()
    if hasattr(page, "get_title"):
        return await page.get_title()
    # Playwright Page: callable .title() returning awaitable
    title_attr = getattr(page, "title", None)
    if callable(title_attr):
        result = title_attr()
        if asyncio.iscoroutine(result):
            return await result
        return result or ""
    return ""


async def _get_url(page: Any) -> str:
    # browser_use Page: async method get_url() -- NOT an attribute
    if hasattr(page, "get_url"):
        return await page.get_url()
    # Playwright Page: .url is a sync string attribute
    url_attr = getattr(page, "url", None)
    if callable(url_attr):
        result = url_attr()
        if asyncio.iscoroutine(result):
            return await result
        return result or ""
    if isinstance(url_attr, str):
        return url_attr
    return ""


async def _get_visible_text(page: Any) -> str:
    # Playwright-style helper
    if hasattr(page, "inner_text"):
        try:
            return await page.inner_text("body")
        except Exception:
            pass
    # browser_use Page.evaluate requires arrow-function form
    if hasattr(page, "evaluate"):
        return await page.evaluate(
            "() => document.body ? document.body.innerText : ''"
        )
    return ""


async def _get_accessibility_tree(page: Any) -> dict:
    """Return a dict-shaped accessibility/DOM tree representation.

    For browser_use Pages we serialize via DomService and emit a flat
    children list of interactable elements (selector_map values). For
    Playwright pages we fall back to the native accessibility snapshot.
    """
    # browser_use Page path: use the DOM serializer.
    if hasattr(page, "dom_service") and hasattr(page, "_browser_session"):
        try:
            session = page._browser_session
            target_id = getattr(page, "_target_id", None)
            # Make sure the session is focused on this target so
            # get_serialized_dom_tree's assertion holds.
            if target_id is not None:
                session.agent_focus_target_id = target_id
            dom_service = page.dom_service
            serialized_state, _enhanced_root, _timing = (
                await dom_service.get_serialized_dom_tree()
            )
            return _serialized_dom_to_dict(serialized_state)
        except Exception:
            # Fall through to playwright snapshot if available.
            pass

    # Playwright path: page.accessibility.snapshot()
    a11y = getattr(page, "accessibility", None)
    if a11y is not None and hasattr(a11y, "snapshot"):
        snapshot = await a11y.snapshot(interesting_only=False)
        if snapshot is None:
            return {}
        if isinstance(snapshot, dict):
            return snapshot
        return dict(snapshot)
    return {}


def _serialized_dom_to_dict(serialized_state: Any) -> dict:
    """Convert browser_use SerializedDOMState into a simple a11y-tree dict.

    Output shape mirrors the Playwright snapshot enough for
    _elements_from_tree to walk it: a root with a `children` list of
    {role, name, focusable, hidden, boundingBox} dicts derived from
    each interactable node in selector_map.
    """
    selector_map = getattr(serialized_state, "selector_map", None) or {}
    children: list[dict] = []
    for index, node in selector_map.items():
        ax_node = getattr(node, "ax_node", None)
        role = ""
        name = ""
        if ax_node is not None:
            role = getattr(ax_node, "role", "") or ""
            name = getattr(ax_node, "name", "") or ""
        if not role:
            role = getattr(node, "tag_name", "") or ""

        snapshot_node = getattr(node, "snapshot_node", None)
        bounds = getattr(snapshot_node, "bounds", None) if snapshot_node else None
        bbox_dict: dict | None = None
        if bounds is not None:
            bbox_dict = {
                "x": getattr(bounds, "x", 0),
                "y": getattr(bounds, "y", 0),
                "width": getattr(bounds, "width", 0),
                "height": getattr(bounds, "height", 0),
            }

        is_visible = getattr(node, "is_visible", True)
        children.append(
            {
                "ref_index": index,
                "role": str(role),
                "name": str(name),
                "focusable": True,
                "hidden": not bool(is_visible) if is_visible is not None else False,
                "boundingBox": bbox_dict,
                "children": [],
            }
        )

    return {"role": "WebArea", "name": "", "children": children}


def _elements_from_tree(tree: dict) -> list[Element]:
    elements: list[Element] = []
    if not tree:
        return elements

    counter = {"n": 0}

    def walk(node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return

        role = node.get("role", "")
        name = node.get("name", "") or ""

        if _is_interactable(role, node):
            counter["n"] += 1
            # Prefer the selector_map index for browser_use trees so the
            # ref stays stable across reads in the same session.
            ref_index = node.get("ref_index")
            ref = f"a11y-{ref_index}" if ref_index is not None else f"a11y-{counter['n']}"
            elements.append(
                Element(
                    ref=ref,
                    role=role,
                    name=str(name),
                    visible=not bool(node.get("hidden", False)),
                    bounding_box=_bbox_from_node(node),
                )
            )

        for i, child in enumerate(node.get("children", []) or []):
            walk(child, f"{path}/{i}")

    walk(tree, "")
    return elements


def _is_interactable(role: str, node: dict) -> bool:
    interactable_roles = {
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "menuitem",
        "tab",
        "switch",
        "searchbox",
        "slider",
        "spinbutton",
        "listbox",
        "option",
    }
    if role in interactable_roles:
        return True
    if node.get("focusable") and not node.get("disabled"):
        return True
    return False


def _bbox_from_node(node: dict) -> BBox | None:
    box = node.get("boundingBox") or node.get("bounding_box")
    if not isinstance(box, dict):
        return None
    try:
        return BBox(
            x=int(box.get("x", 0)),
            y=int(box.get("y", 0)),
            w=int(box.get("width", box.get("w", 0))),
            h=int(box.get("height", box.get("h", 0))),
        )
    except (TypeError, ValueError):
        return None


async def _capture_screenshot(page: Any, path: Path, full_page: bool) -> None:
    # Preferred path for browser_use: session-level take_screenshot
    # supports `path=` and `full_page=`, and returns bytes.
    session = getattr(page, "_browser_session", None)
    if session is not None and hasattr(session, "take_screenshot"):
        try:
            data = await session.take_screenshot(
                path=str(path), full_page=full_page, format="png"
            )
            if not path.exists() and isinstance(data, (bytes, bytearray)):
                path.write_bytes(bytes(data))
            return
        except Exception:
            # Fall through to page-level helpers.
            pass

    # Playwright-style: page.screenshot accepts path/full_page/type kwargs.
    if hasattr(page, "screenshot"):
        try:
            result = await page.screenshot(
                path=str(path), full_page=full_page, type="png"
            )
            if isinstance(result, (bytes, bytearray)) and not path.exists():
                path.write_bytes(bytes(result))
            if isinstance(result, str) and not path.exists():
                # Some implementations return base64 even when path is passed.
                try:
                    path.write_bytes(base64.b64decode(result))
                except Exception:
                    pass
            return
        except TypeError:
            # browser_use Page.screenshot only accepts (format, quality) --
            # fall through to the base64-returning path.
            pass

        data = await page.screenshot(format="png")
        if isinstance(data, str):
            path.write_bytes(base64.b64decode(data))
        elif isinstance(data, (bytes, bytearray)):
            path.write_bytes(bytes(data))
        return

    raise RuntimeError("Active page does not support screenshot capture")

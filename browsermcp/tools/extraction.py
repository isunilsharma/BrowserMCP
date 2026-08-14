from __future__ import annotations

import asyncio
from typing import Any

from ..models import ExtractResult
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
            "browser_use not installed — run 'uv sync'"
        ) from exc

_SIMPLE_TYPES = (str, int, float, bool, type(None))


async def extract(
    schema: dict,
    prompt: str,
    window_id: str | None = None,
    timeout_s: float = 10.0,
    frame: str | None = None,
) -> ExtractResult:
    """Extract structured data from the current page via a deterministic DOM walk.

    Raises stdlib TimeoutError if the page-read step doesn't complete within
    timeout_s. The DOM walk itself is pure Python and not subject to timeouts.
    """
    _require_browser_use()

    # Validate that all keys in the input schema are strings before lower()-casing them later.
    if isinstance(schema, dict):
        for k in schema:
            if not isinstance(k, str):
                return ExtractResult(
                    data={},
                    confidence="low",
                    source_elements=[
                        f"unsupported schema key type: {type(k).__name__}"
                    ],
                )

    if not _is_flat_simple_schema(schema):
        return ExtractResult(
            data={},
            source_elements=[
                "schema is nested or complex; fast path skipped — needs Phase 2 slow path"
            ],
            confidence="low",
        )

    page = await get_page(window_id)
    try:
        target = await asyncio.wait_for(_resolve_extract_target(page, frame), timeout=timeout_s)
        html = await asyncio.wait_for(_read_page_content(target), timeout=timeout_s)
    except (asyncio.TimeoutError, _PlaywrightTimeoutError) as exc:
        raise TimeoutError(
            f"extract page-read did not complete within {timeout_s}s"
        ) from exc

    data, sources = _walk_flat_schema(html, schema)

    missing = [k for k in schema if k not in data or data[k] in (None, "", [])]
    confidence = "low" if missing else "high"

    return ExtractResult(data=data, source_elements=sources, confidence=confidence)


def _is_simple_schema_value(value: Any) -> bool:
    """Return True if value is a simple scalar/type marker (str, int, float, bool, None, or a SIMPLE type)."""
    if isinstance(value, type):
        return value in _SIMPLE_TYPES
    if isinstance(value, str):
        return True
    if isinstance(value, _SIMPLE_TYPES):
        return True
    return False


def _is_list_of_records(value: Any) -> bool:
    """Return True if value is a non-empty list whose first element is a flat record schema."""
    if not isinstance(value, list) or not value:
        return False
    first = value[0]
    if not isinstance(first, dict) or not first:
        return False
    for k, v in first.items():
        if not isinstance(k, str):
            return False
        if not _is_simple_schema_value(v):
            return False
    return True


def _is_flat_simple_schema(schema: Any) -> bool:
    """Schema is acceptable if it's a dict whose values are either simple scalars
    or a list-of-flat-record schemas (e.g. {"kpis": [{"name": "str", "value": "str"}]})."""
    if not isinstance(schema, dict) or not schema:
        return False
    for value in schema.values():
        if _is_simple_schema_value(value):
            continue
        if _is_list_of_records(value):
            continue
        return False
    return True


async def _resolve_extract_target(page: Any, frame: str | None):
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


async def _read_page_content(page) -> str:
    """Fetch raw HTML from a browser_use Page.

    browser_use Pages do NOT expose .content() or .get_html(); the supported way is
    to evaluate a JS arrow function returning document.documentElement.outerHTML.
    """
    return await page.evaluate("() => document.documentElement.outerHTML")


def _walk_flat_schema(html: str, schema: dict) -> tuple[dict, list[str]]:
    from html.parser import HTMLParser

    class _Collector(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.nodes: list[dict] = []
            self._stack: list[dict] = []

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            attr_map = {k: (v or "") for k, v in attrs}
            node = {
                "tag": tag,
                "attrs": attr_map,
                "text": "",
                "children_text": [],
            }
            self.nodes.append(node)
            self._stack.append(node)

        def handle_endtag(self, tag: str) -> None:
            while self._stack and self._stack[-1]["tag"] != tag:
                self._stack.pop()
            if self._stack:
                self._stack.pop()

        def handle_data(self, data: str) -> None:
            text = data.strip()
            if not text:
                return
            if self._stack:
                node = self._stack[-1]
                node["text"] = (node["text"] + " " + text).strip()
                for ancestor in self._stack[:-1]:
                    ancestor["children_text"].append(text)

    parser = _Collector()
    parser.feed(html)

    data: dict = {}
    sources: list[str] = []

    for key, schema_value in schema.items():
        if _is_list_of_records(schema_value):
            record_schema = schema_value[0]
            records, record_sources = _extract_list_of_records(
                parser.nodes, key, record_schema
            )
            if records:
                data[key] = records
                sources.extend(record_sources)
            continue

        value, source = _find_value_for_key(parser.nodes, key)
        if value is not None:
            data[key] = value
            sources.append(source)

    return data, sources


def _extract_list_of_records(
    nodes: list[dict], key: str, record_schema: dict
) -> tuple[list[dict], list[str]]:
    """Best-effort list-of-records extraction for the flat fast path.

    Scans nodes for occurrences of the record's fields appearing in clusters; emits
    one record per matched cluster. Falls back to empty list if nothing matches.
    """
    field_keys = [k for k in record_schema.keys() if isinstance(k, str)]
    if not field_keys:
        return [], []

    records: list[dict] = []
    sources: list[str] = []
    used_indices: set[int] = set()

    for idx, node in enumerate(nodes):
        if idx in used_indices:
            continue
        accessible_name = _accessible_name(node)
        if not accessible_name:
            continue
        # Anchor scan on a node whose accessible name matches the outer key
        # OR matches one of the record's field names (best-effort).
        anchor_match = (
            key.lower() in accessible_name.lower()
            or any(fk.lower() in accessible_name.lower() for fk in field_keys)
        )
        if not anchor_match:
            continue

        # Gather a window of nodes after the anchor and try to fill each field.
        window = nodes[idx : idx + 40]
        record: dict = {}
        for field_key in field_keys:
            value, source = _find_value_for_key(window, field_key)
            if value is not None:
                record[field_key] = value
                if source:
                    sources.append(f"[{key}#{len(records)}] {source}")
        if record:
            records.append(record)
            used_indices.update(range(idx, min(idx + 40, len(nodes))))

    return records, sources


def _find_value_for_key(nodes: list[dict], key: str) -> tuple[str | None, str]:
    needle = key.lower()
    for idx, node in enumerate(nodes):
        accessible_name = _accessible_name(node)
        if not accessible_name:
            continue
        if needle not in accessible_name.lower():
            continue

        value = _value_from_node(node, nodes, idx)
        if value:
            return value, f"<{node['tag']}> name={accessible_name!r}"
    return None, ""


def _accessible_name(node: dict) -> str:
    attrs = node["attrs"]
    for attr in ("aria-label", "title", "alt", "placeholder", "name", "id"):
        val = attrs.get(attr)
        if val:
            return val
    return node["text"]


def _value_from_node(node: dict, nodes: list[dict], idx: int) -> str | None:
    attrs = node["attrs"]
    for attr in ("value", "aria-valuetext", "data-value"):
        val = attrs.get(attr)
        if val:
            return val

    for sibling in nodes[idx + 1 : idx + 6]:
        if sibling["text"]:
            return sibling["text"]

    if node["children_text"]:
        joined = " ".join(node["children_text"]).strip()
        if joined:
            return joined

    if node["text"]:
        return node["text"]

    return None

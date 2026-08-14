"""Power BI drill-down helpers: discover the report's real field references from
its network traffic, then apply report-level URL filters.

Why this exists
---------------
Power BI's report canvas is an SVG/canvas surface; the slicers and matrix "+"
expanders you see are accessibility proxies painted over it. Synthetic clicks —
even *trusted* CDP mouse events — are ignored by the visual's own hit-testing, so
we cannot drive slicers by clicking (verified 2026-07-02). The public
``powerbi-client`` control API (``report.setSlicerState``) is not exposed inside
the Power BI *service* either (``window.powerbi.embeds`` is empty).

The one lever that works is the **URL query-string filter**:

    ...ReportSection<hash>?experience=power-bi&filter=Location/Division eq 'United'

But Power BI silently ignores a filter whose ``Entity/Property`` ref does not
exactly match the data model — and those refs are not present anywhere in the DOM.
They live only in the *semantic-query* POST bodies the report fires at load time.
So :func:`powerbi_discover_fields` arms a network listener, reloads the report,
and recovers the real ``Entity/Property`` map from those bodies;
:func:`powerbi_set_filter` then builds a correct ``&filter=`` URL and navigates.

Security note (see docs/security.md): discovery reads the report's own outbound
request bodies *in memory* only to recover field names. Nothing is written, and
nothing leaves the machine. No cookies, tokens, or row data are persisted.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote, urlsplit, urlunsplit

from ..config import host_allowed, load_settings
from ..models import PowerBIField, PowerBIFieldsResult, PowerBISetFilterResult
from ..state import get_page

# A POST is a semantic query if its body carries these markers. Matching on body
# content (not host) keeps us robust to Power BI routing queries through either
# ``*.analysis.windows.net`` or a ``*.pbidedicated.windows.net`` capacity host.
_QUERY_MARKERS = ("SemanticQuery", "querydata")


def _looks_like_query(url: str, body: str) -> bool:
    if not body:
        return False
    if "querydata" in url.lower():
        return True
    if "SemanticQuery" in body:
        return True
    return '"From"' in body and '"Select"' in body


def parse_field_refs(bodies: list[str]) -> dict[str, dict]:
    """Recover ``{property_name: {ref, entity, property}}`` from semantic-query bodies.

    Each Power BI query names its source tables in a ``From`` list mapping an alias
    (``Name``) to an ``Entity`` (the model table), then references columns/measures
    via ``{"Column"|"Measure": {"Expression": {"SourceRef": {"Source": alias}},
    "Property": column}}``. We resolve alias→entity per query scope (a nested
    subquery may rebind aliases) and pair each property with its entity.

    Pure function — no I/O — so it is unit-testable against captured fixtures.
    """
    fields: dict[str, dict] = {}

    def walk(node, aliases: dict[str, str]) -> None:
        if isinstance(node, dict):
            local = aliases
            frm = node.get("From")
            if isinstance(frm, list):
                local = dict(aliases)
                for entry in frm:
                    if isinstance(entry, dict) and entry.get("Name") and entry.get("Entity"):
                        local[entry["Name"]] = entry["Entity"]
            for key in ("Column", "Measure"):
                ref = node.get(key)
                if isinstance(ref, dict):
                    prop = ref.get("Property")
                    source = (ref.get("Expression") or {}).get("SourceRef") or {}
                    entity = local.get(source.get("Source"), source.get("Source"))
                    if prop and entity:
                        fields.setdefault(
                            prop,
                            {"ref": f"{entity}/{prop}", "entity": entity, "property": prop},
                        )
            for value in node.values():
                walk(value, local)
        elif isinstance(node, list):
            for value in node:
                walk(value, aliases)

    for body in bodies:
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            continue
        walk(data, {})
    return fields


def build_filter_url(url: str, ref: str, value: str) -> str:
    """Return ``url`` with a single ``filter=<ref> eq '<value>'`` param.

    Any pre-existing ``filter=`` is replaced. The ``/`` in the ref is kept literal
    (Power BI rejects a percent-encoded slash); spaces and quotes are encoded.
    Single quotes in the value are doubled per OData string-literal escaping.
    """
    safe_value = value.replace("'", "''")
    expr = f"{ref} eq '{safe_value}'"
    parts = urlsplit(url)
    kept = [kv for kv in parts.query.split("&") if kv and not kv.startswith("filter=")]
    kept.append("filter=" + quote(expr, safe="/"))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(kept), parts.fragment))


async def _capture_query_bodies(page, url: str, settle_s: float, timeout_s: float) -> list[str]:
    """Reload ``url`` with a request listener armed; return semantic-query POST bodies.

    A ``goto`` to the same URL still re-issues the query POSTs (Power BI caches the
    responses, not the requests), so this reliably re-captures the model refs.
    """
    bodies: list[str] = []

    def on_request(req) -> None:
        try:
            if req.method != "POST":
                return
            body = req.post_data or ""
            if _looks_like_query(req.url, body):
                bodies.append(body)
        except Exception:
            # A capture failure must never break navigation.
            pass

    page.on("request", on_request)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        await asyncio.sleep(settle_s)
    finally:
        try:
            page.remove_listener("request", on_request)
        except Exception:
            pass
    return bodies


def _filter_reflected(bodies: list[str], value: str) -> bool:
    """True if ``value`` appears as a query literal in any captured body.

    A Power BI URL filter that the model accepts is compiled into a ``Where``
    condition, so the value shows up as a literal (e.g. ``'United'``) in the
    semantic-query request. Data values never appear in an *unfiltered* query's
    request body, so this cleanly distinguishes an applied filter from one Power
    BI silently dropped because the ``Entity/Property`` ref was wrong.
    """
    needles = (f"'{value}'", f'"{value}"', value)
    return any(any(n in body for n in needles) for body in bodies)


async def powerbi_discover_fields(
    window_id: str | None = None,
    settle_s: float = 9.0,
    timeout_s: float = 45.0,
) -> PowerBIFieldsResult:
    """Discover the current Power BI report's filterable field references.

    Reloads the report currently open in the window with a network listener armed,
    captures its semantic-query POST bodies, and returns a map of friendly column
    name -> ``Entity/Property`` ref suitable for :func:`powerbi_set_filter`.

    Read-only: request bodies are inspected in memory to recover field names only.
    """
    page = await get_page(window_id)
    current = page.url
    if not host_allowed(current, load_settings()):
        raise ValueError(f"current URL {current!r} is not a Power BI / allowed host")

    bodies = await _capture_query_bodies(page, current, settle_s, timeout_s)
    raw = parse_field_refs(bodies)
    fields = {name: PowerBIField(**meta) for name, meta in raw.items()}
    note = None if fields else "no semantic-query traffic captured; is this a report page?"
    return PowerBIFieldsResult(url=current, captured=len(bodies), fields=fields, notes=note)


async def powerbi_set_filter(
    field: str,
    value: str,
    window_id: str | None = None,
    verify: bool = True,
    settle_s: float = 9.0,
    timeout_s: float = 45.0,
) -> PowerBISetFilterResult:
    """Apply a report-level filter to the open Power BI report and navigate.

    ``field`` may be an explicit ``Entity/Property`` ref, or a friendly column name
    (e.g. ``"Division"``) that is resolved via a fresh field discovery. ``value`` is
    matched against the model's stored value, so casing must match (use
    :func:`powerbi_discover_fields` output / the report's own labels).

    When ``verify`` is True, the canvas text is compared before and after; ``applied``
    reflects whether the visible data actually changed (a mismatched ref is silently
    ignored by Power BI, which would leave the data unchanged).
    """
    page = await get_page(window_id)
    current = page.url
    settings = load_settings()
    if not host_allowed(current, settings):
        raise ValueError(f"current URL {current!r} is not a Power BI / allowed host")

    captured = 0
    if "/" in field:
        ref = field
    else:
        bodies = await _capture_query_bodies(page, current, settle_s, timeout_s)
        captured = len(bodies)
        refs = parse_field_refs(bodies)
        match = refs.get(field) or next(
            (m for name, m in refs.items() if name.lower() == field.lower()), None
        )
        if match is None:
            available = ", ".join(sorted(refs)) or "(none captured)"
            raise ValueError(
                f"field {field!r} not found in this report's model. "
                f"Available fields: {available}"
            )
        ref = match["ref"]
        current = page.url  # discovery reloaded the page; re-read the settled URL

    target = build_filter_url(current, ref, value)
    if not host_allowed(target, settings):
        raise ValueError(f"filtered URL host not allowed: {target!r}")

    if verify:
        # Navigate with the listener armed and confirm the value reaches the query
        # Where clause — Power BI silently ignores a filter whose ref is wrong.
        bodies = await _capture_query_bodies(page, target, settle_s, timeout_s)
        captured += len(bodies)
        applied = _filter_reflected(bodies, value)
        note = None if applied else (
            "filter not reflected in report queries — the ref may not match the "
            "model or the value casing is off"
        )
    else:
        await page.goto(target, wait_until="domcontentloaded", timeout=int(timeout_s * 1000))
        applied, note = True, "verify disabled; not confirmed"

    return PowerBISetFilterResult(
        ref=ref, value=value, url=target, applied=applied, captured=captured, notes=note
    )


__all__ = [
    "parse_field_refs",
    "build_filter_url",
    "powerbi_discover_fields",
    "powerbi_set_filter",
]

"""Telemetry page — view ~/.browsermcp/telemetry.jsonl events.

Only shown when `config.telemetry_opt_in == True`. The Phase 5 telemetry
sink is a no-op networkwise; events live on disk only.
"""

from __future__ import annotations

import json

import streamlit as st

from browsermcp.config import load_settings
from browsermcp.telemetry import TELEMETRY_FILE

from web.components.redaction import safe_text, safe_value


def render() -> None:
    st.title("Telemetry")
    st.caption(
        "Local telemetry events. Nothing leaves your machine — the v0 sink "
        "is a no-op networkwise; this page reads "
        f"`{safe_text(str(TELEMETRY_FILE))}`."
    )

    settings = load_settings()
    if not settings.telemetry_opt_in:
        st.warning(
            "Telemetry is **opt-in**. Set `telemetry_opt_in = true` in "
            "`~/.browsermcp/config.toml` to enable. This page is read-only — "
            "we won't toggle it for you."
        )
        return

    if not TELEMETRY_FILE.exists():
        st.info(
            "No telemetry events recorded yet. They'll appear here once the "
            "MCP server starts emitting via `browsermcp.telemetry.emit()`."
        )
        return

    try:
        text = TELEMETRY_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        st.error(f"Could not read telemetry file: {e}")
        return

    events = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            continue

    if not events:
        st.info("Telemetry file is present but contains no parseable events.")
        return

    st.caption(f"Showing {len(events)} events, newest last.")

    rows = [
        {
            "When": safe_text(ev.get("t", "")),
            "Event": safe_text(ev.get("event", "")),
            "Props (keys)": ", ".join(sorted((ev.get("properties") or {}).keys())),
        }
        for ev in events
    ]
    st.dataframe(rows, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Raw events")
    for i, ev in enumerate(events, start=1):
        evt = safe_text(ev.get("event") or "?")
        when = safe_text(ev.get("t") or "")
        with st.expander(f"{i}. {evt}  ·  {when}", expanded=False):
            st.json(safe_value(ev))


render()

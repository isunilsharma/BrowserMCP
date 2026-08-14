"""Recordings page — list saved browser action recordings + per-event view.

Backed by `browsermcp.recorder.list_recordings()` and `load_recording()`. The
recorder module already redacts at load time; we apply `safe_value` again as
defense in depth.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st

from browsermcp.recorder import RECORDINGS_DIR, list_recordings, load_recording

from web.components.redaction import safe_text, safe_value


def _recording_summary(name: str) -> dict | None:
    """Read a recording into a small summary dict (name, created, count)."""
    try:
        rec = load_recording(name)
    except (FileNotFoundError, ValueError):
        return None
    path = RECORDINGS_DIR / f"{name}.jsonl"
    return {
        "name": rec.name,
        "created_at": rec.created_at,
        "event_count": len(rec.events),
        "path": str(path),
        "events": rec.events,
    }


def _format_created_at(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return safe_text(iso)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def render() -> None:
    st.title("Recordings")
    st.caption(
        f"Saved browser action recordings under `{safe_text(str(RECORDINGS_DIR))}`. "
        "Created by `/record-flow` in Claude Code."
    )

    names = list_recordings()
    if not names:
        st.info(
            "No recordings yet. In Claude Code run `/record-flow` to capture "
            "a sequence of browser actions and save it here."
        )
        return

    rows = []
    summaries: dict[str, dict] = {}
    for name in names:
        summary = _recording_summary(name)
        if summary is None:
            continue
        summaries[name] = summary
        rows.append({
            "Name": safe_text(summary["name"]),
            "Created": _format_created_at(summary["created_at"]),
            "Events": summary["event_count"],
        })

    st.dataframe(rows, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Inspect a recording")
    options = ["— select a recording —"] + list(summaries.keys())
    pick = st.selectbox(
        "Select a recording", options, index=0, label_visibility="collapsed"
    )
    if pick == options[0]:
        st.caption("Pick a recording above to see its event list.")
        return

    rec = summaries[pick]

    col_a, col_b = st.columns(2)
    col_a.metric("Events", rec["event_count"])
    col_b.metric("Created", _format_created_at(rec["created_at"]))
    st.caption(f"File: `{safe_text(rec['path'])}`")

    st.markdown("**Replay this in Claude Code:**")
    st.code(f"/record-flow replay {rec['name']}", language="text")

    st.markdown("**Events**")
    for i, ev in enumerate(rec["events"], start=1):
        # The recorder returns Pydantic RecordingEvent objects; convert to
        # dict for redaction + JSON rendering.
        ev_dict = ev.model_dump() if hasattr(ev, "model_dump") else dict(ev)
        kind = safe_text(ev_dict.get("kind") or "?")
        descr = safe_text(ev_dict.get("description") or ev_dict.get("url") or "")
        with st.expander(f"{i}. {kind}  ·  {descr[:80]}", expanded=False):
            st.json(safe_value(ev_dict))


render()

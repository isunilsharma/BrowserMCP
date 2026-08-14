"""Runs page — newest-first table of BrowserMCP runs with per-event drilldown.

Pulls from `load_recent_runs()` (which caps at 100 and honors the 30-day
retention contract). Supports filter-by-skill and filter-by-status. Selecting
a run reveals the full per-tool event list, redacted.
"""

from __future__ import annotations

import streamlit as st

from web.components.redaction import safe_text, safe_value
from web.components.runs import load_recent_runs


def render() -> None:
    st.title("Runs")
    st.caption(
        "Tool calls recorded by the BrowserMCP server. "
        "Capped at 100 newest from the last 30 days. PII is redacted."
    )

    runs = load_recent_runs(limit=100, since_days=30)
    if not runs:
        st.info(
            "No runs in the last 30 days. Trigger a flow in Claude Code "
            "(e.g. `/powerbi-scan` or `/flows-list`) and refresh this page."
        )
        return

    # Filter UI.
    skills_present = sorted({r["skill"] for r in runs})
    col_skill, col_status = st.columns(2)
    skill_choice = col_skill.selectbox(
        "Skill", ["All"] + skills_present, index=0
    )
    status_choice = col_status.selectbox(
        "Status", ["All", "ok", "error"], index=0
    )

    def matches(run: dict) -> bool:
        if skill_choice != "All" and run["skill"] != skill_choice:
            return False
        if status_choice != "All" and run["status"] != status_choice:
            return False
        return True

    filtered = [r for r in runs if matches(r)]
    st.caption(f"Showing {len(filtered)} of {len(runs)} runs.")

    # Index table.
    table_rows = [
        {
            "When": r["timestamp_pretty"],
            "Skill": safe_text(r["skill"]),
            "Tools": r["tool_count"],
            "Status": r["status"],
            "Duration": r["duration_pretty"],
            "Run ID": r["run_id"],
        }
        for r in filtered
    ]
    st.dataframe(table_rows, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Inspect a run")
    options = ["— select a run —"] + [
        f"{r['timestamp_pretty']} · {r['skill']} · {r['run_id']}" for r in filtered
    ]
    pick = st.selectbox(
        "Select a run", options, index=0, label_visibility="collapsed"
    )
    if pick == options[0]:
        st.caption("Pick a run above to see its tool-call event list.")
        return

    pick_idx = options.index(pick) - 1
    run = filtered[pick_idx]

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Tool calls", run["tool_count"])
    col_b.metric("Duration", run["duration_pretty"])
    col_c.metric("Status", run["status"])

    st.caption(f"File: `{safe_text(run['path'])}`")

    # Per-tool event table.
    events_table = []
    for ev in run["events"]:
        events_table.append({
            "When": safe_text(ev.get("t", "")),
            "Tool": safe_text(ev.get("tool", "")),
            "Duration (ms)": ev.get("duration_ms", 0),
            "Result": safe_text(ev.get("result_summary", ""))[:120],
        })
    st.dataframe(events_table, hide_index=True, use_container_width=True)

    st.markdown("**Per-event detail**")
    for i, ev in enumerate(run["events"], start=1):
        tool = safe_text(ev.get("tool", "?"))
        when = safe_text(ev.get("t", ""))
        with st.expander(f"{i}. {tool}  ·  {when}", expanded=False):
            # Whole event already redacted in the loader, but we re-run
            # safe_value() to be extra-safe before handing to st.json.
            st.json(safe_value(ev))


render()

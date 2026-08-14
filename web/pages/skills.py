"""Skills page — table of every installed skill + per-skill drilldown.

Combines team and personal skills into one filterable table. Selecting a row
opens an expander with the full SKILL.md body, the parsed frontmatter, and a
"Copy invocation" button that drops the slash command into the user's
clipboard via Streamlit's `st.code` (which renders with a click-to-copy icon).
"""

from __future__ import annotations

import streamlit as st

from web.components.redaction import safe_text
from web.components.skills import list_skills_classified


def render() -> None:
    st.title("Skills")
    st.caption("Team and personal Claude Code skills installed on this machine.")

    skills = list_skills_classified()
    all_skills = skills["team"] + skills["personal"]

    if not all_skills:
        st.warning(
            "No skills found. Run the team-onboarding installer "
            "(`team-onboarding/scripts/install.sh`) or `/save-as-flow` in "
            "Claude Code to add some."
        )
        return

    # Filter row.
    col_filter, col_source = st.columns([3, 1])
    query = col_filter.text_input(
        "Filter by name or description", value="", placeholder="search..."
    ).strip().lower()
    source_choice = col_source.selectbox(
        "Source", ["All", "TEAM", "PERSONAL"], index=0
    )

    def matches(skill: dict) -> bool:
        if source_choice != "All" and skill["source"] != source_choice:
            return False
        if query:
            haystack = f"{skill['name']} {skill['description']}".lower()
            if query not in haystack:
                return False
        return True

    filtered = [s for s in all_skills if matches(s)]

    # Build a flat table for the index view.
    table_rows = [
        {
            "Name": safe_text(s["name"]),
            "Description": safe_text(s["description"]),
            "Source": s["source"],
            "Last run": s.get("last_run_pretty") or s.get("last_run") or "—",
            "Status": s.get("last_run_status") or "—",
        }
        for s in filtered
    ]
    # `last_run` from the loader is an ISO string; reuse the pretty rendering
    # the Runs page uses so timestamps stay consistent.
    from web.components.runs import _pretty_timestamp  # local import to avoid cycle on cold start

    for row, skill in zip(table_rows, filtered, strict=False):
        if skill.get("last_run"):
            row["Last run"] = _pretty_timestamp(skill["last_run"])

    st.dataframe(table_rows, hide_index=True, use_container_width=True)

    st.divider()
    st.subheader("Open a skill")

    # Drilldown selector — keyed off skill name (uniqueness is fine: same name
    # in both team + personal would be a setup error and the dashboard renders
    # both rows anyway).
    options = ["— select a skill —"] + [s["name"] for s in filtered]
    pick = st.selectbox("Select a skill", options, index=0, label_visibility="collapsed")
    if pick == options[0]:
        st.caption("Pick a skill above to see its SKILL.md and copy the slash command.")
        return

    selected = next((s for s in filtered if s["name"] == pick), None)
    if selected is None:
        return

    st.markdown(f"### `/{safe_text(selected['name'])}`")
    st.caption(f"{selected['source']} · {safe_text(selected['path'])}")
    st.write(safe_text(selected["description"]))

    # Copy-invocation block: shown as a code line so Streamlit attaches its
    # built-in clipboard icon. No JS required.
    st.markdown("**Copy this invocation, then paste it into Claude Code:**")
    st.code(f"/{selected['name']}", language="text")

    args = selected.get("arguments") or []
    if args:
        with st.expander(f"Arguments ({len(args)})", expanded=True):
            for arg in args:
                name = safe_text(arg.get("name") or "?")
                arg_type = safe_text(arg.get("type") or "string")
                required = arg.get("required")
                default = arg.get("default")
                requirement = (
                    "required" if str(required).lower() == "true"
                    else f"default: {safe_text(default)}" if default is not None
                    else "optional"
                )
                desc = safe_text(arg.get("description") or "")
                st.markdown(
                    f"- **{name}** _({arg_type}, {requirement})_ — {desc}"
                )

    with st.expander("Frontmatter (parsed)", expanded=False):
        st.json(selected.get("frontmatter") or {})

    with st.expander("SKILL.md body", expanded=False):
        st.markdown(safe_text(selected["body"]))


render()

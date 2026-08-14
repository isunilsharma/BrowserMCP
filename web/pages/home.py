"""Home page — overview cards + navigation hints.

Shows count badges (team skills, personal skills, recent runs, recordings) and
a short tour of what each tab does. Designed to be the first thing a
non-engineer sees when they open the UI.
"""

from __future__ import annotations

import streamlit as st

from browsermcp.recorder import list_recordings

from web.components.runs import load_recent_runs
from web.components.skills import list_skills_classified


def render() -> None:
    st.title("BrowserMCP Console")
    st.caption(
        "A local-only dashboard for the BrowserMCP MCP server. "
        "Browse skills, see recent runs, manage recordings, and review config — "
        "all without leaving your laptop."
    )

    skills = list_skills_classified()
    runs = load_recent_runs(limit=100, since_days=30)
    recordings = list_recordings()

    # Three count badges across the top of the page.
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Team skills", len(skills["team"]))
    col2.metric("Personal skills", len(skills["personal"]))
    col3.metric("Runs (last 30d)", len(runs))
    col4.metric("Recordings", len(recordings))

    st.divider()

    st.subheader("What's in here")
    st.markdown(
        """
- **Skills** — browse every team and personal Claude Code skill installed under
  `~/.claude/skills/`. Click a row to see the full SKILL.md and copy the slash
  command into your clipboard.
- **Runs** — every BrowserMCP tool call you've made in the last 30 days,
  grouped by run. Filter by skill or status. Click a row for the per-tool
  event list.
- **Recordings** — browser action recordings saved under
  `~/.browsermcp/recordings/`. Replay them through `/record-flow` in Claude Code.
- **Settings** — read-only view of the live `browsermcp.config.Settings`
  (allowed hosts, Chrome port, retention). Includes a webhook validator.
- **Telemetry** — only visible if you've opted in via
  `~/.browsermcp/config.toml`.
        """
    )

    st.info(
        "This console is **local-only**. It does NOT invoke skills — Streamlit "
        "can't reach into Claude Code. Use the Copy invocation button to grab "
        "the slash command, then paste it into Claude Code yourself.",
        icon=":material/info:",
    )

    if runs:
        most_recent = runs[0]
        st.subheader("Most recent run")
        st.markdown(
            f"**{most_recent['skill']}** at `{most_recent['timestamp_pretty']}` — "
            f"{most_recent['tool_count']} tool calls, "
            f"{most_recent['duration_pretty']}, status: "
            f"`{most_recent['status']}`."
        )


render()

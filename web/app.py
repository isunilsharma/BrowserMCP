"""BrowserMCP Streamlit console — multi-page entry point.

Run with:

    cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP}
    streamlit run web/app.py

Opens at http://localhost:8501. Local-only — no auth, no remote backend.
The UI is read-only with respect to BrowserMCP state: it inspects skills
under `~/.claude/skills/`, run logs under `~/.browsermcp/runs/`, recordings
under `~/.browsermcp/recordings/`, and the live `Settings` object. It does
NOT invoke skills — Claude Code does that. The Skills page provides a
"Copy invocation" button that gives users the slash command to paste.

Page modules live under `web/pages/` and are dispatched here via
`st.navigation`, which was introduced in Streamlit 1.30. We use the
programmatic `st.Page` API rather than the older convention-based
`pages/` directory (which would collide with our `web/pages/` package
name) — this keeps the module layout clean and lets us conditionally
hide the Telemetry page when the user hasn't opted in.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Ensure both the BrowserMCP package and this `web/` package are importable
# regardless of which directory `streamlit run` is invoked from. Streamlit
# adds the script's directory to sys.path, so `pages.foo` works, but the
# parent (which holds `browsermcp/` and `web/components/`) needs help.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from browsermcp.config import load_settings  # noqa: E402


st.set_page_config(
    page_title="BrowserMCP Console",
    page_icon=":material/dashboard:",
    layout="wide",
)


def _build_pages() -> list:
    """Construct the page list, conditionally including Telemetry."""
    home = st.Page(
        "pages/home.py", title="Home", icon=":material/home:", default=True
    )
    skills = st.Page(
        "pages/skills.py", title="Skills", icon=":material/extension:"
    )
    runs = st.Page(
        "pages/runs.py", title="Runs", icon=":material/history:"
    )
    recordings = st.Page(
        "pages/recordings.py", title="Recordings", icon=":material/movie:"
    )
    settings = st.Page(
        "pages/settings.py", title="Settings", icon=":material/settings:"
    )
    pages = [home, skills, runs, recordings, settings]

    # Telemetry only surfaces when the user has opted in via config.toml.
    if load_settings().telemetry_opt_in:
        pages.append(
            st.Page(
                "pages/telemetry.py",
                title="Telemetry",
                icon=":material/insights:",
            )
        )
    return pages


def main() -> None:
    pages = _build_pages()
    nav = st.navigation(pages, position="sidebar")
    nav.run()


main()

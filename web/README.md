# BrowserMCP Console

A local Streamlit dashboard for the BrowserMCP MCP server. Browse installed
skills, inspect recent tool-call runs, list saved recordings, and review the
live config — all from a browser, without typing into Claude Code.

## Who it's for

- Non-engineer teammates (category managers, analysts) who want to know what
  skills are installed and what's been running, without learning the Claude
  Code CLI surface.
- Engineers debugging a flow — flip between Skills and Runs, click into a run,
  see the full per-tool event list with PII already redacted.

## Run it

```bash
cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP}
uv pip install streamlit             # one-time
streamlit run web/app.py
```

Or, using the project's `web` extra:

```bash
uv sync --extra web
uv run streamlit run web/app.py
```

Opens at <http://localhost:8501>.

The server is **bound to 127.0.0.1 only** via `web/.streamlit/config.toml` — nobody else on your Wi-Fi/VPN can reach it. Don't override `--server.address` on the command line. Verify the binding with:

```bash
lsof -iTCP:8501 -sTCP:LISTEN   # should show only 127.0.0.1, NOT *.*.*.* or 0.0.0.0
```

**No auth — local-only.** The console reads files under your home directory
(`~/.claude/skills/`, `~/.browsermcp/runs/`, `~/.browsermcp/recordings/`) and the
live `browsermcp.config.Settings`. It never POSTs to a webhook (the "Test
webhooks" section validates env vars without sending). It never invokes a
skill — Claude Code does that. The Skills page's "Copy invocation" button
gives you the slash command to paste.

## Pages

| Page | What it does |
| --- | --- |
| Home | Count badges (team skills, personal skills, runs in last 30d, recordings) and a short tour. |
| Skills | Table of every skill under `~/.claude/skills/`, classified as TEAM (symlink into `BrowserMCP/team-skills/`) or PERSONAL (regular directory). Drilldown shows the SKILL.md body, parsed arguments, and a copyable slash command. |
| Runs | Newest-first table of runs from `~/.browsermcp/runs/*.jsonl`, capped at 100, filtered to the last 30 days (matches the retention contract in `docs/security.md`). Filter by skill or status. Drilldown shows the per-tool event list with PII redacted. |
| Recordings | Lists saved recordings from `~/.browsermcp/recordings/*.jsonl`. Drilldown shows the events for a given recording. |
| Settings | Read-only view of `browsermcp.config.Settings` (Chrome CDP port, allowed hosts, log retention, max tool calls per run, telemetry opt-in). Includes a "Test webhooks" section that validates your `SLACK_WEBHOOK_URL` / `TEAMS_WEBHOOK_URL` env vars against the allowlist in `browsermcp.notify`, without POSTing. |
| Telemetry | Only visible if `telemetry_opt_in = true` in `~/.browsermcp/config.toml`. Renders `~/.browsermcp/telemetry.jsonl`. |

## How it integrates with BrowserMCP

The web UI imports straight from the parent `browsermcp` package — no
reimplemented logic. Files of note:

- `browsermcp/config.py` → Settings page reads `load_settings()`.
- `browsermcp/logging_jsonl.py` → defines the run JSONL shape this UI
  consumes (`web/components/runs.py`).
- `browsermcp/redact.py` → every on-screen string passes through
  `web.components.redaction.safe_text()` (a thin wrapper around `_redact_str`).
- `browsermcp/recorder.py` → Recordings page uses `list_recordings` and
  `load_recording`.
- `browsermcp/notify.py` → Settings page imports the host allowlist constants
  for the webhook validator (no actual POST is performed).

## File layout

```
web/
├── app.py                       — st.navigation entry point
├── README.md                    — this file
├── requirements.txt             — streamlit>=1.30 (everything else from parent)
├── components/
│   ├── __init__.py
│   ├── redaction.py             — safe_text() / safe_value() wrappers
│   ├── runs.py                  — load_recent_runs() helper
│   └── skills.py                — list_skills_classified() helper
└── pages/
    ├── home.py
    ├── skills.py
    ├── runs.py
    ├── recordings.py
    ├── settings.py
    └── telemetry.py
```

## Limitations (intentional)

- **No skill execution.** Streamlit can't reach into Claude Code. The Skills
  page only copies invocations to your clipboard.
- **No remote access.** Bound to localhost. If you need someone else to see
  this dashboard, they should run their own instance on their machine — that's
  where their `~/.browsermcp/runs/` and skills live anyway.
- **No file edits.** All pages are read-only. To change settings, edit
  `~/.browsermcp/config.toml`; to remove a recording, delete the JSONL file by
  hand.

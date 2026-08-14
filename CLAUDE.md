# CLAUDE.md

> Guidance for Claude Code when working in this repository.

## Project overview

**BrowserMCP** is an internal MCP server that wraps [browser-use](https://github.com/browser-use/browser-use) so teammates can drive their own browser through Claude Code without needing an Anthropic/OpenAI API key. Claude Code is the LLM "brain"; this repo provides the browser "arms" as MCP tools, plus a starter library of Claude Code skills.

Key intent: lower the unit cost of "small but real" web-automation tasks inside a large enterprise by orders of magnitude — replacing 3-month IT integration tickets with hour-scale flows that any teammate can author.

## Architecture in one breath

```
Claude Code Desktop  ←(MCP)→  BrowserMCP server  ←(Playwright/CDP)→  User's Chrome
                                       │
                            attaches to user's SSO'd session
                                       │
                        exposes ~10 primitive browser tools
                        + a library of higher-level "team skills"
```

Three layers of tools the MCP server exposes:

1. **Primitives** — `attach_to_chrome`, `navigate`, `click`, `type`, `read_page`, `extract`, `screenshot`, `wait_for`
2. **Conveniences** — `with_chrome_profile`, `save_session`, `run_saved_flow`
3. **Team skills** (in `team-skills/`) — pre-built flows like `/powerbi-scan`, `/confluence-search`

See `docs/design.md` for the full picture.

## Repository layout

```
BrowserMCP/
├── README.md
├── CLAUDE.md                 ← this file
├── docs/                     ← read these before code
│   ├── design.md             ← architecture decisions
│   ├── getting-started.md    ← install guide for new users
│   ├── userflow.md           ← user journeys
│   ├── techflow.md           ← MCP wire calls, tool reference, skill frontmatter
│   ├── testing.md            ← test strategy
│   ├── security.md           ← threat model, review checklist, governance
│   ├── acceptable-use.md     ← user-facing policy
│   └── roadmap.md            ← phases + what shipped (includes Phase 4/5 detail)
├── browsermcp/               ← MCP server implementation
│   ├── server.py
│   ├── tools/
│   └── pyproject.toml
├── team-skills/              ← (forthcoming) shipped Claude Code skills
│   ├── powerbi-scan/SKILL.md
│   ├── confluence-search/SKILL.md
│   └── jira-bulk-update/SKILL.md
└── tests/                    ← (forthcoming)
```

## Conventions

### Code style
- Python 3.11+, typed (PEP 604 unions, `from __future__ import annotations`)
- `uv` for dependency management; `pyproject.toml` is the source of truth
- `ruff` for lint + format (line length 100)
- Functions returning structured data should use Pydantic models, not raw dicts

### MCP tool naming
- Primitives are verbs: `navigate`, `click`, `extract`
- Higher-level helpers are `noun_verb`: `chrome_attach`, `session_save`
- All tools take typed parameters and return Pydantic responses

### Skill files (`SKILL.md`)
Each team skill lives in `team-skills/<name>/SKILL.md` with frontmatter:

```yaml
---
name: powerbi-scan
description: Scan a Power BI report and return KPIs
arguments:
  - name: report
    type: string
    required: true
---
```

Body is markdown describing what the skill does and how Claude should use the BrowserMCP tools to accomplish it.

### Personal skills
Saved by users via `/save-as-flow` into `~/.claude/skills/<name>/`. Never edited from this repo — the repo only ships `team-skills/`.

## Things to be careful about

### 🔐 Security & SSO
- The default Chrome attach mode uses the user's real session. Do NOT exfiltrate cookies, tokens, or auth data anywhere.
- All flows run **client-side** on the user's machine. No central server holds credentials.
- See `docs/security.md` before adding any new tool that could write data or move data off-machine.

### ⚠️ Destructive actions
- Any tool that writes (clicks "Submit", "Delete", "Approve") should default to **dry-run** and require explicit confirmation.
- Bulk actions must list what they're about to do and ask "Proceed?" before doing it.
- Pattern: see `team-skills/jira-bulk-update/` for the canonical example.

### 🧪 Testing real browser flows
- Unit tests mock the browser; integration tests use a local fixture site; e2e tests run against staging Power BI / Jira if available.
- Don't write tests that hit production internal systems.
- See `docs/testing.md`.

### 📝 Logging
- Every tool call is logged locally to `~/.browsermcp/runs/<timestamp>.jsonl`
- Logs include: tool name, args (with PII redaction), result summary, duration
- Never log raw page HTML, cookies, or auth tokens

## When asked to do common things

### "Add a new team skill"
1. Create `team-skills/<name>/SKILL.md` with the frontmatter pattern above
2. If the skill needs Python helpers, add them to `browsermcp/skill_helpers/<name>.py`
3. Add an integration test in `tests/skills/test_<name>.py`
4. Update `docs/userflow.md` if the user journey changes meaningfully
5. Bump `browsermcp/pyproject.toml` version (semver: minor bump for new skill)

### "Add a new primitive MCP tool"
1. Define it in `browsermcp/tools/<category>.py` with typed Pydantic params/returns
2. Register it in `browsermcp/server.py`
3. Document it in `docs/techflow.md` under "MCP Tool Reference"
4. Add unit tests in `tests/tools/test_<category>.py`
5. Consider security implications — does this tool make destructive actions possible?

### "Modify the chrome-attach mechanism"
Read `docs/security.md` and `docs/techflow.md` first — chrome-attach is the highest-stakes part of the system. Changes here need a security review note in the PR.

### "Update the docs"
Docs in `docs/` are user-facing. Keep them readable for non-developers (the audience includes non-engineer teammates, not just engineers).

## What this project is NOT

- ❌ Not a general-purpose browser automation framework — we're a thin opinionated wrapper for *internal* use cases
- ❌ Not a competitor to Browser Use Cloud — we're the *Claude-Code-native* alternative for internal teams who already have Claude Code
- ❌ Not a public/SaaS product — internal only, no external hosting plans
- ❌ Not for unattended/24-7 automation in v1 — runs on the user's own machine while they're logged in. (See `docs/roadmap.md` Phase 3 for the headless/scheduled path.)

## Communication style for this repo

- Docs are written for a mixed audience (eng + non-eng). Plain language wins over jargon.
- Diagrams over walls of text. ASCII boxes are fine.
- When in doubt about a design decision, write a one-pager and link it from the relevant `docs/*.md`.

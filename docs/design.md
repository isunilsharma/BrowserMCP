# Design

> Architecture, components, and the rationale behind every major design decision.

## 1. Problem statement

Inside a large enterprise, most "useful" automation work falls into one of three buckets:

| Bucket | Description | Today's outcome |
|---|---|---|
| **API exists, well-supported** | Slack, GitHub, modern internal services | Use the API. Done. |
| **API exists but blocked** | Power BI, Workday, ServiceNow, Salesforce | 3–6 month IT/security ticket. Most workflows die here. |
| **No API at all** | Vendor portals, legacy apps, regulatory sites | RPA project or manual work forever. |

Buckets 2 and 3 represent the long tail of small-but-real automations. Each is too small to justify a multi-month integration project, so they don't get done — collectively losing thousands of hours per year across the company.

**BrowserMCP exists to make Bucket 2 and 3 work tractable** by:
- Using the user's *existing* SSO'd browser session (no service account, no IT ticket)
- Using the user's *existing* Claude Code subscription (no LLM API key)
- Letting the user *describe* flows instead of *coding* them

## 2. Design goals (in priority order)

1. **Zero friction for end users.** A teammate with no engineering background should be able to install, run, and *author* flows.
2. **No new credentials.** Leverage what every teammate already has: Claude Code + their work Chrome.
3. **Don't take over the user's computer.** The agent must be sandboxed to a single browser context, not steal mouse/keyboard focus.
4. **Sharing must be cheap.** Going from "this works for me" to "the team has it" should be one command.
5. **Be honest about limits.** Where an API is better, use the API. Where determinism matters, don't use an LLM.

## 3. Non-goals (explicitly)

- ❌ Not a public/SaaS product
- ❌ Not built for 24/7 unattended runs (in v1)
- ❌ Not a Selenium/Playwright replacement for high-volume deterministic flows
- ❌ Not a general computer-use agent — scoped to the browser only

## 4. High-level architecture

```
┌────────────────────────────────────────────────────────────────┐
│                  Teammate's machine                            │
│                                                                │
│   ┌──────────────────────┐         ┌──────────────────────┐   │
│   │  Claude Code Desktop │  MCP    │   BrowserMCP server  │   │
│   │  (the "brain")       │ ◄─────► │   (Python process)   │   │
│   │                      │         │                       │   │
│   │  - User chat         │         │  - Browser primitives │   │
│   │  - Skill registry    │         │  - Skill helpers      │   │
│   │  - LLM (via user's   │         │  - Run logging        │   │
│   │    Claude subscription)        │                       │   │
│   └──────────────────────┘         └──────────┬───────────┘   │
│                                                │ Playwright/   │
│                                                │ CDP           │
│                                                ▼               │
│                                    ┌──────────────────────┐   │
│                                    │   User's Chrome      │   │
│                                    │   (existing SSO'd    │   │
│                                    │   session reused)    │   │
│                                    └──────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

**Key property:** everything runs on the teammate's own machine. No central server holds credentials, sessions, or page content. This is intentional — it simplifies security review and minimizes blast radius.

## 5. The three layers of MCP tools

The BrowserMCP server exposes tools in three layers, from low-level to high-level:

### Layer 1 — Primitives (the building blocks)

The atomic operations Claude Code uses to drive a browser. These are the "LEGO bricks."

| Tool | Purpose |
|---|---|
| `chrome_attach()` | Connect to the user's running Chrome via CDP |
| `chrome_new_window()` | Open a separate window (default UX) |
| `navigate(url)` | Go to a URL |
| `click(description)` | Click an element by natural-language description |
| `type(field, text)` | Type into a field |
| `read_page()` | Return structured DOM/text |
| `extract(schema, prompt)` | Pull structured data matching a Pydantic schema |
| `screenshot()` | Capture the current view |
| `wait_for(condition)` | Wait for a condition (text appears, URL matches, etc.) |
| `scroll(direction, amount)` | Scroll the page |

### Layer 2 — Conveniences (composed helpers)

Higher-level operations built on Layer 1 to reduce LLM token use and improve reliability.

| Tool | Purpose |
|---|---|
| `with_chrome_profile(path)` | Attach to a specific Chrome profile (e.g., `~/Library/.../Sunil-Bot`) |
| `session_save(name)` | Snapshot cookies/storage for later replay |
| `session_restore(name)` | Restore a saved session |
| `run_saved_flow(name, args)` | Run a saved Claude Code skill from inside another flow |

### Layer 3 — Team skills (shipped flows)

Pre-built Claude Code skills that ship with the plugin. These are NOT MCP tools — they're skill files (`SKILL.md`) that *use* Layer 1/2 tools to accomplish a specific task.

| Skill | What it does |
|---|---|
| `/powerbi-scan` | Scan a Power BI report and return KPIs |
| `/confluence-search` | Cross-page search across internal Confluence |
| `/jira-bulk-update` | Bulk-update Jira tickets matching a query |
| `/save-as-flow` | Meta — save the current chat as a reusable personal skill |
| `/promote-flow` | Meta — promote a personal skill to the team via GitHub PR |
| `/flows-list` | Meta — list installed flows + recent runs |
| `/flows-edit` | Meta — edit a saved personal skill |

### Skill frontmatter (recognized fields)

Every `SKILL.md` opens with a YAML block. The recognized fields are:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `name` | string | (required) | Kebab-case skill id; must match the directory name. |
| `description` | string | (required) | One-line summary surfaced in `/flows-list` and the slash-command picker. |
| `arguments` | list | `[]` | Typed inputs the skill accepts (`name`, `type`, `required` or `default`, `description`). |
| `interactive` | bool | `true` | If `false`, the skill is permitted to run unattended — no user prompts mid-flow. Today this is advisory + checklist-enforced; Phase 4 v2 wires it to a headless Chrome path. |
| `max_steps` | int | (server cap) | Per-skill cap on tool calls; falls back to `Settings.max_tool_calls_per_run` if unset. |
| `risk` | enum | `read` | One of `read | write | destructive`. `write` and `destructive` require an explicit user-confirmation step (see security.md §6). |

See `docs/skill-frontmatter.md` for the full reference, including examples for each field.

### Why three layers (not one)?

- **Primitives alone** would force every flow to be very prompt-heavy and slow. The LLM would re-invent the same patterns 1000 times.
- **Skills alone** would mean every flow needs to be hand-coded by a developer — defeating the "non-eng teammate can author" goal.
- **Both together** lets users start from team skills (works on day 1), discover patterns, and graduate to authoring their own (via `/save-as-flow`).

## 6. The "brain" decision: Claude Code, not a dedicated LLM key

Most browser-use deployments require each user to provide an Anthropic / OpenAI API key. Inside a large enterprise, teammates don't have these — but they do have Claude Code subscriptions.

By exposing browser actions as MCP tools rather than running our own agent loop, **Claude Code becomes the brain**. The user's existing Claude Code authentication / billing applies. No new credentials, no shared key, no Anthropic enterprise contract needed for v1.

### Trade-off accepted
- ✅ Zero LLM key management
- ✅ Per-user billing baked in via existing Claude subscriptions
- ✅ Natural conversational UX (users already use Claude Code)
- ❌ Can't run when the user isn't in a Claude Code session
- ❌ Latency depends on Claude Code's response time
- ❌ Hard to do truly unattended/scheduled runs (deferred to Phase 3)

## 7. Chrome attach: the "use the user's session" trick

The hardest enterprise problem in browser automation is SSO + MFA + Conditional Access. We sidestep it by **never logging in from the bot.**

Instead, BrowserMCP attaches to the user's *already-running* Chrome via the Chrome DevTools Protocol (CDP). Chrome is launched (or relaunched) with `--remote-debugging-port=9222` against the user's normal profile. The user has already passed SSO + MFA this morning when they logged into Outlook/Teams; their session cookies are sitting right there.

```
First-time setup (one click in the plugin install):
  Quit Chrome → Relaunch with `--remote-debugging-port=9222 --user-data-dir=<profile>` 
  → BrowserMCP can now attach

Every subsequent run:
  Just attach — session is already authenticated
```

### Default: new window, not new tab
The agent opens a **separate Chrome window** (Option 2 in `userflow.md`). The user's main browsing is untouched; they can keep working. The agent window can be minimized or watched live.

### Fallback: dedicated agent profile
For scheduled/headless use, a separate Chrome profile dedicated to the bot. Login happens once, with MFA; sessions persist for the policy lifetime. See `docs/security.md` for the trade-offs.

## 8. Skill storage layout (the "where does my flow live" question)

```
~/.claude/                                         (teammate's local Claude Code)
├── plugins/
│   └── browsermcp/                                   ← installed from internal GH
│       ├── plugin.json
│       ├── browsermcp/server.py                   ← MCP server
│       └── skills/                                ← TEAM-shared skills
│           ├── powerbi-scan/SKILL.md
│           ├── confluence-search/SKILL.md
│           ├── jira-bulk-update/SKILL.md
│           ├── save-as-flow/SKILL.md
│           ├── promote-flow/SKILL.md
│           ├── flows-list/SKILL.md
│           └── flows-edit/SKILL.md
└── skills/                                        ← PERSONAL skills (per-user)
    ├── stale-tickets/SKILL.md                     ← created by user
    └── monday-triage/SKILL.md
```

The team plugin folder is *managed* by `claude plugin update browsermcp`. The personal skills folder is *owned by the user* and never touched by the plugin.

## 9. Promotion path: personal → team

When a teammate decides their personal flow is generally useful:

```
/promote-flow stale-tickets
   ↓
1. Read ~/.claude/skills/stale-tickets/
2. Lint (PII check, destructive-action check, working test run)
3. Clone github.com/isunilsharma/BrowserMCP via gh CLI
4. Add file to team-skills/stale-tickets/
5. Open PR with author = the user's email
6. Reviewer (team-skill-reviewers) merges
7. Next `claude plugin update` distributes to all teammates
```

This is the only "central" workflow in the system — and it's just GitHub PRs against an internal repo using credentials the user already has.

## 10. Key design decisions and their rationale

| Decision | Rationale | Alternative considered |
|---|---|---|
| MCP server, not standalone agent | Reuses Claude Code's LLM, billing, UX | Standalone agent w/ shared org key. Rejected: key management, central single point of failure. |
| Local-only (no central server) | Smaller attack surface, easier IT review, simpler ops | Centrally hosted FastAPI service. Rejected: SSO complexity, ops burden, slower IT approval. |
| Chrome attach (not headless) by default | Reuses SSO session for free | Service-account + Power BI REST API. Deferred to Phase 3: requires IT/Entra app registration. |
| Skills as plain markdown (`SKILL.md`) | Non-developers can edit. Diff-friendly. | YAML-only DSL. Rejected: less expressive, harder for Claude Code to write/read in chat. |
| Promote via GitHub PR | Code review + audit trail built in. Reuses existing tooling. | Direct write to a shared share-drive. Rejected: no review, broken flows would propagate. |
| Python 3.11+ + `uv` | Modern, fast, single-binary installs via `uvx` | Node/TypeScript. Rejected: `browser-use` is Python; mixing runtimes adds friction. |

## 11. Open design questions

These are flagged for resolution before v1 ships:

- **Q1.** How do we handle long-running flows (>5 min) where Claude Code's session might time out?
- **Q2.** Should we ship a desktop "control panel" UI (Electron/Tauri) for non-Claude-Code users, or stay pure-MCP?
- **Q3.** How do we sandbox a malicious skill that someone promotes (intentionally or accidentally)? Static analysis of SKILL.md? Required reviewer? Allowlist of MCP tools per skill?
- **Q4.** When (Phase 3) we add headless/scheduled runs, do we authenticate via service account or by using the user's saved Chrome profile in a separate process?

See `docs/roadmap.md` for when each of these gets resolved.

## 12. Glossary

- **MCP** — Model Context Protocol. Anthropic's spec for letting tools (servers) expose capabilities (tools) to LLMs (clients like Claude Code).
- **Skill** — A `SKILL.md` file that Claude Code reads when a slash command is invoked. Tells Claude how to accomplish a task, often by using MCP tools.
- **Plugin** — A bundle that ships a set of skills + optional MCP server. Installed via `claude plugin install`.
- **Primitive** — A low-level MCP tool (e.g., `click`, `navigate`).
- **Team skill** — A skill that ships with the BrowserMCP plugin, available to everyone.
- **Personal skill** — A skill saved by a user in their own `~/.claude/skills/`, visible only to them.
- **Promotion** — Moving a personal skill into the team plugin via PR.
- **Attach** — Connecting BrowserMCP to a running Chrome instance via CDP, inheriting its session.

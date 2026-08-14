# BrowserMCP

> An internal MCP server that lets teammates drive their own browser through Claude Code — no LLM API key required, SSO sessions preserved, flows shareable as skills.

BrowserMCP wraps [browser-use](https://github.com/browser-use/browser-use) as a **Model Context Protocol (MCP) server** that plugs into Claude Code. Because Claude Code is the brain, teammates use their existing Claude Code subscription as the LLM — no separate Anthropic / OpenAI keys needed.

---

## Why this exists

Inside a large enterprise, the long tail of "small but real" automation needs (Power BI scanning, ServiceNow triage, vendor portal scraping, Confluence search, Jira bulk updates) usually dies in one of two places:

1. **API access takes months** to get approved through IT/security
2. **The site has no API** at all (vendor portals, legacy apps, regulatory sites)

BrowserMCP changes the unit economics — a teammate can build, save, and share a working browser agent in hours instead of waiting weeks for an integration project.

See [`docs/design.md`](./docs/design.md) for the full rationale.

---

## Quick install

<details>
<summary><strong>macOS</strong></summary>

```bash
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP
bash team-onboarding/scripts/install.sh
```
</details>

<details>
<summary><strong>Windows</strong></summary>

```powershell
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP
powershell -ExecutionPolicy Bypass -File team-onboarding\scripts\install.ps1
```
</details>

Fully quit and relaunch Claude Desktop when the installer finishes. See [`team-onboarding/`](./team-onboarding/) for details and the manual path.

---

## What you get

- **One MCP server** that exposes a small set of browser primitives (navigate, click, type, read, extract, attach-to-chrome) to Claude Code
- **A starter library of team skills** (`/powerbi-scan`, `/confluence-search`, `/jira-bulk-update`)
- **Meta-skills** that let any teammate save their own working chat as a reusable flow (`/save-as-flow`) and promote it to the team (`/promote-flow`)
- **Zero LLM API keys for users** — Claude Code provides the intelligence
- **SSO is preserved** — the agent attaches to the user's existing logged-in Chrome session

---

## Quick start (teammate, 2 minutes)

```bash
# One-time install
claude plugin install https://github.com/isunilsharma/BrowserMCP

# Then in any Claude Code session
/powerbi-scan --report "Q3 Produce Sales"
```

That's it. No API key. No Python setup. No terminal acrobatics.

See [`docs/userflow.md`](./docs/userflow.md) for end-to-end user journeys.

---

## Repository layout

```
BrowserMCP/
├── README.md                  ← you are here
├── CLAUDE.md                  ← instructions for Claude Code working in this repo
├── docs/
│   ├── design.md              ← architecture & component design
│   ├── userflow.md            ← end-to-end user journeys with transcripts
│   ├── techflow.md            ← technical sequence diagrams & MCP protocol
│   ├── testing.md             ← test strategy & coverage
│   ├── security.md            ← threat model & IT review checklist
│   └── roadmap.md             ← phased delivery plan
└── (code to come)
    ├── browsermcp/            ← MCP server implementation
    ├── team-skills/           ← shipped Claude Code skills
    └── tests/
```

---

## Project status

🟡 **Pre-MVP** — design and docs phase. Code scaffolding next. See [`docs/roadmap.md`](./docs/roadmap.md) for the phased plan.

---

## Owner / contact

- **Author:** Sunil Sharma (@isunilsharma on GitHub)
- **Repo:** https://github.com/isunilsharma/BrowserMCP

---

## Read the docs in this order

1. [`docs/design.md`](./docs/design.md) — *what* we're building and *why*
2. [`docs/userflow.md`](./docs/userflow.md) — what teammates actually experience
3. [`docs/techflow.md`](./docs/techflow.md) — how it works under the hood
4. [`docs/security.md`](./docs/security.md) — risks and mitigations
5. [`docs/testing.md`](./docs/testing.md) — how we'll know it works
6. [`docs/roadmap.md`](./docs/roadmap.md) — when it ships

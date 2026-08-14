# Claude Skill Browser Agent

> An internal toolkit that lets you automate any repetitive browser task — Power BI, Jira, Confluence, Outlook — by chatting with Claude Code. No new credentials. No new infrastructure. No code required from the user.

| | |
|---|---|
| **Status** | Pilot — ready for hands-on use |
| **Audience** | Anyone with Claude Code installed + corporate Chrome access |
| **Owner** | Sunil Sharma (@isunilsharma on GitHub) |
| **Repo** | [github.com/isunilsharma/BrowserMCP](https://github.com/isunilsharma/BrowserMCP) |
| **Last updated** | 2026-06-26 |

---

## Table of contents

1. [What this is and why it matters](#1-what-this-is-and-why-it-matters)
2. [What you can do today](#2-what-you-can-do-today)
3. [Getting started](#3-getting-started)
4. [User journeys](#4-user-journeys)
5. [Governance and safety](#5-governance-and-safety)
6. [Appendix](#6-appendix)

---

## 1. What this is and why it matters

### One-line definition

**A reusable robot that drives your own Chrome browser, on your own machine, using your own logins, to do repetitive web work for you — orchestrated by Claude Code.**

### The problem it solves

Inside a large enterprise, the long tail of useful automation rarely gets built:

| What you want | Why it doesn't get built |
|---|---|
| Pull yesterday's Power BI numbers into Slack every morning | Too small to fund a 3-month IT integration ticket |
| Bulk-update 12 Jira tickets when a release goes out | API access requires service-account approval |
| Search Confluence across 8 spaces for "X compliance policy" | Each space has different naming; manual hunt every time |
| Triage your unread Outlook to highlight what really matters | Has no API path; pure UI work |

The Claude Skill Browser Agent turns each of these into a **one-line command**.

### Business value

| Lever | Before | With this tool |
|---|---|---|
| Time to automate a "small" workflow | Weeks (IT ticket + approval) | Hours (describe it, save it) |
| Cost per automation | $$$ (engineer time + tooling) | $0 (uses existing Claude Code + Chrome) |
| Who can build automations | Engineers only | Anyone who can describe a task |
| New credentials required | Service account + InfoSec review | None — uses your existing SSO |
| Where data lives | Often shipped to vendor cloud | 100% on your laptop |

### Why now

Three things came together to make this viable:

1. **Claude Code is a real LLM-driven IDE** that already has chat, slash commands, and an MCP plugin system.
2. **Chrome's DevTools Protocol** lets a program attach to a running browser without disturbing the user's session.
3. **MCP (Model Context Protocol)** standardizes how Claude Code talks to local tools — making the browser one more tool in Claude's belt.

Without all three, this would be Selenium scripts + brittle screen-scraping. With them, you describe what you want in English and the agent figures out the clicks.

---

## 2. What you can do today

### Available skills (rock-solid, used in production by the pilot)

Type any of these as a slash command in Claude Code:

| Skill | What it does | Read or write? |
|---|---|---|
| `/powerbi-scan` | Scan a Power BI report (self-hosted or Microsoft-hosted) and return the top KPIs | Read |
| `/confluence-search` | Search Confluence (confluence.example.com) and return the top matching pages | Read |
| `/jira-bulk-update` | Bulk-update Jira tickets matching a JQL filter | Write — dry-run by default, requires explicit `confirm=true` |
| `/outlook-triage-unread` | Scan your Outlook inbox and rank unread emails by importance | Read |
| `/flows-list` | Show every skill installed (team + personal) and recent run history | Read |
| `/save-as-flow` | Save the chat you just had as a reusable personal skill (`/<your-name>`) | Meta — writes to your home dir |
| `/create-flow` | Guided Q&A wizard for authoring a new personal skill from scratch | Meta |
| `/promote-flow` | Open a pull request to share a personal skill with the whole team | Meta |

### How to think about which skill to use

```
Reading data from an internal site?         →  /powerbi-scan, /confluence-search, /outlook-triage-unread
Editing data on an internal site?           →  /jira-bulk-update (dry-run first!)
Want to build your own automation?          →  /create-flow  (if you can describe it)
                                                /save-as-flow (if you just did it ad hoc in chat)
Want the team to get your automation?       →  /promote-flow
Want to see what's installed?               →  /flows-list
```

### Ad-hoc chat works too

You don't have to use a slash command. You can just describe what you want:

> *"Use BrowserMCP to navigate to my Q3 Produce Sales Power BI report and tell me the current Shrink %."*

Claude figures out which tools to use. Once it works, save it as a skill via `/save-as-flow` for next time.

---

## 3. Getting started

### Prerequisites

| What | How to check | Where to get it |
|---|---|---|
| Mac (Apple Silicon or Intel) | `uname -m` | — |
| Claude Desktop installed and logged in | Open the app | https://claude.ai/download |
| Claude Code CLI installed | `claude --version` | https://claude.ai/code |
| Google Chrome installed | `ls /Applications/Google\ Chrome.app` | https://google.com/chrome |
| Connected to the corporate network (for first install only) | Try opening jira.example.com | Standard corporate setup |

### Install in three commands

Run these in a terminal:

```bash
# 1. Clone the internal repo
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP

# 2. Run the team onboarding installer
bash team-onboarding/scripts/install.sh

# 3. Restart Claude Desktop fully (Cmd+Q, then reopen)
```

The installer will:

- Install the Python virtual environment + dependencies
- Configure Claude Desktop to know about BrowserMCP and the related Atlassian tools
- Prompt you (with hidden input) for Personal Access Tokens for GitHub, Jira, and Confluence — skip any you don't need
- Symlink the eight team skills into your `~/.claude/skills/` directory

**Total time: about 5 minutes**, most of it waiting for `uv sync` to install Python packages.

### First-time Chrome setup

The agent uses a **dedicated, separate Chrome profile** (not your main one) so it can drive a browser independently. The first time you use a skill that touches a site, you'll be prompted to sign in to that site in the agent's Chrome window — once per site, sessions persist across runs.

| Site | First-run sign-in needed? |
|---|---|
| app.powerbi.com | Yes (Microsoft SSO) |
| confluence.example.com | Yes (corporate SSO) |
| jira.example.com | Yes (corporate SSO) |
| outlook.cloud.microsoft | Yes (Microsoft SSO) |

After the initial sign-in, sessions stay warm for ~24 hours (Microsoft) to ~30 days (Atlassian).

### Verify it works

In Claude Code, type:

```
/flows-list
```

You should see a table of eight team skills. If yes, you're ready.

---

## 4. User journeys

Three concrete examples — pick whichever matches a problem you actually have.

### Journey A — "Tell me the current Shrink % for my store"

**Persona:** Category manager. Checks Power BI shrink reports several times a week.

**Time saved per run:** ~3 minutes (skip the click-through; get the number).

| Step | What you do | What happens |
|---|---|---|
| 1 | Open Claude Code |  |
| 2 | Type `/powerbi-scan` and paste the report URL | Skill opens the report in the agent Chrome |
| 3 | (First time only) Sign in to Power BI in the agent window | Session persists |
| 4 | Wait ~30 seconds | Skill reads the report, extracts KPIs |
| 5 | Get the result: a markdown table of the top 5 KPIs + screenshot | |

**What the chat looks like:**

```
You:    /powerbi-scan report=https://app.powerbi.com/.../Fresh-Item-Shrink

Claude: Attaching to your Chrome session...
        Heading to the report...
        Reading the KPI tiles...

        Top 5 KPIs:
        | Shrink %     | 10.52%   |
        | Shrink $     | $8,098   |
        | Net Sales    | $76,972  |
        | Gross Margin | 24.43%   |
        | Top Category | Berries  |

        Screenshot: ~/.browsermcp/runs/screenshots/...png
```

---

### Journey B — "Find me the spec for the new returns workflow"

**Persona:** Product Manager. Knows the doc exists in Confluence but can't remember where.

**Time saved per run:** ~5 minutes (skip the navigate-and-search dance).

| Step | What you do | What happens |
|---|---|---|
| 1 | Type `/confluence-search query="returns workflow"` | Skill opens Confluence search |
| 2 | (First time only) Sign in to Confluence in the agent window | Session persists |
| 3 | Wait ~15 seconds | Skill reads search results |
| 4 | Get a ranked list of top 5 matching pages with snippets and URLs | |
| 5 | Click the most relevant link | Done |

---

### Journey C — "Build my own automation in 5 minutes"

**Persona:** Anyone with a repetitive workflow they want to save.

**Two paths depending on what you have:**

#### Path C1 — You already did the task once in chat

```
1. You used Claude + BrowserMCP to do something ad-hoc, and it worked.
2. Type: /save-as-flow my-monday-routine
3. Claude reads your recent chat, extracts the steps, asks 2-3 questions
   about which values to parameterize, and writes a personal skill.
4. From then on, `/my-monday-routine` reruns the whole workflow.
```

#### Path C2 — You can describe the task but haven't done it yet

```
1. Type: /create-flow stale-tickets-weekly
2. Claude walks you through five questions:
     - What's the goal? (one line)
     - What's the starting URL?
     - Walk through the steps (one per line, "done" when finished)
     - Any parameters that change between runs?
     - Does it write/change anything? (so we add a confirm gate)
3. Claude assembles a skill file and saves it.
4. /stale-tickets-weekly is now in your slash menu.
```

#### Path C3 — Share your skill with the team

```
1. Once your personal skill has proven itself for a week or two:
2. Type: /promote-flow stale-tickets-weekly
3. Claude lints the skill (no hardcoded secrets, no destructive defaults),
   opens a pull request against the BrowserMCP repo, and pings the
   reviewers group.
4. Once merged, every teammate gets your skill on their next plugin update.
```

---

## 5. Governance and safety

These are the questions InfoSec and Engineering Leadership ask first — covered upfront so you can answer them.

### Where does the code execute?

**100% on the user's own laptop.** No central server. No vendor cloud. Page content is sent to Claude (the LLM that orchestrates the agent), under the user's existing Claude Code subscription terms.

### What credentials does the user need?

**None new.** The agent reuses your existing browser sessions (SSO via Entra ID). It cannot ever see your password — you sign in yourself, in the agent's Chrome window.

### What can the agent do that the user couldn't?

**Nothing.** The agent runs as the user. If the user can see a page, the agent can read it. If the user has permission to edit a ticket, the agent can edit it (with confirmation).

> **Critical principle:** the agent grants no power the user doesn't already have. It just makes existing user authority easier to wield.

### What stops destructive actions?

Three layers:

1. **Allowlist:** the agent can only navigate to a fixed list of corporate domains (`*.example.com`, `*.example.net`, `*.powerbi.com`, etc.). Adding hosts requires editing a config file.
2. **Dry-run by default:** any write skill (e.g. `/jira-bulk-update`) shows a preview of what *would* change and refuses to act until you re-invoke with `confirm=true`.
3. **Per-tool confirmation gates:** if a skill tries to click "Approve" or "Delete" without explicit confirmation, the request is rejected.

### What gets logged?

Every tool call is logged locally to `~/.browsermcp/runs/<run-id>.jsonl`:

- Tool name, timestamp, duration, success/failure
- Arguments **after** PII redaction (emails, phones, SSNs, credit cards masked)

**No central log aggregation.** Logs are local-only with 30-day retention.

### What's the rollout plan?

| Phase | Status | Who |
|---|---|---|
| 0. Design & docs | Complete | Solo |
| 1. Solo proof-of-concept | Complete | Sunil |
| 2. Pilot with 2-3 willing teammates | Complete | Pilot users |
| 3. Team rollout + InfoSec review | **In progress** — code complete, awaiting formal InfoSec sign-off | ~20 people |
| 4. Scheduled / unattended runs | Future — gated on service-account decision | TBD |
| 5. Cross-team expansion | Future — gated on Phase 3 adoption | TBD |

---

## 6. Appendix

### A. Glossary

| Term | Meaning |
|---|---|
| **MCP (Model Context Protocol)** | Open standard for letting language models talk to local tools. Made by Anthropic. |
| **BrowserMCP** | The internal package we built — an MCP server that exposes browser actions (click, type, read, etc.) as tools Claude Code can call. |
| **Skill** | A markdown file (SKILL.md) that tells Claude how to perform a specific task. Lives in `~/.claude/skills/<name>/`. |
| **Team skill** | A skill shipped to every teammate via the BrowserMCP plugin. Reviewed via pull request. |
| **Personal skill** | A skill saved by a user via `/save-as-flow` or `/create-flow`. Lives only on that user's machine. |
| **Agent Chrome** | The dedicated, separate Chrome profile that BrowserMCP drives. Lives at `~/.browsermcp/chrome-profile/`. |
| **CDP (Chrome DevTools Protocol)** | The localhost API Chrome exposes for programs to drive it. |
| **Slash command** | A way to invoke a skill in Claude Code: `/powerbi-scan`, `/flows-list`, etc. |
| **Allowlist** | The fixed set of internet domains the agent is permitted to navigate to. |
| **Dry-run** | Preview-only mode for write skills. Default for `/jira-bulk-update`. |

### B. FAQ

**Q: Do I need an Anthropic or OpenAI API key?**
No. BrowserMCP rides on your existing Claude Code subscription — the LLM that orchestrates the agent is Claude in Claude Code.

**Q: Can my teammate use my saved skill?**
Not directly. Run `/promote-flow <name>` and Claude opens a pull request. After review and merge, teammates pick it up on the next plugin update.

**Q: Will this slow down my regular Chrome?**
No. The agent uses a separate Chrome profile and window. Your main browsing is unaffected.

**Q: What if a site changes its layout?**
For simple navigation flows, the skill keeps working (the agent finds elements by their visible labels, not by brittle CSS selectors). For complex flows, the skill may need a small update. Re-run `/create-flow <same-name>` to overwrite, or edit the SKILL.md file directly.

**Q: Where does the data go when I use a skill?**
Page content that Claude needs to see is sent to Claude (via your Claude Code subscription) for reasoning. Nothing is sent anywhere else by default. There's no central server.

**Q: I want to use this on a site that's not on the allowlist. Now what?**
Add the host to `browsermcp/config.py`'s `allowed_hosts` list, open a pull request, get review. We deliberately make this an explicit gesture so unauthorized hosts can't sneak in.

**Q: I'm a PM, not an engineer. Can I really use this?**
Yes. The slash commands are designed for non-engineers. `/create-flow` is a guided wizard with no code. The hardest part is the first install, and it's three commands.

**Q: What happens if a skill misbehaves?**
Tell Sunil (@isunilsharma on GitHub) and include the `run_id` from the chat (visible in `/flows-list` recent runs). Logs are local on your machine; you control sharing them.

### C. Where to go next

| You want to... | Do this |
|---|---|
| Install and try it | Follow [Section 3 — Getting started](#3-getting-started) |
| Read the threat model | Open [`docs/security.md`](https://github.com/isunilsharma/BrowserMCP/blob/master/docs/security.md) in the repo |
| See what's planned | Open [`docs/roadmap.md`](https://github.com/isunilsharma/BrowserMCP/blob/master/docs/roadmap.md) |
| Read the acceptable-use policy | Open [`docs/acceptable-use.md`](https://github.com/isunilsharma/BrowserMCP/blob/master/docs/acceptable-use.md) |
| Hand it to your team | Send them this page + the install instructions |
| Request a new skill | Ping Sunil; or write it yourself via `/create-flow` and ship via `/promote-flow` |
| Report a bug | Open an issue on the repo; include the `run_id` |

### D. Contact

| | |
|---|---|
| Owner | Sunil Sharma — @isunilsharma on GitHub |
| Repo | https://github.com/isunilsharma/BrowserMCP |
| Issues | https://github.com/isunilsharma/BrowserMCP/issues |
| Pilot users group | (to be set up — `team-skill-reviewers` on GitHub) |

### E. What's intentionally NOT in this page

For honesty, scope-cuts you should know about:

- **Scheduled / unattended runs** (cron-style execution). Exists in code as a registry stub; execution layer is gated on an IT decision (service account vs persistent profile).
- **Record-and-replay of arbitrary browser sessions.** Exists in preview (v0.1); not promised here because the rough edges aren't pilot-ready yet.
- **Output piping** (`/notify-slack`, `/notify-teams`, `/notify-email`). Exists; deferred from this page until tested in real use.
- **A standalone web UI** for non-Claude-Code users. Exists as a local-only Streamlit dashboard; full enterprise web UI is a future build.
- **Cross-team rollout** (other teams beyond the immediate team). Future phase.

If you want any of these, talk to Sunil — happy to add you to the pilot for whichever one matches your need.

---

*Document generated by the BrowserMCP project. To update, edit `docs/confluence-page.md` in the [repo](https://github.com/isunilsharma/BrowserMCP) and re-paste here.*

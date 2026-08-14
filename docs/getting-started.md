# Getting Started with BrowserMCP

Welcome. Your team-onboarding script just finished, which means BrowserMCP and a starter set of team skills are wired into your Claude Code. This page walks you from "installed" to "actually using it" in about ten minutes.

## 0. Where the repo should live

**Clone or install this repo under `~/code/`, `~/dev/`, `~/projects/`, or similar — NOT under `~/Desktop/`, `~/Documents/`, or `~/Downloads/`.**

Why: macOS 10.15+ protects those three folders with TCC (Transparency, Consent, and Control). Claude Code's Bash tool and its own Read/Write tools run in a context that doesn't have Desktop access by default, so file edits inside the repo fail with `Operation not permitted` until you grant Full Disk Access via System Settings. Cloning to a non-protected folder like `~/code/BrowserMCP` sidesteps the entire problem — no permission prompts, no surprise failures after a Claude Code restart.

If you already installed under a protected folder and hit "Operation not permitted" errors, either:
- Move the repo: `mv ~/Desktop/BrowserMCP ~/code/BrowserMCP` (may need Terminal.app which has native FS access), then update the Claude Desktop config path at `~/Library/Application Support/Claude/claude_desktop_config.json`; or
- Grant Claude Code Full Disk Access in **System Settings → Privacy & Security → Full Disk Access** (fastest).

## 1. What this is, in two sentences

BrowserMCP is a Claude Code add-on that lets you drive **your own Chrome** through chat — point it at Power BI, Confluence, or Jira and ask it to do things in plain English, no code required. Your SSO session stays on your machine; nothing is copied to a server, and you never have to share a password with anyone.

Think of Claude Code as the brain and your Chrome as the hands. You talk to the brain; the hands do the clicking.

## 2. Once-per-day setup

You only need to do this once each morning. The Chrome session lasts the rest of the day.

### Open the agent Chrome

Open Terminal and run:

```bash
~/code/BrowserMCP/scripts/chrome-shim.sh
```

(Adjust the path if your install location differs.)

This quits any running Chrome and relaunches it with a debugging port open on `127.0.0.1:9222`. BrowserMCP attaches to that port. The window looks and feels like normal Chrome — same bookmarks, same extensions — it's just listening for Claude.

A small note: the shim uses a **dedicated, separate Chrome profile** under `~/.browsermcp/chrome-profile`. Newer Chrome versions don't let us share your normal Chrome profile, so the agent gets its own. That means the first time you launch, you'll be signed out of everything in the agent window — just sign in once per site (Power BI, Jira, Confluence) and the sessions stick around for the day.

### Sign in to the sites you'll use

In that agent Chrome window, visit each tool you plan to use today and complete normal SSO:

- **Power BI** — `https://app.powerbi.com`
- **Jira** — `https://jira.example.com`
- **Confluence** — `https://confluence.example.com`

Sessions persist in the agent profile for the rest of the day. Tomorrow morning you'll relaunch the shim and sign in again — that's the rhythm.

**Why a separate Chrome?** Two reasons. First, you can keep your real Chrome open for normal browsing without Claude reaching into it. Second, the debugging port is a privileged hook — keeping it scoped to a dedicated profile is safer.

## 3. Try your first command

Pick a Power BI report you already have access to and copy its URL. Then in Claude Code, type:

```
/powerbi-scan <paste the URL here>
```

Here's what happens on screen:

1. Claude says something like "Attaching to your Chrome session..." and you'll see a brief pause.
2. It finds the existing signed-in Power BI tab (or opens a new one).
3. The agent Chrome window flips to your report and you watch it load.
4. Claude reads the page, identifies KPI tiles, and snaps a screenshot.
5. Back in chat you get a table of the top 5 KPIs (name, value, delta) and a path to the screenshot.

If Claude says "Looks like the agent's Chrome profile isn't signed in" — that's your cue to flip to the agent window and complete sign-in, then re-run the command. Claude will never try to type your password.

## 4. Try the other team skills

Once `/powerbi-scan` works, try these too:

### `/confluence-search <query>`

Searches `confluence.example.com` for the query and returns the top results with titles, URLs, and short excerpts. Good for "where did we document X?" questions.

### `/jira-bulk-update <JQL> <change>`

Applies a change (e.g., "set fixVersion to 2026.07") to every issue matching a Jira JQL filter. **Defaults to dry-run.** The first pass shows you a table of what *would* change — nothing is modified. To actually apply, **re-invoke the same command with `confirm=true` appended**:

```
/jira-bulk-update jql='assignee = currentUser() AND status = "In Progress"' \
                  action='add comment "released"' \
                  confirm=true
```

Hard cap: 50 tickets per run. If your JQL matches more, the skill refuses and asks you to narrow it.

This two-phase pattern is deliberate. Anything that writes to a system requires explicit re-invocation, every time.

## 5. Save your own flow

The real value shows up when you make BrowserMCP do *your* job, not just the shipped examples.

Describe a task in chat in plain English. For example:

> "Open the Weekly Shrink dashboard in Power BI, grab the top 10 stores by shrink %, and drop them into a markdown table."

Claude will navigate, click, read, and respond — the same primitives the team skills use. Once it works the way you want, type:

```
/save-as-flow weekly-shrink-top10
```

That flow is now in your slash menu forever as `/weekly-shrink-top10`. Next Monday you just type the slash command instead of re-explaining the task.

Personal flows live in `~/.claude/skills/<name>/` — they belong to you, not the team repo.

## 6. See your history

```
/flows-list
```

Shows two things:

- **Installed skills** — both team skills (`/powerbi-scan`, `/confluence-search`, `/jira-bulk-update`) and your personal flows.
- **Recent runs** — the last several flow invocations with timestamps and pass/fail status.

Detailed logs of every tool call live under `~/.browsermcp/runs/r-<id>.jsonl` if you ever need to dig in. Sensitive values are redacted automatically.

## 7. Sharing a flow with the team

You built a flow your whole team would use. What now?

**Phase 2 (right now):** send Sunil (@isunilsharma on GitHub) the `SKILL.md` file from `~/.claude/skills/<your-flow-name>/`. He'll review it and add it to `team-skills/` so the next team-onboarding run picks it up for everyone.

**Phase 3 (coming soon):** a `/promote-flow <name>` command that opens a PR against the BrowserMCP repo for you — review, merge, done. No manual hand-off.

## 8. Common errors and what to do

| Error message | What it means | Fix |
|---|---|---|
| `chrome_attach failed: ECONNREFUSED 127.0.0.1:9222` | The agent Chrome isn't running. | Run `chrome-shim.sh` again. |
| `Looks like the agent's Chrome profile isn't signed in` | Your SSO session in the agent profile expired or never existed. | Flip to the agent Chrome window, complete SSO, re-run the command. |
| `host not allowed: <domain>` | The flow tried to navigate to a site outside the corporate allowlist. | This is a guardrail. If the domain should be allowed, message Sunil to add it. |
| `extract: confidence=low` | Claude couldn't reliably parse the page. | Often the page hadn't finished loading. Re-run, or ask Claude to scroll/wait first. |
| `confirmation_required` on a write action | A destructive step is gated. | Re-invoke the same command with `confirm=true` appended (for skills like `/jira-bulk-update`), or tell Claude "yes, proceed with the write" and it will re-issue the click with `confirmed=True`. |
| The agent window won't open | Another Chrome is locking the profile dir. | Quit all Chrome windows (Cmd-Q), then re-run `chrome-shim.sh`. |
| Skill not found / `/foo` not in menu | The team-onboarding script didn't run or hasn't been re-run since this skill was added. | Re-run the onboarding installer at `team-onboarding/scripts/install.sh`. |

## 9. Where help lives

- **README** — `~/code/BrowserMCP/README.md` for the high-level overview.
- **docs/** — `~/code/BrowserMCP/docs/` has `userflow.md` (what users do), `design.md` (the why), `security.md` (what we protect), and `roadmap.md` (what's next).
- **Reference skill** — `~/code/BrowserMCP/team-skills/powerbi-scan/SKILL.md` is the gold-standard example to copy when writing your own.
- **People** — Sunil Sharma (@isunilsharma on GitHub) is the maintainer during the pilot. Ping him with bugs, ideas, or "is BrowserMCP the right tool for this?" questions.

Welcome aboard. Go break something — gently.

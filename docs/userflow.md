# User flow

> What teammates actually experience, end-to-end, in Claude Code Desktop.

The user-facing surface is a handful of slash commands plus natural-language chat. Three flows cover the lifecycle:

- **Flow A** — Run an existing team skill (e.g., `/powerbi-scan`)
- **Flow B** — Do something ad-hoc, then save it as a personal flow
- **Flow C** — Promote a personal flow to the team

---

## Flow 0 — One-time install

The first time a teammate uses BrowserMCP:

```bash
$ claude plugin install https://github.com/isunilsharma/BrowserMCP
✓ Installed plugin: browsermcp v0.3.0
✓ Added MCP server: browsermcp
✓ Installed skills:
   /powerbi-scan
   /confluence-search
   /jira-bulk-update
   /save-as-flow
   /promote-flow
   /flows-list
   /flows-edit
```

Done. They'll never run this again unless they want to update.

### One-time Chrome relaunch (handled by the plugin install)

Because Chrome needs to be running with `--remote-debugging-port` for BrowserMCP to attach, the installer prompts:

```
The browsermcp plugin needs to relaunch your Chrome to enable attach mode.
This will:
  - Close your existing Chrome windows (saves session)
  - Relaunch Chrome with remote-debugging enabled
  - Use your normal profile (SSO sessions preserved)

Proceed? [y/N]
```

After that, every Chrome launch uses the remote-debugging flag automatically (via a shell alias / launch shim installed by the plugin).

---

## Flow A — Running an existing team skill

Goal: a teammate runs `/powerbi-scan` to get KPIs from a Power BI report they normally check manually.

### Step 1: Invoke

In Claude Code Desktop they hit `/` to open the slash-command menu:

```
┌────────────────────────────────────────────────────────┐
│  /                                                     │
│  ─────────────────────────────────────────────────     │
│  📦 TEAM SKILLS (browsermcp)                              │
│  📊  /powerbi-scan       Scan a Power BI report        │
│  📚  /confluence-search  Search Confluence             │
│  🎫  /jira-bulk-update   Bulk-edit Jira tickets        │
│                                                        │
│  ✨ MY SKILLS                                           │
│  (none yet)                                            │
│                                                        │
│  ⚙️  META                                               │
│  💾  /save-as-flow                                     │
│  🚀  /promote-flow                                     │
│  📜  /flows-list                                       │
└────────────────────────────────────────────────────────┘
```

They pick `/powerbi-scan`.

### Step 2: Inputs

Claude Code prompts for the required input (defined in the skill's frontmatter):

```
🤖 What Power BI report do you want to scan?

   Examples:
   • "Q3 Sales Dashboard"
   • https://app.powerbi.com/groups/.../reports/abc123
   • "Last week's produce shrink"

👤 Q3 Produce Sales

🤖 What do you want from this report?  (default: top 5 KPIs)

👤 [Enter to accept default]
```

### Step 3: Execution

```
🤖 Starting powerbi-scan:
   Report: "Q3 Produce Sales"
   Goal:   top 5 KPIs + summary

   📎 Attaching to your Chrome session...
       ✓ Found profile: you@example.com
       ✓ Power BI session active

   🪟 Opened a new Chrome window for the agent

   🌐 Navigating to powerbi.example.com...
   🔍 Searching for report "Q3 Produce Sales"...
       ✓ Found: Q3 Produce Sales (FY26)
   📊 Reading dashboard tiles...
       ✓ Identified 8 KPI tiles
   🧠 Selecting top 5 by relevance...
   📸 Captured screenshot

   ─────────────────────────────────────────────────
   ✅ Done in 47 seconds

   Top 5 KPIs:
   ┌─────────────────────┬──────────┬─────────┐
   │ Metric              │ Value    │ vs LY   │
   ├─────────────────────┼──────────┼─────────┤
   │ Total Revenue       │ $4.2M    │ +12%    │
   │ Units Sold          │ 18,400   │ +8%     │
   │ Shrink %            │ 3.1%     │ -0.4pp  │
   │ Avg Basket          │ $228     │ +4%     │
   │ Top Category        │ Berries  │ -       │
   └─────────────────────┴──────────┴─────────┘

   📸 Screenshot:  ~/browsermcp-runs/2026-06-24-powerbi.png
   📝 Run log:     ~/browsermcp-runs/2026-06-24-114532.jsonl

🤖 Anything else? You can ask follow-ups about this data.
```

### Step 4: Follow-ups (free chat)

Once a flow finishes, the user is in normal Claude Code chat with all the context. They can:

```
👤 Email this to my manager
👤 Compare to Q2 numbers
👤 What's the YoY trend for "Shrink %"?
```

…and Claude handles them naturally (sometimes by invoking other BrowserMCP tools, sometimes by just reasoning over the data already gathered).

### What the user experiences physically

- Their main Chrome window: **untouched** ✅
- Their mouse: **never moved by the agent** ✅
- Their other apps (Slack, Outlook): **completely unaffected** ✅
- A small new Chrome window appears, does its thing, closes itself
- Total disruption: equivalent to a notification toast

---

## Flow B — Ad-hoc task that becomes a personal flow

Goal: a teammate has a recurring Monday task (check stale ServiceNow tickets). They don't know if BrowserMCP supports it — they just ask.

### Step 1: Try it ad-hoc

```
👤 Use browsermcp to open ServiceNow, find tickets assigned to me
   that are 'In Progress' but haven't been updated in 7+ days,
   and list them.

🤖 Sure — I'll use the browsermcp browser tools.

   📎 Attaching to Chrome...
   🌐 Opening servicenow.example.com...
   🔍 Navigating to "My Open Tickets"...
   📋 Reading ticket table (37 rows)...
   📅 Filtering by last-updated > 7 days...

   Found 4 stale tickets:

   ┌────────┬──────────────────────────────┬───────────┐
   │ Ticket │ Title                        │ Last upd. │
   ├────────┼──────────────────────────────┼───────────┤
   │ INC1234│ Power BI access for new hire │ 12 days   │
   │ INC1289│ Vendor portal SSO error      │ 9 days    │
   │ INC1301│ Shrink report missing data   │ 8 days    │
   │ INC1322│ Confluence space request     │ 7 days    │
   └────────┴──────────────────────────────┴───────────┘

   Want me to add a status comment to any of them?

👤 No this is great. I need to do this every Monday morning.
```

### Step 2: Save as a personal flow

```
👤 /save-as-flow

🤖 I'll save the chat we just had as a reusable flow.

   📛 Name?  (e.g., stale-tickets, monday-triage)

👤 stale-tickets

🤖 📝 Description for the / menu?
   (default: "List my ServiceNow tickets stale > 7 days")

👤 [Enter to accept default]

🤖 ⚙️  Any inputs you want to parameterize?
   I detected these in your task:
   • "7 days" → make this configurable? (default: yes)
   • "In Progress" → make this configurable? (default: no)

👤 7 days yes, status no

🤖 ✅ Saved!

   📁 ~/.claude/skills/stale-tickets/
      ├── SKILL.md
      └── README.md

   Try it now:
   /stale-tickets               # uses default 7 days
   /stale-tickets --days 14     # override
```

### What got saved on disk

`~/.claude/skills/stale-tickets/SKILL.md`:

```markdown
---
name: stale-tickets
description: List my ServiceNow tickets stale > 7 days
arguments:
  - name: days
    type: integer
    default: 7
    description: How many days since last update to consider "stale"
---

# Stale Tickets

When invoked:
1. Use browsermcp.chrome_attach() to attach to the user's Chrome session
2. Use browsermcp.navigate("servicenow.example.com/...")
3. Open "My Open Tickets" view via browsermcp.click("My Tickets")
4. Use browsermcp.read_page() to capture the ticket table
5. Filter rows where status="In Progress" AND last_updated > {{days}} days ago
6. Return as a formatted markdown table
7. Offer to add a status comment to any of them via /jira-bulk-update or browsermcp.click + browsermcp.type
```

### Step 3: Run it next Monday

```
👤 /stale-tickets
🤖 (skips the back-and-forth and just runs)
   Found 3 stale tickets: ...
```

Or with an override:

```
👤 /stale-tickets --days 14
🤖 Found 1 stale ticket (>14 days): ...
```

---

## Flow C — Promote a personal flow to the team

Goal: the teammate realizes `/stale-tickets` would be useful for the whole team.

### Step 1: Promote

```
👤 /promote-flow stale-tickets

🤖 I'll promote /stale-tickets from your personal skills to
   the team-shared browsermcp repo.

   📋 Reviewing the skill...
       ✓ No personal data hardcoded
       ✓ Uses parameterizable inputs
       ✓ Read-only (no destructive actions)
       ⚠️  Mentions "you@example.com" in description — remove? (y/n)

👤 y

🤖 ✓ Cleaned

   📝 Suggested PR title:
      "Add /stale-tickets skill — list stale ServiceNow tickets"

   📝 PR description (preview):
      ────────────────────────────────────────────────
      Adds a new team skill /stale-tickets that lists
      a user's stale ServiceNow tickets (default 7 days).

      Author:    @isunilsharma on GitHub
      Tested:    ✓ Worked on 3 separate runs locally
      Risk:      Low (read-only)
      Reviewer:  team-skill-reviewers
      ────────────────────────────────────────────────

   Open PR against github.com/isunilsharma/BrowserMCP? (y/n)

👤 y

🤖 ✅ PR #47 opened:
      https://github.com/isunilsharma/BrowserMCP/pull/47

   Next steps:
   • Reviewer from team-skill-reviewers will look at it
   • Once merged, ships in next plugin version
   • Teammates pick it up on `claude plugin update browsermcp`
```

### Step 2: Reviewer (separate person)

Standard GitHub PR review. The reviewer:
- Reads `team-skills/stale-tickets/SKILL.md`
- Runs the skill themselves to verify
- Checks for security/PII issues (see `docs/security.md` checklist)
- Approves and merges, or comments for revision

### Step 3: Distribution

After merge, CI on the BrowserMCP repo tags a new version (`v0.4.0`). When other teammates run `claude plugin update browsermcp`, they automatically get the new skill:

```bash
$ claude plugin update browsermcp
✓ Updated to v0.4.0
  + New skill: /stale-tickets
```

The new skill shows up in their `/` menu under TEAM SKILLS.

---

## The full skill discovery surface

The user's mental model of "what flows do I have" is the `/` menu:

```
┌────────────────────────────────────────────────────────┐
│  /                                                     │
│  ─────────────────────────────────────────────────     │
│  📦 TEAM SKILLS (browsermcp)                              │
│  📊  /powerbi-scan       Scan a Power BI report        │
│  📚  /confluence-search  Search Confluence             │
│  🎫  /jira-bulk-update   Bulk-edit Jira                │
│  📋  /stale-tickets      List stale ServiceNow tickets │
│                                                        │
│  ✨ MY SKILLS                                           │
│  📅  /monday-triage      My Monday morning routine     │
│                                                        │
│  ⚙️  META                                               │
│  💾  /save-as-flow                                     │
│  🚀  /promote-flow                                     │
│  📜  /flows-list                                       │
│  ✏️   /flows-edit                                       │
└────────────────────────────────────────────────────────┘
```

`/flows-list` opens a small dashboard view inside Claude Code with run history:

```
👤 /flows-list

🤖 Your flows:

   📊 /powerbi-scan       (team)     Last run: 2h ago    ✓
   📋 /stale-tickets      (team)     Last run: 6d ago    ✓
   📅 /monday-triage      (personal) Last run: 1h ago    ✓
   🎫 /jira-bulk-update   (team)     Never run            -

   Recent runs:
   • powerbi-scan(Q3 Produce)    ✓ 2h ago
   • monday-triage()             ✓ 1h ago
   • stale-tickets(days=14)      ✓ 6d ago
   • powerbi-scan(Q2 Bakery)     ✗ failed 2d ago — see logs

   /flows-edit <name>     to edit a saved flow
   /flows-delete <name>   to delete
```

---

## What about non-happy paths?

### Flow failed mid-run
```
🤖 ❌ powerbi-scan failed at step 4 (read_page)
   Reason: Power BI session expired

   What happened:
   • Attached to Chrome successfully
   • Navigated to Power BI
   • Got redirected to login page (session timeout)
   • Couldn't proceed without re-authentication

   Fix:
   • Open powerbi.example.com in your main Chrome
   • Sign in (you may need MFA)
   • Re-run /powerbi-scan

   Full log: ~/browsermcp-runs/2026-06-24-114532.jsonl
```

### User wants to cancel mid-run
Hit Esc / Ctrl-C in Claude Code. The MCP server receives a cancel signal, closes the agent window cleanly, and reports:

```
🤖 ⏸ Cancelled at step 3 of 7. No partial actions left behind.
```

### Destructive flow needs confirmation
Skills marked `risk: write` require an explicit confirmation step:

```
🤖 About to update 17 Jira tickets:
   - Set status to "In Progress"
   - Add comment: "Picked up by Sunil"

   Tickets affected: ACIP-1234, ACIP-1235, ... (15 more)

   Proceed? [yes / no / show full list]
```

No flow ever writes data without an explicit yes.

---

## Summary table: what teammate does when

| Goal | What they do | Where it saves | Who sees it |
|---|---|---|---|
| Run an existing team flow | `/powerbi-scan` + inputs | n/a | n/a |
| One-off task (no save) | Natural language chat | n/a | n/a |
| Save a chat as a flow | `/save-as-flow <name>` | `~/.claude/skills/<name>/` | Just them |
| Edit a personal flow | `/flows-edit <name>` | Same file | Just them |
| Share with the team | `/promote-flow <name>` | PR to `github.com/isunilsharma/BrowserMCP` | Team (after merge) |
| See history / re-run | `/flows-list` | Reads `~/browsermcp-runs/` | Just them |
| Get team updates | `claude plugin update browsermcp` | Updates `~/.claude/plugins/browsermcp/` | Everyone |

---

## Design intent recap

Three things make this UX work:

1. **Discoverability via `/` menu.** Users don't need to remember anything — the menu lists what's available.
2. **Promotion path = one command.** Going from "works for me" → "team has it" doesn't require touching git.
3. **Default to visible, non-blocking.** A separate browser window means trust builds quickly without sacrificing user productivity.

See `docs/techflow.md` for the wire-level details of how each step works.

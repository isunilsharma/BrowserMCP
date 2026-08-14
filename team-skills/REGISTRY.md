# Team Skills Registry

> Inventory of every skill shipped by this repo, plus the team-specific skills
> we're planning for each function. Keep this file in sync with the actual
> directory contents — the goal is one glance to answer "what skill does X?
> who owns it? is it safe?"

## Legend

**Risk levels**

| Level         | Meaning                                                              |
|---------------|----------------------------------------------------------------------|
| `read`        | Only reads — no UI writes, no off-machine sends                      |
| `write`       | Performs writes (forms, comments, sends), gated by user confirmation |
| `destructive` | Performs deletes / status changes that are hard to undo              |
| `meta`        | Writes to the user's own machine only (`~/.claude/`, `~/.browsermcp/`)  |

**Primary team** — `all` means universal (every user gets it regardless of
`--team`). A team name (`produce`, `hr`, …) means it only installs when the
user passes `--team=<that-team>`. See `docs/phase5-multi-team.md`.

**Maintainer** — the human who's on the hook for triage, deprecation calls,
and reviewing PRs that touch this skill. Defaults to the starter-set owner.

---

## Universal skills (`team-skills/all/` + flat/legacy)

These ship to every teammate regardless of `--team`. The 12 skills below are
the current starter set.

| Skill              | Risk         | Primary team | Args (required)                     | Maintainer                       | Description                                                                                       |
|--------------------|--------------|--------------|-------------------------------------|----------------------------------|---------------------------------------------------------------------------------------------------|
| `powerbi-scan`     | `read`       | all          | `report` (str)                      | @isunilsharma on GitHub      | Scan a Power BI report (corporate or Microsoft-hosted) and return its top KPIs.                  |
| `confluence-search`| `read`       | all          | `query` (str)                       | @isunilsharma on GitHub      | Search internal Confluence (confluence.example.com) by query, summarize top matching pages.       |
| `jira-bulk-update` | `write`      | all          | `jql` (str), `action` (str)         | @isunilsharma on GitHub      | Bulk-update Jira tickets matching a JQL filter. DRY-RUN by default; requires explicit `confirm`.  |
| `flows-list`       | `read`       | all          | —                                   | @isunilsharma on GitHub      | List all team and personal skills installed in Claude Code, plus recent BrowserMCP run history.   |
| `save-as-flow`     | `meta`       | all          | `name` (str)                        | @isunilsharma on GitHub      | Save the most recent chat as a reusable personal skill at `~/.claude/skills/<name>/SKILL.md`.     |
| `promote-flow`     | `meta`       | all          | `name` (str)                        | @isunilsharma on GitHub      | Promote a personal skill to the team repo via a GitHub pull request. Writes to internal git.      |
| `create-flow`      | `meta`       | all          | `name` (str)                        | @isunilsharma on GitHub      | Guided wizard for authoring a new personal skill from scratch via structured Q&A.                 |
| `record-flow`      | `meta`       | all          | `name` (str)                        | @isunilsharma on GitHub      | Record user actions in a browser tab and replay them as a saved skill. Phase 4 v0.1.              |
| `notify-slack`     | `write`      | all          | `text` (str), `title?` (str), `webhook_url?` (str) | @isunilsharma on GitHub | POST a message to a Slack incoming webhook. URL from arg or `$SLACK_WEBHOOK_URL`. PII-redacted.   |
| `notify-teams`     | `write`      | all          | `text` (str), `title?` (str), `webhook_url?` (str) | @isunilsharma on GitHub | POST to a Microsoft Teams connector webhook. URL from arg or `$TEAMS_WEBHOOK_URL`. PII-redacted.  |
| `notify-email`     | `write`      | all          | `to` (str), `subject` (str), `body` (str), `smtp_host?` (str), `smtp_port?` (int), `from_addr?` (str) | @isunilsharma on GitHub | Send an email via SMTP. Host/from default to `$SMTP_HOST`/`$SMTP_FROM` env.                       |
| `schedule`         | `meta`       | all          | `action` (list\|add\|remove), `skill_name?` (str), `cron?` (str), `args?` (json) | @isunilsharma on GitHub | Manage entries in `~/.browsermcp/schedules.toml` (registry only — execution layer pending IT decision). |

---

## Produce team (`team-skills/produce/`) — *planned, not yet shipped*

Skills tailored to category managers, replenishment planners, and store ops
folks on the produce side.

| Skill                    | Risk    | Primary team | Args                           | Maintainer                       | Description                                                                                  |
|--------------------------|---------|--------------|--------------------------------|----------------------------------|----------------------------------------------------------------------------------------------|
| `shrink-scan`            | `read`  | produce      | `store` (str), `category` (str)| @isunilsharma on GitHub      | Scan the Fresh Item Shrink Power BI report for a store/category, return shrink % and trend.  |
| `oos-report`             | `read`  | produce      | `region` (str)                 | @isunilsharma on GitHub      | Pull yesterday's out-of-stock report for a region; flag categories above threshold.          |
| `markdown-approve`       | `write` | produce      | `item_ids` (str), `pct` (int)  | @isunilsharma on GitHub      | Apply markdown % to a list of items in the merchandising tool. Defaults to dry-run.          |
| `vendor-followup-draft`  | `read`  | produce      | `vendor` (str)                 | @isunilsharma on GitHub      | Pull open POs for a vendor and draft (do not send) a follow-up email summary.                |

---

## HR team (`team-skills/hr/`) — *planned, not yet shipped*

| Skill                  | Risk         | Primary team | Args                             | Maintainer                       | Description                                                                                |
|------------------------|--------------|--------------|----------------------------------|----------------------------------|--------------------------------------------------------------------------------------------|
| `workday-pto-summary`  | `read`       | hr           | `team` (str)                     | @isunilsharma on GitHub      | Summarize PTO balances and upcoming requests for a team in Workday.                        |
| `org-chart-export`     | `read`       | hr           | `manager_email` (str)            | @isunilsharma on GitHub      | Walk down the org from a manager and export a CSV of direct + indirect reports.            |
| `req-status-batch`     | `read`       | hr           | `req_ids` (str)                  | @isunilsharma on GitHub      | Pull the current status of a list of open reqs from the ATS.                               |
| `new-hire-checklist`   | `meta`       | hr           | `start_date` (str)               | @isunilsharma on GitHub      | Generate a personalized day-1 checklist Markdown file from a template.                     |

---

## Finance team (`team-skills/finance/`) — *planned, not yet shipped*

| Skill                       | Risk         | Primary team | Args                            | Maintainer                       | Description                                                                              |
|-----------------------------|--------------|--------------|---------------------------------|----------------------------------|------------------------------------------------------------------------------------------|
| `cogs-variance-snapshot`    | `read`       | finance      | `period` (str)                  | @isunilsharma on GitHub      | Snapshot COGS variance vs. plan for a period from the finance Power BI workspace.        |
| `journal-entry-status`      | `read`       | finance      | `entry_ids` (str)               | @isunilsharma on GitHub      | Check posting status of a batch of journal entries in the GL system.                     |
| `invoice-approval-queue`    | `read`       | finance      | `approver_email` (str)          | @isunilsharma on GitHub      | List invoices waiting on a specific approver, oldest first.                              |
| `month-end-checklist`       | `read`       | finance      | `month` (str)                   | @isunilsharma on GitHub      | Run the month-end close checklist and report which items are blocked.                    |

---

## IT team (`team-skills/it/`) — *planned, not yet shipped*

| Skill                       | Risk         | Primary team | Args                            | Maintainer                       | Description                                                                              |
|-----------------------------|--------------|--------------|---------------------------------|----------------------------------|------------------------------------------------------------------------------------------|
| `incident-bridge-summary`   | `read`       | it           | `incident_id` (str)             | @isunilsharma on GitHub      | Pull the latest summary, owner, and timeline events from an active ServiceNow incident.  |
| `cab-ticket-triage`         | `read`       | it           | `cab_date` (str)                | @isunilsharma on GitHub      | Pull the change-advisory-board agenda for a date and pre-summarize each item.            |
| `oncall-handoff-draft`      | `read`       | it           | `team` (str)                    | @isunilsharma on GitHub      | Draft an on-call handoff doc by scanning open P1/P2 incidents and the last 24h pages.    |
| `okta-group-audit`          | `read`       | it           | `group_name` (str)              | @isunilsharma on GitHub      | Snapshot membership of an Okta group, diff vs. last snapshot stored locally.             |

---

## Adding a new skill

See `CLAUDE.md` → "Add a new team skill" and `docs/governance.md` for the
ownership / promotion rules. Don't forget to add the row here in the same PR.

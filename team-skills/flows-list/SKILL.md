---
name: flows-list
description: List all team and personal skills installed in Claude Code, plus recent BrowserMCP run history.
---

# Flows List

You are showing the user what skills they have available and what's run recently. Think of this as the "dashboard" view — a friendly inventory of what's on the shelf and what's been used. Keep it short and scannable. The whole interaction should feel like opening a desk drawer, not running a query.

No arguments. The user just typed `/flows-list` and wants to see the lay of the land.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="flows-list")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Without this, the dashboard would render itself as "<ad-hoc>" in its own Recent Runs section — embarrassing. Do not narrate this step to the user.

### 1. Enumerate ALL skills + distinguish team vs personal

Say something like: "Looking at what's installed..."

All Claude Code skills live under `~/.claude/skills/`. The BrowserMCP team skills land there as **symlinks pointing into the cloned BrowserMCP repo's `team-skills/<name>/` directories** (that's how `team-onboarding/scripts/install.sh` and the manual setup wire them up). Personal skills (saved by `/save-as-flow`) land there as regular directories.

So the right enumeration is:

```
ls -la ~/.claude/skills/ 2>/dev/null
```

For each entry:
- If the entry is a **symlink** that points into a path ending in `team-skills/<name>` → classify as **TEAM**.
- Otherwise (a regular directory) → classify as **PERSONAL**.

If `~/.claude/skills/` doesn't exist or is empty, treat as zero skills installed and move on. Don't fail the dashboard.

### 2. Read each skill's description

For every entry from step 1, `Read` the file `~/.claude/skills/<name>/SKILL.md` (symlinks resolve transparently — Read follows them). Pull the `description:` field out of the YAML frontmatter at the top.

- Frontmatter is the block between the leading `---` and the next `---`.
- Look for the literal line that starts with `description:` and take the rest of the line as the description (strip surrounding quotes/whitespace).
- If the SKILL.md file is missing, the frontmatter is unparseable, or there's no `description:` field, fall back to the literal string `(no description)`. Do not fail the whole dashboard for one bad skill.

Keep skill names in the order `ls` returned them (alphabetical on macOS/Linux). Don't re-sort.

### 3. Read recent run logs

Run logs live at `~/.browsermcp/runs/*.jsonl`. Each file is one run, named `r-<hex>.jsonl`, with one JSON object per line (one per tool call).

Use Bash to list them newest-first:

```
ls -1t ~/.browsermcp/runs/r-*.jsonl 2>/dev/null | head -30
```

(Pull 30 candidates so you have headroom — you'll filter and dedupe down to 10.)

For each file, in order:

- **Skip if older than 30 days.** Check the file's mtime (`stat -f %m <path>` on macOS, `stat -c %Y <path>` on Linux — try macOS form first since this is the corporate fleet). Compare to "now minus 30 days". This is a retention contract — see `docs/security.md`. Do not read older logs even if they're sitting on disk.
- **Read the file.** Every line has the same flat shape (written by `browsermcp/logging_jsonl.py`): `t` (ISO timestamp), `run_id`, `skill` (string or null), `tool`, `args` (redacted), `result_summary` (truncated string, NOT a dict), `duration_ms`. There is **no separate header line** — any line will give you `skill` and `run_id`.
- **Derive the run summary**:
  - `timestamp` — the file's mtime, formatted as `YYYY-MM-DD HH:MM` local time.
  - `skill` — value of the `skill` field on any line. If missing or null, use the literal `<ad-hoc>`.
  - `status` — `✗` if `result_summary` on any line contains the substrings `ok=False`, `"ok": false`, `Error`, `Traceback`, or `confirmation_required` in a context that wasn't followed by a successful confirmed re-run. Otherwise `✓`. Since `result_summary` is a stringified result, you match by substring, not by parsing.
  - `duration` — sum of `duration_ms` across all entries, rendered as `Xs` (one decimal place for sub-minute runs, e.g. `4.3s`; `Xm Ys` if 60s or longer).

Take the first **10 distinct runs** (one row per file — files are already one-run-each). Stop reading once you have 10.

### 4. Redact PII before rendering

Run logs go through `browsermcp.redact` at write time, but they may still contain incidental PII that slipped past field-name detection — emails, phone numbers, SSNs, anything that looks like a credit card. Before putting anything from a log into the chat:

- Scrub email addresses (`name@domain.tld` → `[email redacted]`)
- Scrub phone numbers (`NNN-NNN-NNNN`, `NNN.NNN.NNNN`, `NNN NNN NNNN` → `[phone redacted]`)
- Scrub SSN-shaped strings (`NNN-NN-NNNN` → `[SSN redacted]`)
- Scrub credit-card-shaped runs (13–16 digit sequences) → `[cc redacted]`
- Scrub anything else that looks like a personal identifier
- The skill name itself is fine — that's a kebab-case slug, not PII.

If in doubt, leave it out. The dashboard is a glance, not a forensic tool.

### 5. Render the dashboard

Reply with exactly three sections, in this order, using markdown tables. Use the emoji header lines literally.

**📦 TEAM SKILLS**

Columns: `name`, `description`, `last_run`, `status`.

- `last_run` — most recent timestamp from step 4 for a run where the `skill` field matched this name; `—` if never run.
- `status` — `✓` / `✗` from that most recent run; `—` if never run.

If there are no team skills, write `_No team skills installed._` instead of an empty table.

**✨ MY SKILLS**

Same columns, same rules, drawn from the personal skills list.

If there are none, write `_No personal skills yet. Save one with /save-as-flow._`.

**📜 RECENT RUNS**

Columns: `when`, `skill`, `status`, `duration`. One row per run from step 4, newest first.

If there are no runs in the last 30 days, write `_No runs in the last 30 days._`.

### 6. Footer

End the reply with a single italic line:

```
_Type /<name> to run a flow, or /save-as-flow to save the current chat as a new one._
```

That's it. Don't add commentary, don't auto-suggest cleanup, don't open Chrome. The user asked what's installed; you told them.

## Guardrails

- **30-day retention contract.** Never read or display data from `.jsonl` files whose mtime is older than 30 days. This is enforced in `docs/security.md`; the dashboard must honor it even though the files may still exist on disk.
- **Redact PII at the surface.** The redaction in `browsermcp/redact.py` runs at write-time but isn't a guarantee — emails, SSNs, and similar identifiers found in run logs must be scrubbed before they hit the chat.
- **No browser, no MCP tools.** This skill never calls `chrome_attach`, `navigate`, or any other BrowserMCP primitive. It's a pure local-filesystem read. Don't be tempted to "open the dashboard in a browser" — there is no dashboard URL.
- **Fail soft per row, not per dashboard.** A malformed SKILL.md or a corrupt JSONL line means that one row shows `(no description)` or gets skipped — it does not abort the whole listing.
- **Don't write anything.** No file edits, no new logs, no config changes. Read-only.

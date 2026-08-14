---
name: schedule
description: Manage scheduled runs of Claude Code skills — list, add, or remove entries in the BrowserMCP scheduling registry. REGISTRY ONLY — no execution layer is wired up yet.
arguments:
  - name: action
    type: string
    required: true
    description: Subcommand to run — one of `list`, `add`, or `remove`. Drives which other arguments are required.
  - name: skill_name
    type: string
    required: false
    description: The Claude Code skill to schedule (e.g. "powerbi-scan"). Required for `add` and `remove`; ignored for `list`.
  - name: cron
    type: string
    required: false
    description: Standard 5-field cron expression (e.g. "0 9 * * 1-5" for weekdays at 9am). Required for `add` and `remove`; ignored for `list`.
  - name: args
    type: string
    required: false
    description: JSON-encoded dict of arguments to pass to the scheduled skill on each run (e.g. `{"report": "Fresh Item Shrink"}`). Required for `add`; ignored for `list` and `remove`. Pass `{}` if the skill takes no arguments.
  - name: interactive
    type: boolean
    default: true
    description: Whether the scheduled run expects a user-attended Chrome session. Defaults to true. Non-interactive (service-account) runs are blocked until the execution layer lands.
  - name: enabled
    type: boolean
    default: true
    description: Whether the new entry is active when added. Defaults to true.
---

# Schedule

You are managing the BrowserMCP scheduling registry. This skill is a **subcommand dispatcher**: the `action` argument picks one of three flows (`list`, `add`, `remove`), and the remaining arguments are interpreted accordingly. The flows are all thin wrappers around the `schedule_*` MCP tools, which in turn persist to `~/.browsermcp/schedules.toml`.

**Critical caveat — read this and surface it to the user every time:** this is a **registry-only** stub. Adding an entry writes it to disk but does NOT install a cron job, does NOT spawn any background process, and does NOT actually run anything on a schedule. The execution layer is intentionally deferred until the service-account vs persistent-profile decision lands (see `docs/roadmap.md` Phase 4+). For now, this skill is a place to record *intent* — what you'd like to schedule — so the actual runner has a manifest to consume once it ships.

## Inputs

- `action` — one of `list`, `add`, or `remove`. Required.
- `skill_name` — the skill to schedule. Required for `add` and `remove`.
- `cron` — 5-field cron expression. Required for `add` and `remove`. The `(skill_name, cron)` pair is the primary key for `remove`.
- `args` — JSON-encoded dict of skill arguments. Required for `add`; pass `"{}"` if none.
- `interactive` — bool, defaults true. Only meaningful for `add`.
- `enabled` — bool, defaults true. Only meaningful for `add`.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="schedule")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Do not narrate this step to the user — the very next user-facing message is the registry-only disclaimer from step 1.

### 1. Announce the registry-only caveat

The very first thing you say to the user is:

> "Heads up: `/schedule` is registry-only right now — it persists your scheduled-run *intent* to `~/.browsermcp/schedules.toml`, but no cron job is installed and nothing will actually fire on its own until the execution layer lands. See `docs/roadmap.md` Phase 4+ for status."

This is the most important sentence in the whole run. Do not skip it. It prevents the user from thinking they've set up something that will actually run while they're away.

### 2. Validate the `action` argument

Normalize `action` with `str(action).strip().lower()`. It must be one of `list`, `add`, or `remove`. Anything else: respond with

> "Unknown action `<action>`. Valid actions are `list`, `add`, `remove`."

and STOP. Do not call any tools.

### 3. Dispatch on action

Now branch on the normalized `action`:

#### 3a. `list`

Say: "Reading the schedule registry..."

Call `schedule_list()`. It returns `{"schedules": [...], "count": N}`.

- If `count == 0`, say: "No scheduled runs are registered. Use `/schedule action=add ...` to add one." and STOP.
- Otherwise, render a markdown table with columns `Skill`, `Cron`, `Args`, `Interactive`, `Enabled`. One row per entry, in the order the registry returned them. Below the table, restate: "Reminder: these are registered intents, not active jobs."

#### 3b. `add`

Validate required args:

- If `skill_name` is missing or empty, respond `"add` requires `skill_name`."` and STOP.
- If `cron` is missing or empty, respond `"add` requires `cron` (5-field expression, e.g. `0 9 * * 1-5`)."` and STOP.
- If `args` is missing, respond `"add` requires `args` (JSON dict; pass `\"{}\"` if the skill takes no arguments)."` and STOP.

Parse `args` as JSON via `json.loads(args)`. If parsing fails, respond:

> "Could not parse `args` as JSON: `<error message>`. Pass a dict like `{\"report\": \"Fresh Item Shrink\"}`, or `{}` if the skill takes no arguments."

and STOP.

If the parsed value is not a dict, respond:

> "`args` must be a JSON object (dict), got `<type>`. Pass `{}` if the skill takes no arguments."

and STOP.

Normalize `interactive` and `enabled` with `str(value).strip().lower() in {"true","yes","y","1"}` or treat bool `True` as true; default each to `True` if missing.

Say: "Adding scheduled run for `<skill_name>` at cron `<cron>` (interactive=<bool>, enabled=<bool>)..."

Call `schedule_add(skill_name=<skill_name>, args=<parsed dict>, cron=<cron>, interactive=<bool>, enabled=<bool>)`. It returns `{"ok": True, "scheduled": {...}}`.

Reply with a short confirmation showing the scheduled entry's fields, then re-state the registry-only caveat: "Entry written to `~/.browsermcp/schedules.toml`. Remember: nothing will actually run on this cron yet — the execution layer is not wired up."

#### 3c. `remove`

Validate required args:

- If `skill_name` is missing or empty, respond `"remove` requires `skill_name`."` and STOP.
- If `cron` is missing or empty, respond `"remove` requires `cron`."` and STOP.

Say: "Removing scheduled run(s) matching skill=`<skill_name>` cron=`<cron>`..."

Call `schedule_remove(skill_name=<skill_name>, cron=<cron>)`. It returns `{"ok": True, "removed": <bool>}`.

- If `removed` is true, respond: "Removed entry for `<skill_name>` at cron `<cron>`."
- If `removed` is false, respond: "No entry matched skill=`<skill_name>` cron=`<cron>`. Use `/schedule action=list` to see what's registered."

### 4. Do NOT touch Chrome

This skill never opens a browser, never calls `chrome_attach`, and never navigates anywhere. It is pure registry CRUD on a local TOML file. If you find yourself reaching for a chrome tool, stop — you've taken a wrong turn.

## Guardrails

- **Registry only — no execution.** Always include the disclaimer in your first user-facing message. Users must not assume their entries will fire on the cron schedule. The execution layer is deferred until service-account vs persistent-profile is resolved.
- **No Chrome attach.** This skill is a CRUD wrapper around a TOML file; it does not drive a browser at any point.
- **Action is required.** Refuse with a helpful message if `action` is missing or not one of `list`/`add`/`remove`. Do not guess.
- **Validate `args` is a JSON dict on `add`.** Surface parse errors verbatim — never silently pass a malformed value to the tool.
- **`(skill_name, cron)` is the remove key.** If a user has two entries for the same skill on different crons, removing one leaves the other; if they want to wipe all entries for a skill, they need to call remove for each cron in turn.
- **Local file only.** The registry lives at `~/.browsermcp/schedules.toml`. It is not synced anywhere, not shared between users, and not backed up by this skill.
- **Fail loud, don't thrash.** Bad cron expressions, missing required args, JSON parse failures — surface them clearly and STOP. Do not retry or "try to be helpful" by guessing the user's intent.

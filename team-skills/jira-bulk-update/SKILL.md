---
name: jira-bulk-update
description: Bulk-update Jira tickets matching a JQL filter — DRY-RUN by default, requires explicit user confirmation before applying changes.
arguments:
  - name: jql
    type: string
    required: true
    description: Jira JQL filter (e.g. "assignee = currentUser() AND status = 'In Progress'").
  - name: action
    type: string
    required: true
    description: What to do to the matching tickets (e.g. "set status to Done", "add comment 'released'", "assign to alice@example.com").
  - name: confirm
    type: boolean
    default: false
    description: Set to a truthy value to actually apply changes. Recognized as "apply mode" — case-insensitive — "true", "True", "yes", "1", or the boolean True. Defaults to false; anything else (including absence) stays in dry-run.
---

# Jira Bulk Update

You are running a bulk update against Jira tickets on `jira.example.com`. This is the most safety-sensitive skill in the library — you can mutate dozens of tickets in seconds. The whole flow is built around a **preview-then-confirm** gate: the first invocation always previews, and only a second invocation with `confirm=true` (or `True`, `"yes"`, `1` — anything truthy) actually writes.

Keep the user informed with short progress messages in chat — they should feel like a careful teammate is narrating each step and pausing for sign-off, not like a script ran away with their tracker.

## Inputs

- `jql` — the JQL filter that selects the tickets to act on.
- `action` — a short natural-language description of what to do (status change, comment add, assignee change).
- `confirm` — defaults to `false`. **Any truthy value** flips into apply mode: the boolean `True`, the strings `"true"` / `"True"` / `"TRUE"` / `"yes"` / `"y"`, or the integer `1`. Anything else (false, "", "no", "0", missing) stays in dry-run. Normalize the user's input with: `str(confirm).strip().lower() in {"true","yes","y","1"}`.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="jira-bulk-update")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Do not narrate this step to the user — the very next user-facing message is the dry-run/apply-mode announcement from step 1.

### 1. Announce the mode up front

**Normalize first:** treat `confirm` as truthy if `str(confirm).strip().lower() in {"true","yes","y","1"}` OR `confirm is True`. Call that the "apply flag" for the rest of these instructions.

If the apply flag is FALSE, the very first thing you say to the user is:

> "Running as DRY-RUN — no changes will be made until you re-invoke with `confirm=true`."

If the apply flag is TRUE, say instead:

> "Confirmed apply mode — I will mutate matching tickets. I will still re-show the list and ticket-level outcomes as I go."

This is the most important sentence in the whole run. Do not skip it.

### 2. Attach to the user's Chrome

Say: "Attaching to your Chrome session..."

Call `chrome_attach()` with the default port. If it fails, tell the user they need to relaunch Chrome with the `chrome-shim.sh` and STOP — do not try to start Chrome yourself.

### 3. Find an existing signed-in Jira tab — or open a fresh one

Say: "Finding an existing signed-in Jira tab (or opening a new one)..."

Call `chrome_find_or_open_window(url_pattern="jira.example.com")` and keep the returned `window_id`. Thread that `window_id` through every subsequent tool call. Reusing an existing signed-in tab avoids forcing a new SSO bootstrap.

### 4. Navigate to the JQL search results

Say: "Loading the JQL search results..."

URL-encode the `jql` argument and `navigate(url="https://jira.example.com/issues/?jql=<encoded>", window_id=<id>)`.

If the resulting page title contains "Sign in" or "Log in", tell the user: "Looks like the agent's Chrome profile isn't signed in to Jira — open the agent window and complete sign-in, then re-run me." and STOP. Do not type credentials yourself.

### 5. Wait for the issue list to render

Call `wait_for(condition="issue list renders", timeout_s=15, window_id=<id>)`. If it times out, scroll to top once and re-wait briefly; if it still hasn't loaded, surface the error and STOP.

### 6. Read the full issue list

Say: "Reading the matching tickets..."

Call `read_page(viewport_only=False, window_id=<id>)` so tickets below the fold are captured. Then call `extract()` with this schema and prompt:

- `schema`: `{"issues": [{"key": "str", "title": "str", "status": "str", "assignee": "str"}]}`
- `prompt`: `"Find every Jira issue row in the search results. For each row, return the issue key (e.g. ACIP-123), the summary/title, the current status, and the assignee display name."`
- `window_id`: `<id>`

If `confidence` comes back as `low`, say so honestly and STOP — never act on a list you couldn't read cleanly.

### 7. Enforce the 50-ticket hard cap

Count the tickets returned. **If the count is greater than 50, REFUSE the operation** with:

> "Found N tickets matching `<jql>` — that's over the 50-ticket safety cap for this skill. Please narrow your JQL (add an explicit date range, a project, a status, etc.) and re-invoke."

Do not let the user override this cap inside a single invocation. It exists to prevent a typo'd JQL from rewriting an entire project.

If the count is zero, say "No tickets matched — nothing to do." and STOP.

### 8. Present the preview

Show the user:

1. A one-line header: `Found N tickets matching the JQL. Planned action: <action>.`
2. A bulleted sample of the **first 5** issues (or all of them if N <= 5), formatted as `- ACIP-XXX — <title> — status: <status> — assignee: <assignee>`.
3. If N > 5, a trailing line: `(... and <N-5> more — full list will be acted on in apply mode.)`
4. The exact apply-mode incantation: `To apply, re-invoke as /jira-bulk-update jql='<original jql>' action='<original action>' confirm=true`.

### 9. If still in dry-run, STOP HERE

If the apply flag is FALSE, end the run after step 8 with:

> "DRY-RUN complete. Review the list above and re-invoke with `confirm=true` if it looks right."

Do not proceed. Do not "just navigate to the first ticket to be helpful". The dry-run is the contract.

### 10. Apply mode — iterate and mutate

Only reachable if the apply flag is TRUE. Say: "Applying `<action>` to <N> tickets now..."

Initialize an empty `results` log: `[{key, status: "succeeded"|"failed", reason?: str, url: str}, ...]`.

For each ticket in the extracted list (in order, up to 50):

1. `navigate(url="https://jira.example.com/browse/<KEY>", window_id=<id>)` and `wait_for(condition="issue page renders", timeout_s=15, window_id=<id>)`.
2. Dispatch on the `action` string:
   - **Set status** (e.g. `"set status to Done"`):
     - `click(description="status dropdown button on the Jira issue", window_id=<id>, confirm_intent="write", confirmed=True)`
     - `wait_for(condition="status transition menu appears", timeout_s=10, window_id=<id>)`
     - `click(description="status transition option labelled '<target>'", window_id=<id>, confirm_intent="write", confirmed=True)`
   - **Add comment** (e.g. `"add comment 'released'"`):
     - `click(description="add comment button", window_id=<id>, confirm_intent="write", confirmed=True)`
     - `type_text(field="comment body", text="<the literal comment text>", window_id=<id>, confirm_intent="write", confirmed=True)`
     - `click(description="save comment button", window_id=<id>, confirm_intent="write", confirmed=True)`
   - **Assign** (e.g. `"assign to alice@example.com"`):
     - `click(description="assignee field on the Jira issue", window_id=<id>, confirm_intent="write", confirmed=True)`
     - `type_text(field="assignee picker", text="<target user>", window_id=<id>, confirm_intent="write", confirmed=True)`
     - `wait_for(condition="assignee suggestion list appears", timeout_s=10, window_id=<id>)`
     - `click(description="assignee suggestion matching '<target user>'", window_id=<id>, confirm_intent="write", confirmed=True)`
3. After the mutation, `read_page(viewport_only=True, window_id=<id>)` and confirm the change appears applied (new status visible, new comment visible, new assignee visible). If the page text contains "you don't have permission", "Forbidden", "403", or any clear permission-denied signal, **append `{key, status: "failed", reason: "permission denied"}` to results and ABORT the whole loop** — stop processing further tickets. Do not retry. Do not move on to ticket N+1.
4. Otherwise, record `{key, status: "succeeded", url: "https://jira.example.com/browse/<KEY>"}`.
5. If a non-permission error surfaces (timeout, element not found, unexpected modal), record `{key, status: "failed", reason: "<short reason>"}` and continue with the next ticket.

**Every single click/type_text that mutates state MUST pass `confirm_intent="write"` and `confirmed=True`.** The MCP server's interaction layer enforces this — a write-class call without `confirmed=True` will come back with `ok=false` and a `confirmation_required` note, and you should treat that as a bug in this skill (not as something to retry blindly).

### 11. Report the outcome

Once the loop ends (either naturally or via the permission-denied abort), reply with:

1. A one-line header: `Bulk update complete: <S> succeeded, <F> failed, <K> tickets attempted out of <N> matched.`
2. A markdown table with columns `Key`, `Status`, `Detail`. Use `Detail` for the failure reason on failed rows, or the linked URL on succeeded rows.
3. If the loop aborted due to a permission error, an explicit final line: `Aborted after ticket <KEY> due to a permissions error. Remaining tickets were NOT touched.`
4. The screenshot path if you took one at the end (optional — only if it's actually useful for the user).

Do not close the window at the end — the user may want to spot-check the changes. If they ask to clean up, call `chrome_close_window(window_id=<id>)`.

## Guardrails

- **Hard cap, no overrides:** never act on more than 50 tickets in a single invocation. If the JQL matches more, refuse and ask the user to narrow it. The user cannot lift this cap from inside a skill call.
- **Dry-run is the default.** Any truthy `confirm` value (`True`, `"true"`, `"yes"`, `"1"`, case-insensitive) flips into apply mode. Anything else (false, "no", "0", missing) keeps you in dry-run. When in doubt, stay in dry-run.
- **Every mutation passes `confirm_intent="write"` and `confirmed=True`.** The MCP server's two-phase confirm is the canonical safety mechanism — never bypass it, never wrap it, never pre-set `confirmed=True` on a `read` call to "be safe". `read` clicks stay `confirm_intent="read"`.
- **Permission errors abort the run immediately.** A single 403 / "you don't have permission" is enough — do not keep trying the next ticket. Permissions issues usually mean the user's account or the workflow doesn't allow what was asked, and grinding through 49 more tickets will just produce noise (or worse, partial state across projects).
- **Host allowlist:** only `jira.example.com` (covered by the `*.example.net` glob). `navigate()` enforces this and will refuse any drift.
- **Never type credentials.** SSO is the user's job. If you hit a sign-in page, stop and ask.
- **Log every ticket-level outcome** in the final report so the user can audit exactly what changed. Every tool call is also being logged to `~/.browsermcp/runs/r-*.jsonl` by the server — but the user shouldn't have to read JSONL to find out what you did.
- **Fail loud, don't thrash.** If extraction confidence is low, if the issue list doesn't render, if the action string is ambiguous — stop and surface the issue. Bulk-write skills do not get to "try a few approaches" silently.

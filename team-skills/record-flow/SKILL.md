---
name: record-flow
description: Record user actions across browser tabs and replay them as a saved skill. Phase 4 v0.4 — real-time event channel, shadow DOM, iframes.
arguments:
  - name: name
    type: string
    required: true
    description: Name of the personal skill to create from this recording.
  - name: mode
    type: string
    default: record
    description: "'record' to capture a new session, 'replay' to test an existing recording."
---

# Record Flow (Phase 4 v0.4)

You help the user **record** browser actions across one or more tabs and later **replay** them. Capture is transparent and survives real navigation — full page reloads, SPA route changes (pushState/replaceState), new tabs, and redirect chains all keep recording.

The server runs a background drain loop every ~2s, so you do NOT poll mid-recording. Just start the session, wait for the user to type `stop`, then call stop. All events accumulate server-side.

## Inputs

- `name` — on-disk filename (`~/.browsermcp/recordings/<name>.jsonl`) and the eventual `/<name>` skill slug.
- `mode` — `"record"` (default) or `"replay"`.

## Flow

### 0. Tag this run

Call `set_skill_context(skill="record-flow")`. Do not narrate.

### 1. Validate the name

Kebab-case, 3–40 chars, no reserved words. Stop on invalid — do not auto-rename.

---

### 2A. mode="record"

#### a. Set expectations

> "I'll open a fresh tab as your starting point. I'm also watching every currently-open tab, and any new tab you open will be captured automatically. The recorder survives full page reloads. Type `stop` when done. Password values are never recorded."

#### b. Start the session

Call `recording_start_session()`. Returns:
- `anchor_window_id` — fresh tab
- `existing_tabs` — count of pre-existing tabs being captured
- `init_script_ok` — whether the context-wide auto-install worked
- `auto_drain_interval_s` — how often the server is sweeping

#### c. Tell the user we're live

> "Recording started. Fresh tab `<anchor_window_id>`. `<existing_tabs>` existing tabs being captured. Server auto-drains every `<auto_drain_interval_s>` seconds. Use the browser naturally — type `stop` here when done."

#### d. Wait for stop

Do NOT poll. The background drain task is collecting events server-side every 2 seconds. Just wait for the user's `stop` message.

If the user asks for a status check during recording, you may optionally call `recording_drain_session()` once — that returns ONLY events captured since the last sweep (since the background task is also draining, this manual call may return very few events; that's fine, the bulk are already in `accumulated_events`).

#### e. Stop, parameterize, save

When the user says `stop`:

1. Call `recording_stop_session()` — cancels the background drainer, does a final sweep, returns ALL accumulated events from the entire session.
2. Show the user a one-line breakdown by kind ("N clicks, M inputs, K keys, J navigates across W tabs").
3. Call `recording_extract_params(events=<all_events>)`. Show suggestions and ask: "Use these parameters? (yes / no / edit)"
4. Call `recording_save(name=<name>, events=<all_events>)`.
5. Confirm: "Recorded N events → `~/.browsermcp/recordings/<name>.jsonl`. Run `/record-flow name=<name> mode=replay` to test."

---

### 2B. mode="replay"

1. `recording_load(name=<name>)` — if not found, tell user and stop.
2. `chrome_attach()` + `chrome_find_or_open_window(url_pattern="*")` for the fallback window_id.
3. `recording_replay(name=<name>, window_id=<fallback>)` — the engine opens one live tab per distinct recorded `window_id` and routes events accordingly.
4. Show the per-step result table. Summarize failures at the end.
5. Offer to promote into a permanent `~/.claude/skills/<name>/SKILL.md`.

---

### 3. Honest limitations

> "Phase 4 v0.4. **Working:** real-time event delivery via `page.expose_function` (no buffer, no drain race, cross-origin safe), multi-tab capture, context-wide auto-install, open shadow DOM coverage, iframe coverage (init script applies to all frames), SPA route changes, Enter/Tab/Escape keys, debounced input flush on Enter, multi-tab replay. **Remaining limits:** (1) closed shadow roots are inaccessible by browser design — affects a minority of widgets; (2) password VALUES never captured by design (field label is captured so replay can target the field — you type the password fresh at replay time)."

## Guardrails

- All replay navigation flows through `navigate()` (host allowlist enforced).
- Password values filtered client-side in the JS — never reach Python.
- Recordings at `~/.browsermcp/recordings/`, 30-day retention, redacted on write and on load.
- Recording only starts on explicit `/record-flow` — no ambient capture.

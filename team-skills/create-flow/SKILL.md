---
name: create-flow
description: Guided wizard for authoring a new personal Claude Code skill from scratch via a structured Q&A — for tasks you can describe but haven't done ad-hoc first.
arguments:
  - name: name
    type: string
    required: true
    description: The new skill's command name, in kebab-case (no leading slash, no spaces).
  - name: description
    type: string
    required: false
    description: One-line description of the new skill. Defaults to a one-liner you assemble from the goal answer (Q1).
---

# Create Flow

You are walking a teammate through authoring a brand-new personal Claude Code skill from scratch. Unlike `/save-as-flow`, the user hasn't already done the task in chat — they only have it *in their head*. Your job is a structured Q&A wizard: ask one short question at a time, capture answers into an internal plan, confirm the plan back, then write `~/.claude/skills/<name>/SKILL.md`. After the file lands, `/<name>` will show up in the slash menu permanently.

Keep the conversation tight. Each question is one line; each answer is short. Don't pad with explanations between questions. The whole interaction should feel like a quick intake form, not a lecture.

## Inputs

- `name` — the new skill's command name, kebab-case (e.g. `weekly-store-scan`, `jira-triage-mine`).
- `description` — optional one-line description. If omitted, you'll synthesize one from the goal answer in Q1.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="create-flow")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Even though this skill doesn't touch Chrome, it still calls Bash/Write through the MCP server's logging path, and we want accurate attribution in `/flows-list`. Do not narrate this step to the user.

### 1. Validate the name

Say something like: "Validating the skill name `<name>`..."

Check that `name`:
- matches `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (kebab-case, starts/ends with alphanumeric, lowercase only)
- contains no slashes, spaces, dots, or non-ASCII characters
- is not a reserved word: `help`, `clear`, `exit`, `save-as-flow`, `create-flow`, `record-flow`, `flows-list`, `promote-flow`

If validation fails, tell the user exactly what's wrong with the name and stop. **Do not auto-fix it** — let them re-run with a corrected name.

### 2. Check for an existing skill at that path

Resolve the target path: `~/.claude/skills/<name>/SKILL.md` (expand `~` to the user's home directory using Bash `echo $HOME` if needed).

If the directory already exists, ASK: "A skill named `/<name>` already exists at `~/.claude/skills/<name>/`. Overwrite it?" Wait for a clear yes/no. If they say no — or anything ambiguous — stop without writing.

If the directory does not exist yet, you'll create it in step 6.

### 3. Walk the user through the template via Q&A

Ask **one question at a time**, accept short answers, and build internal state as you go. Don't dump all five questions at once.

**Q1 — Goal.** Ask: "What's the one-line goal? (e.g., 'pull yesterday's stale ServiceNow tickets')"
- Capture as `goal`. This becomes the opening paragraph of the new skill's body, and — if the user left `description` blank — the frontmatter description too.

**Q2 — Starting URL or app.** Ask: "What's the starting URL or app? (e.g., 'https://servicenow.example.com', or 'none' if this isn't a browser task)"
- Capture as `start_url`. If they say `none` / blank, this is a non-browser skill and you'll skip the chrome_attach + chrome_find_or_open_window steps in step 5.

**Q3 — Steps.** Ask: "Walk me through the steps the bot should do. Type 'done' when finished. Step 1?"
- For each step the user types, capture it verbatim into a `steps` list, then ask "Step N+1?" with the next number.
- Stop the loop when they type `done` (case-insensitive) or an empty line.
- **Keep their phrasing.** Don't auto-rewrite or "improve" their wording — that's the user's voice and they'll need to recognize it later.
- **At most 12 steps.** If they go past 12, stop the loop and say: "That's 12 steps — this skill is getting big. Consider splitting it into smaller sub-skills (e.g. `<name>-prep` and `<name>-run`) for easier debugging and reuse. Want to continue anyway, or stop here?" Accept their call and proceed.

**Q4 — Parameters.** Ask: "Any parameters (things you'd swap on different runs)? List them like 'days (default 7), store-number', or 'none'."
- Parse into a `parameters` list of `{name, default}` dicts. Empty/`none` means no `arguments` section in the frontmatter.

**Q5 — Write actions.** Ask: "Does this skill write/change anything (clicks Submit, Approve, sends, deletes)? If yes, name the action so we add a confirm gate."
- If yes, capture as `write_action` (a short description). You'll wire `confirm_intent="write"` + `confirmed=True` on the relevant tool call(s) in step 5, and add an explicit user-confirmation step right before it fires.
- If no, the skill is read-only — no write gate needed.

**Dangerous-behavior check.** While capturing answers, watch for obviously dangerous behavior phrasing — e.g. "delete all my tickets without asking", "approve every PR I see", "wipe the queue silently". If you spot it, STOP. Tell the user: "Step N reads like `<paraphrase>` — that's a destructive action without a human-in-the-loop gate, and I won't write a skill that does that. Either reword the step to include explicit confirmation, or stop here." Do not proceed until they reword.

**Secret/PII scan.** Walk every captured answer (`goal`, `start_url`, each step, each parameter, `write_action`) for credential or PII patterns:
- Field names or substrings matching `/password|passwd|token|api[_-]?key|secret|bearer|auth|ssn|dob|pin|cookie|session/i`
- Values that look like credentials: long base64-ish strings, JWTs (`eyJ...`), bearer tokens, anything matching `^[A-Za-z0-9_-]{32,}$` in an obvious auth context
- US SSN pattern (`\d{3}-\d{2}-\d{4}`), full credit card numbers (16 digits, possibly hyphenated)

If you find any match, REFUSE: "Found a potentially sensitive value in your answer to Q<n> — looks like `<masked preview>`. I won't bake a credential into a skill file. Re-run `/create-flow <name>` and skip that detail (the skill should fetch credentials from the user's SSO session, not hardcode them)." Stop without writing.

### 4. Confirm the plan back to the user

Once Q1–Q5 are captured (and no refusal triggered), summarize the plan so the user can sanity-check before any file is written. Show:

- **Skill name:** `/<name>`
- **Description:** the user-provided `description`, or — if they left it blank — a one-liner you derive from `goal` (e.g. if `goal` is "pull yesterday's stale ServiceNow tickets", a reasonable description is "Pull yesterday's stale ServiceNow tickets and return them as a list.")
- **Steps:** numbered list of the captured `steps`, in order.
- **Parameters:** the captured `parameters` (or "(none)").
- **Write gate:** "Read-only — no write actions." OR "Has a write gate before: `<write_action>`."

Then ask: "Looks right? (yes / no / edit)"

- **yes** → proceed to step 5.
- **edit** → ask: "Which part — name, description, steps, parameters, or write gate?" Loop back to the relevant question, capture the new value, and re-show the full plan. Repeat until they say yes or no.
- **no** → stop without writing. Say: "OK — nothing written. Re-run `/create-flow <name>` when you're ready."

### 5. Translate the answers into a SKILL.md

Say: "Writing `/<name>` to `~/.claude/skills/<name>/SKILL.md`..."

Resolve the absolute path by expanding `~` (use Bash `echo $HOME` if you don't already have it; do not assume `/Users/<x>`). Create the parent directory with `mkdir -p`. Then write the file with `Write` using the absolute path.

The file content must follow this exact structure. **Build it programmatically — do not copy the template literally including these notes.**

**Frontmatter** — between two `---` fences:
- `name:` ← the user-provided skill name from step 1
- `description:` ← user-provided description, or the synthesized one-liner from step 4
- `arguments:` ← a YAML list, one entry per captured parameter. **Omit the entire `arguments:` key if `parameters` is empty.** Each entry: `name`, `type` (string|integer|boolean — infer from the default value's shape), `required` (false if the user gave a default, true otherwise), `description` (short, derived from the parameter name).

**Body** — markdown, in this order:

```
# <Title Case of skill name>

<One paragraph restating `goal` in "you are doing X" voice, mirroring the powerbi-scan opener.>

## Inputs

- `<argname>` — <description>.
- <one bullet per parameter>

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="<name>")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Do not narrate this step to the user.

### 1. Attach to the user's Chrome

Say something like: "Attaching to your Chrome session..."

Call `chrome_attach()` with the default port.

### 2. Find an existing signed-in tab — or open a fresh one

Say: "Finding an existing signed-in tab (or opening a new one)..."

Call `chrome_find_or_open_window(url_pattern="<start_url host>")` and keep the returned `window_id`. Pass this `window_id` to every subsequent tool call.

### 3. <first user-described step>

Say something like: "<short progress message derived from the step>"

Call `<best-inferred tool>(<args>, window_id=<id>)`.

### 4. <next step>

<one numbered step per captured user step>

### N. Respond to the user

<How to summarize the final result.>

## Guardrails

- Stay within the host allowlist enforced by `navigate()`.
- Never type credentials. SSO is the user's job.
- If a tool fails, surface the error and stop rather than thrashing.

---
_Created by `/create-flow` on <YYYY-MM-DD>._
```

**Omit the `## Inputs` section entirely if `parameters` is empty.** The number of numbered Flow steps depends on how many user steps were captured — don't pad or trim arbitrarily.

The final file must NOT contain any of the angle-bracket placeholders or square-bracket commentary from this template — those are *instructions to you*, not literal text to write. Substitute every `<placeholder>` with the concrete value before calling Write.

A few rules when generating the body:

- **Step 0 always present:** Add a step 0 calling `set_skill_context(skill="<name>")` so the skill self-tags in the run log, exactly like the template above. Same wording: "Do not narrate this step to the user."
- **Chrome steps conditional on `start_url`:** If `start_url` was a URL (not `none`), include `chrome_attach()` as step 1 and `chrome_find_or_open_window(url_pattern="<host of start_url>")` as step 2, exactly like `powerbi-scan`. If `start_url` was `none`, skip both and start the user's steps at step 1.
- **Tool inference per step:** For each captured user step, render it as a numbered step with two short lines: a "Say something like: '<short progress>'" line, then a "Call `<tool>(<args>, window_id=<id>)`." line. Pick the tool by best inference from the user's phrasing:
  - "click X" / "press X" / "select X" → `click(description=...)`
  - "type X into Y" / "fill in Y with X" / "search for X" → `type_text(field=..., text=...)`
  - "go to URL" / "open page" / "navigate to" → `navigate(url=...)`
  - "read the page" / "see what's there" → `read_page()`
  - "pull out the X" / "extract the Y" / "get the list of Z" → `extract(schema=..., prompt=...)`
  - "wait for X" / "until Y loads" → `wait_for(condition=..., timeout_s=...)`
  - "screenshot" / "snap a picture" → `screenshot()`
  - "scroll down" / "scroll to bottom" → `scroll(direction=...)`
  - When unsure, default to `click(description=<user's phrasing>)` and add a comment that the tool inference is a best guess.
- **Window-id threading:** If chrome steps were included, thread `window_id=<id>` through every subsequent Chrome-touching call. Use the literal placeholder `<id>` in the generated file — the running skill will substitute the actual id at runtime.
- **Write-gate plumbing:** If Q5 captured a `write_action`, locate the step that performs that action and:
  1. Insert an explicit user-confirmation step BEFORE it: a step that says "Show the user exactly what's about to change and ask 'Proceed? (yes/no)'. Stop on anything other than a clear yes."
  2. On the mutating tool call itself, add `confirm_intent="write"` and `confirmed=True` as arguments. Match the two-phase confirm pattern from `team-skills/jira-bulk-update/SKILL.md`.
- **Parameter placeholders:** Reference parameters in the body as `{{argname}}` (double-curly) inside prose and tool-call examples. The skill runtime substitutes literal values at invocation time.
- **Guardrails section:** Always include the three-bullet Guardrails block above. If the skill has a write gate, add a fourth bullet: "Never auto-confirm write actions. The two-phase `confirm_intent` pattern exists to keep a human in the loop."
- **Footer:** End with `_Created by /create-flow on YYYY-MM-DD._` using today's date.

### 6. Write the file

Use the `Write` tool with the absolute path resolved from `$HOME` in step 5. If the parent directory doesn't exist, `mkdir -p ~/.claude/skills/<name>/` first.

Only fall back to `bash` + heredoc if `Write` is unavailable — `Write` is preferred so the tool-call audit log captures the file content cleanly.

### 7. Verify and confirm to the user

After the file is written, run `ls ~/.claude/skills/<name>/SKILL.md` to confirm it landed, and `head -20 ~/.claude/skills/<name>/SKILL.md` to verify the frontmatter is valid YAML (name and description present, arguments well-formed if any).

Then reply to the user with exactly this shape:

> Saved `/<name>` to `~/.claude/skills/<name>/SKILL.md`. Try `/<name>` to run it. If you need to tweak the steps, edit the file directly or call `/create-flow <name>` again to overwrite.

If the verification step shows any anomaly (file missing, frontmatter malformed), tell the user what's wrong and offer to retry.

## Guardrails

- **Never write outside `~/.claude/skills/<name>/`.** This skill is per-user, per-machine. Team skills go through code review under `team-skills/` — `/create-flow` is for personal experiments only. Never write to the repo's `team-skills/` directory.
- **Never auto-fix invalid names.** If the user passes a bad name (uppercase, spaces, leading slash, reserved word), tell them and stop — let them re-run with the corrected value.
- **Never overwrite without explicit confirmation.** Step 2's overwrite prompt is non-negotiable.
- **Refuse obviously dangerous behavior.** If a captured step describes a destructive action without a human-in-the-loop gate (e.g. "delete all my tickets without asking"), surface the concern and STOP — don't write the skill.
- **Refuse credentials and PII in any answer.** The secret/PII scan in step 3 is non-negotiable; refuse and surface the offending value (masked) to the user. Do not write a partial or "cleaned" version.
- **Never type credentials.** The generated skill should rely on the user's existing SSO session, just like `powerbi-scan`. Don't generate steps that hardcode passwords or tokens.
- **Fail loudly.** If any step in the wizard errors (e.g. `Write` fails, `mkdir -p` errors), surface the error and stop. Don't paper over it.
- **No network calls.** This skill is pure local Q&A + file I/O against `~/.claude/skills/`. Do not navigate, fetch, or screenshot. The only Bash you need is `echo $HOME`, `mkdir -p`, `ls`, and `head`.

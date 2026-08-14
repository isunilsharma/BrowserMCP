---
name: save-as-flow
description: Save the most recent chat as a reusable personal Claude Code skill at ~/.claude/skills/<name>/SKILL.md.
arguments:
  - name: name
    type: string
    required: true
    description: The new skill's command name, in kebab-case (no leading slash, no spaces).
  - name: description
    type: string
    required: false
    description: One-line description of the new skill. Defaults to a short summary of the saved chat.
---

# Save As Flow

You are turning the conversation that just happened into a reusable personal Claude Code skill. The user did something useful in chat (probably driving Chrome via BrowserMCP tools), and now they want to save it as `/<name>` so they — or a teammate — can re-run it in one command later. Keep the user informed with short progress messages as you go; this is a meta-skill that writes another skill, so be explicit about what you're saving.

The output is a new file at `~/.claude/skills/<name>/SKILL.md` using the same YAML-frontmatter + markdown body format as `team-skills/powerbi-scan/SKILL.md`. After the file lands, `/<name>` will show up in the slash menu permanently.

## Inputs

- `name` — the new skill's command name, kebab-case, no leading slash, no spaces, ASCII only (e.g. `weekly-store-scan`, `jira-triage-mine`).
- `description` — optional one-line description. If omitted, summarize the chat in one sentence yourself.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="save-as-flow")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Even though this skill doesn't touch Chrome, it still calls Bash/Write through the MCP server's logging path, and we want accurate attribution in `/flows-list`. Do not narrate this step to the user.

### 1. Validate the name

Say something like: "Validating the skill name `<name>`..."

Check that `name`:
- matches `^[a-z0-9][a-z0-9-]*[a-z0-9]$` (kebab-case, starts/ends with alphanumeric, lowercase only)
- contains no slashes, spaces, dots, or non-ASCII characters
- is not a reserved word — Claude Code built-ins (`help`, `clear`, `exit`) or shipped team skill names (`save-as-flow`, `create-flow`, `record-flow`, `promote-flow`, `flows-list`, `powerbi-scan`, `confluence-search`, `jira-bulk-update`)

If validation fails, tell the user exactly what's wrong with the name and stop. Do not try to auto-fix it — let them re-run with a corrected name.

### 2. Check for an existing skill at that path

Resolve the target path: `~/.claude/skills/<name>/SKILL.md` (expand `~` to the user's home directory using Bash `echo $HOME` if needed).

If the directory already exists, ASK the user: "A skill named `/<name>` already exists at `~/.claude/skills/<name>/`. Overwrite it?" Wait for a clear yes/no. If they say no — or anything ambiguous — stop without writing.

If the directory does not exist yet, you'll create it in step 6.

### 3. Reflect on the recent conversation

Say: "Looking back at what we just did..."

Scan the prior chat turns and identify:

- **The user's original goal.** What did they ask for at the start? Capture that in one sentence — this becomes the opening paragraph of the new skill's body.
- **The sequence of MCP tool calls that worked.** Pull out every `mcp__browsermcp__*` call (or by the unprefixed names used in this repo: `chrome_attach`, `chrome_find_or_open_window`, `chrome_new_window`, `chrome_close_window`, `navigate`, `wait_for`, `scroll`, `click`, `type_text`, `read_page`, `screenshot`, `extract`) that returned `ok=True` or otherwise succeeded. Preserve their order.
- **What to skip.** Drop any tool call that errored, returned `ok=False` (e.g. write-intent without confirmation), or was an immediate retry of a previous call. Drop exploratory `read_page` calls that didn't inform the next step. Drop `extract` calls that came back with `confidence="low"` AND were re-run with a different schema right after — keep only the final successful one.

If you find fewer than 2 successful tool calls, REFUSE: tell the user "The recent chat has fewer than 2 successful tool calls — there's not enough here to be worth saving as a skill. Try again after a longer working session." and stop.

### 4. Scan for secrets and PII

Say: "Scanning the chat for anything sensitive..."

Walk the tool calls and their arguments. Refuse to save if any of the following patterns appear in the values being passed to tools:

- Field names or argument keys matching `/password|passwd|token|api[_-]?key|secret|bearer|auth|ssn|dob|pin|cookie|session/i`
- Values that look like credentials: long base64-ish strings, JWTs (`eyJ...`), bearer tokens, anything matching `^[A-Za-z0-9_-]{32,}$` in an obvious auth context
- US SSN pattern (`\d{3}-\d{2}-\d{4}`), full credit card numbers (16 digits, possibly hyphenated)

If you find any match, STOP and tell the user exactly what you found and where: "Found a potentially sensitive value in the chat — the `<argname>` argument to `<tool>` looks like `<masked preview>`. Refusing to save. Either redact that turn from your chat history first, or re-run the flow without entering that value, then call `/save-as-flow` again." Do not write the file.

### 5. Identify parameters worth extracting

Look at the literal values the user passed to tools and pick 1-3 that are obvious candidates for being a swappable parameter on future runs. Use these heuristics:

- **URLs** — any `https://...` value passed to `navigate()` or `chrome_find_or_open_window()`. Usually worth a parameter.
- **Search queries / report names** — string values passed to `type_text(field="search", text=...)` or `extract(prompt=..., includes <name>)`.
- **Identifiers** — store numbers, employee IDs, Jira keys (e.g. `ACIP-1234`), Confluence page IDs, dates (`2026-06-25`).
- **File paths** — local paths passed as outputs or inputs.

Skip values that are clearly structural (CSS selectors, `confirm_intent="write"`, `window_id`, schema dicts). The goal is to name the things a teammate might want to swap, not to over-parameterize.

For each candidate, choose a kebab-case argument name (e.g. `report`, `store-number`, `jira-key`) and a one-line description. If you can't find any obvious candidates, that's fine — the saved skill just has no `arguments` section.

### 6. Write the new SKILL.md

Say: "Writing `/<name>` to `~/.claude/skills/<name>/SKILL.md`..."

Resolve the absolute path by expanding `~` (use Bash `echo $HOME` to get the home directory if you don't already have it; do not assume `/Users/<x>`). Create the parent directory with `mkdir -p`. Then write the file. Prefer the `Write` tool with an absolute path; only fall back to `bash` + heredoc if `Write` is unavailable.

The file content must follow this exact structure. **Build it programmatically — do not copy the template literally including these notes.** Sections to assemble:

**Frontmatter** — between two `---` fences:
- `name:` ← the user-provided skill name from step 1
- `description:` ← user-provided description, or the one-sentence summary from step 3
- `arguments:` ← a YAML list with 1–3 entries, one per parameter extracted in step 4. **Omit the entire `arguments:` key if no parameters were extracted.** Each entry: `name`, `type` (string|integer|boolean), `required` (true|false), `description`.

**Body** — markdown, in this order:

```
# <Title Case of skill name>

<One paragraph restating the user's original goal in "you are doing X" voice, mirroring the powerbi-scan opener.>

## Inputs

- `<argname>` — <description>.
- <one bullet per argument>

## Flow

### 1. <step name>

Say something like: "<short progress message>"

Call `<tool_name>(<args>, window_id=<id>)`. <One sentence on what it does.>

### 2. <next step>

<one numbered step per successful tool call from the recorded sequence, in order>

### N. Respond to the user

<How to summarize the final result.>

## Guardrails

- Stay within the host allowlist enforced by `navigate()`.
- Never type credentials. SSO is the user's job.
- If a tool fails, surface the error and stop rather than thrashing.
- Use `{{argname}}` placeholders only inside prose; when calling tools, substitute literal values.

---
_Created by `/save-as-flow` on <YYYY-MM-DD>._
```

**Omit the `## Inputs` section entirely if there are no arguments.** The number of numbered Flow steps depends on how many tool calls were in the recorded sequence — don't pad or trim arbitrarily.

The final file must NOT contain any of the angle-bracket placeholders or square-bracket commentary from this template — those are *instructions to you*, not literal text to write. Substitute every `<placeholder>` with the concrete value before calling Write.

A few rules when generating the body:

- Use `{{argname}}` placeholders only inside the prose descriptions and tool-call examples where the value should be swapped per-invocation. The first step should always be `chrome_attach()` if the saved chat touched Chrome at all, and the second step should be `chrome_find_or_open_window(url_pattern=...)` so `window_id` threads through everything after.
- Thread `window_id=<id>` through every Chrome-touching step, exactly like `powerbi-scan` does.
- If the saved chat used `click()` or `type_text()` with `confirm_intent="write"` or `"destructive"`, preserve that — keep the two-phase confirm pattern in the generated skill, don't paper over it.
- Keep each step short. One paragraph, maybe a small bullet list of sub-calls. Don't invent extra steps that weren't in the original chat.

### 7. Verify and confirm to the user

After the file is written, run `ls ~/.claude/skills/<name>/SKILL.md` to confirm it landed, and `head -20 ~/.claude/skills/<name>/SKILL.md` to verify the frontmatter is valid YAML (name and description present, arguments well-formed).

Then reply to the user with exactly this shape:

> Saved `/<name>` to `~/.claude/skills/<name>/SKILL.md` with parameters: `<comma-separated argnames, or "(no arguments)">`. Try `/<name> --help` to see how to invoke.

If the verification step shows any anomaly (file missing, frontmatter malformed), tell the user what's wrong and offer to retry.

## Guardrails

- **Never overwrite** `~/.claude/skills/<name>/` without explicit user confirmation in step 2. A silent overwrite would destroy a teammate's earlier work.
- **Never save chats containing credentials, tokens, or PII.** Step 4 is non-negotiable — if you find a match, refuse and surface the offending value (masked) to the user. Do not write a partial or "cleaned" version.
- **Don't save thin chats.** Fewer than 2 successful tool calls is not enough signal to extract a reusable flow; refuse in step 3.
- **Don't auto-fix invalid names.** If the user passes a bad name (uppercase, spaces, leading slash), tell them and stop — let them re-run with the corrected value.
- **This skill writes outside the repo.** `~/.claude/skills/` is a per-user, per-machine directory — never write to `team-skills/` from `/save-as-flow`. Team skills go through code review; personal skills don't.
- **No network calls.** This skill is pure local file I/O against `~/.claude/skills/`. Do not navigate, do not fetch, do not screenshot. The only Bash you need is `echo $HOME`, `mkdir -p`, `ls`, and `head`.

---
name: promote-flow
description: Promote a personal Claude Code skill from ~/.claude/skills/<name>/ to the team-shared BrowserMCP repo via a GitHub pull request.
arguments:
  - name: name
    type: string
    required: true
    description: The personal skill name to promote (e.g. "stale-tickets"). Must already exist at ~/.claude/skills/<name>/SKILL.md.
  - name: reason
    type: string
    required: false
    description: One-line reason for the team to merge this skill; surfaces in the PR body to help reviewers decide.
---

# Promote Flow

You are promoting a personal Claude Code skill from a teammate's `~/.claude/skills/<name>/` directory into the shared BrowserMCP repo at `team-skills/<name>/`, then opening a GitHub pull request against `github.com/isunilsharma/BrowserMCP` so the team can review it. Once reviewers approve and merge, the skill ships in the next plugin version and every teammate picks it up on their next plugin update — that's the whole point of this meta-skill. Keep the user informed at each step; this skill writes a branch, a commit, and a PR on their behalf, so they need to feel in control of every transition.

## Inputs

- `name` — the kebab-case name of the personal skill to promote, matching the directory `~/.claude/skills/<name>/`.
- `reason` — optional one-line justification for the team. If provided, it lands in the PR body to give reviewers context.

## Flow

### 1. Set skill context

Call `set_skill_context(skill="promote-flow")` so this run is attributed correctly in `/flows-list` and the audit log shows which Claude Code skill triggered the underlying MCP tool calls.

### 2. Validate the input skill exists

Say something like: "Looking for `~/.claude/skills/{{name}}/SKILL.md`..."

Expand `~` via Bash `echo $HOME` if needed, then check that `$HOME/.claude/skills/{{name}}/SKILL.md` exists. If it does not, STOP and tell the user: "No personal skill found at `~/.claude/skills/{{name}}/SKILL.md`. Save it first with `/save-as-flow {{name}}` and try again." Do not proceed.

Read the file and extract its frontmatter `description:` value — you will need it for the PR body and for the user-facing diff plan in step 4. If the frontmatter is malformed (no `description:` line, or `description:` is empty), STOP and ask the user to fix the personal skill's frontmatter first.

### 3. Lint the skill (BEFORE any git work)

Say: "Linting `{{name}}` before promoting..."

Three checks, in order. Any failure means STOP — do not create a branch, do not write anything, surface the issue and exit.

**3a. Name-collision check.** List `${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP}/team-skills/` and refuse if a directory named `{{name}}` already exists. Tell the user: "A team skill named `{{name}}` already exists. Rename your personal skill first (`mv ~/.claude/skills/{{name}} ~/.claude/skills/<new-name>` and update its frontmatter `name:`), then re-run `/promote-flow <new-name>`."

**3b. Secret / PII scan.** Read the full body of `~/.claude/skills/{{name}}/SKILL.md` and walk it line-by-line against the same regex set documented in `/save-as-flow`'s secret scanner (step 4 there). Refuse if any of the following match:

- Field names or argument keys matching `/password|passwd|token|api[_-]?key|secret|bearer|auth|ssn|dob|pin|cookie|session/i` paired with a literal value
- Values that look like credentials: long base64-ish strings, JWTs starting with `eyJ`, bearer tokens, anything matching `^[A-Za-z0-9_-]{32,}$` in an obvious auth context
- US SSN pattern (`\d{3}-\d{2}-\d{4}`), full credit card numbers (16 digits, possibly hyphenated)
- Internal URLs containing auth query params (anything matching `\?.*\b(token|auth|key|sig|sas)=`)
- Employee email addresses (`@internal\.com` or `@example.net`) hardcoded into the skill body
- Any other obvious PII (full names paired with employee IDs, store numbers paired with manager names, etc.)

If anything matches, surface the (masked) match to the user — show the field name and the first 4 + last 4 characters of the value with the middle replaced by `...` — and refuse with: "Found a potentially sensitive value in `{{name}}`'s body: `<masked>`. Refusing to promote. Edit `~/.claude/skills/{{name}}/SKILL.md` to remove the hardcoded value (parameterize it as an argument instead), then re-run."

**3c. Destructive-action check.** Grep the skill body for any `click(` or `type_text(` call that includes `confirm_intent="write"` or `confirm_intent="destructive"`. For every such call, verify the skill body contains an explicit user-confirmation step earlier in the same numbered step or in an immediately preceding step (a sentence like "Ask the user to confirm" or "Wait for explicit yes/no"). If a destructive call has no matching confirmation prose, refuse with: "`{{name}}` contains a destructive MCP call (`<tool>` with `confirm_intent=<intent>`) but no explicit user-confirmation step in the body. Add a confirmation step in the SKILL.md before re-running `/promote-flow`."

### 4. Show the diff plan and wait for explicit confirmation

Tell the user, verbatim shape:

> Promoting `/{{name}}`: will copy `~/.claude/skills/{{name}}/SKILL.md` to `team-skills/{{name}}/SKILL.md` and open a PR against `github.com/isunilsharma/BrowserMCP`.
> Description: `<the description you extracted in step 2>`.
> OK to proceed?

Wait for an explicit `yes` / `y` / `proceed`. STOP on `no`, on silence, or on anything ambiguous (`maybe`, `not sure`, a follow-up question). Do not interpret silence as consent.

### 5. Create branch, commit, push

Say: "Creating the promotion branch and pushing..."

Run the following Bash commands in order. If any step fails (non-zero exit), STOP and surface the error to the user — do not try to continue past a failure.

1. **Verify clean working tree:**
   ```bash
   cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git status --porcelain
   ```
   If output is non-empty, refuse with: "Your BrowserMCP working tree has uncommitted changes. Commit or stash them first (`git stash` or `git commit`), then re-run `/promote-flow {{name}}`. I won't operate on a dirty tree — that's a foot-gun."

2. **Create the branch:**
   ```bash
   BRANCH="promote/{{name}}-$(date +%Y%m%d-%H%M%S)" && cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git checkout -b "$BRANCH"
   ```
   Capture `$BRANCH` for later steps.

3. **Copy the skill file:**
   ```bash
   cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && mkdir -p team-skills/{{name}} && cp "$HOME/.claude/skills/{{name}}/SKILL.md" "team-skills/{{name}}/SKILL.md"
   ```

4. **Stage the new file:**
   ```bash
   cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git add team-skills/{{name}}/SKILL.md
   ```

5. **Commit with the user's git identity** (use the per-command `-c` overrides so we do not touch `git config --global`):
   ```bash
   AUTHOR_EMAIL=$(git config --global user.email) && AUTHOR_NAME=$(git config --global user.name || echo "$AUTHOR_EMAIL") && cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git -c user.email="$AUTHOR_EMAIL" -c user.name="$AUTHOR_NAME" commit -m "Promote /{{name}} from personal skill" -m "{{reason}}"
   ```
   Omit the second `-m "{{reason}}"` if no `reason` argument was supplied.

6. **Push to origin:**
   ```bash
   cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git push origin "HEAD:refs/heads/$BRANCH"
   ```

### 6. Open the PR

Say: "Opening the pull request..."

First detect whether `gh` is installed:
```bash
which gh
```

**If `gh` is available**, open the PR with `gh pr create`, base `master`, head `$BRANCH`, repo `isunilsharma/BrowserMCP`. The PR body MUST include, in order:

- A first-line summary: `Promotes /{{name}} from a personal skill to team-skills/.`
- **Description:** the description string you extracted from the personal skill's frontmatter in step 2.
- **Author:** `<the email from $AUTHOR_EMAIL>`.
- **Reason:** the `reason` argument if provided; omit this section entirely otherwise.
- **Source path:** `~/.claude/skills/{{name}}/` — so reviewers know where the file came from on the author's machine.
- **Reviewer checklist**, copied from `docs/security.md` §6:
  - [ ] PII check — no hardcoded credentials, tokens, employee emails, or PII in the skill body
  - [ ] Destructive-action check — every `confirm_intent="write"` or `"destructive"` MCP call has an explicit user-confirmation step in the body
  - [ ] Naming check — kebab-case, no collision with existing team skills, no reserved words
  - [ ] Test confirmation — the author has run the skill end-to-end on their machine and it works

Pass the body via a HEREDOC so the formatting survives. Example shape:
```bash
gh pr create \
  --base master \
  --head "$BRANCH" \
  --repo isunilsharma/BrowserMCP \
  --title "Promote /{{name}} from personal skill" \
  --body "$(cat <<'EOF'
Promotes /{{name}} from a personal skill to team-skills/.

**Description:** <desc>

**Author:** <email>

**Reason:** <reason if provided>

**Source path:** ~/.claude/skills/{{name}}/

## Reviewer checklist (docs/security.md §6)
- [ ] PII check — no hardcoded credentials, tokens, employee emails, or PII in the skill body
- [ ] Destructive-action check — every confirm_intent="write" or "destructive" MCP call has an explicit user-confirmation step in the body
- [ ] Naming check — kebab-case, no collision with existing team skills, no reserved words
- [ ] Test confirmation — the author has run the skill end-to-end on their machine and it works
EOF
)"
```

Capture the PR URL from `gh`'s stdout for step 8.

**If `gh` is NOT available**, surface the branch URL and instruct the user to open the PR via the web UI:
> `gh` isn't installed. Your branch is pushed to `https://github.com/isunilsharma/BrowserMCP/tree/<BRANCH>`. Open the PR manually at `https://github.com/isunilsharma/BrowserMCP/compare/master...<BRANCH>` and paste the description/reason/checklist above into the PR body.

Then skip to step 7 with no PR URL — step 8's "Report back" message should say "Branch pushed, please open the PR manually" instead.

### 7. Switch back to master

Say: "Switching back to master so your tree is clean..."

```bash
cd ${BROWSERMCP_REPO:-$HOME/Documents/code/BrowserMCP} && git checkout master
```

Then verify with `git status --porcelain` — output must be empty. Tell the user: "Returned to master. Your working tree is clean. The `<BRANCH>` branch is on origin awaiting review."

### 8. Report back

Reply to the user with exactly this shape (substituting the PR URL captured in step 6):

> PR opened: `<url>`. Once reviewed and merged, the skill ships in the next plugin version — teammates pick it up on `claude plugin update browsermcp` (or rerunning team-onboarding `install.sh`).

If `gh` was not available and you fell through to the manual path in step 6, adjust the first sentence to: "Branch pushed to `<branch-url>` — please open the PR manually using the body in step 6." The second sentence about plugin updates still applies once the PR lands.

## Guardrails

- **Never push to `master` or `main`.** Only push to `promote/*` branches created in step 5. The push command must always target `HEAD:refs/heads/$BRANCH`, never `master`.
- **Never auto-merge.** Humans review promoted skills — `gh pr merge` is not called by this skill, ever.
- **If lint fails (step 3), do NOT create the branch.** Surface the issue and stop. Branches are only created after all three lint checks pass and the user explicitly confirms in step 4.
- **Network access only via `git` and `gh` against `github.com`.** No `navigate()`, no `chrome_attach()`, no web fetches. This is a pure git-and-GitHub flow.
- **Refuse to operate on a dirty working tree** (step 5.1). The user must commit or stash their in-progress changes first. Silently stashing on their behalf would lose work.
- **Never touch `git config --global`.** Pass the author identity through per-command `-c user.email=... -c user.name=...` overrides in step 5.5 only.
- **Never skip the explicit confirmation in step 4.** Silence is not consent. If the user response is ambiguous, treat it as "no" and stop.
- **Never write to `~/.claude/skills/`.** This skill only *reads* from the user's personal skill directory and *writes* into the repo's `team-skills/`. The personal skill stays untouched on disk after promotion.

---
_Part of the BrowserMCP Phase 3 meta-skill set. See `docs/roadmap.md` Phase 3 for the promotion workflow rationale._

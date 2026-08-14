# Security

> Threat model, mitigations, and an IT/Security review checklist.

This document is what you'd hand to InfoSec when asking for permission to roll BrowserMCP out beyond a small pilot. It's also the contract the project commits to upholding.

## 1. Security posture summary (TL;DR)

| Property | Status |
|---|---|
| Where does code execute? | **100% on the user's own machine.** No central server. |
| Where are credentials stored? | **Only in the user's existing Chrome profile.** BrowserMCP never sees or stores credentials. |
| Where do logs go? | **Local only** (`~/.browsermcp/runs/`) in v1. No central log aggregation. |
| Can a remote attacker drive my Chrome? | **No.** CDP is bound to `127.0.0.1` only. |
| Can a malicious skill exfiltrate data? | **Constrained.** Skills run via Claude Code; can be reviewed pre-merge. See §6. |
| What new credentials does the user need? | **None.** Uses existing Claude Code + existing Chrome SSO session. |
| Is the user's main Chrome compromised? | **No.** Default mode opens a new window; main browsing untouched. |

## 2. Trust model

Three trust principals:

| Principal | Trusted to do |
|---|---|
| **The user** | Anything they could do manually in their own browser |
| **Team-shipped skills** | Same as the user — they're code-reviewed before merge |
| **Personal skills** | Whatever the user writes for themselves; same authority as ad-hoc chat |
| **Random downloaded skill / 3rd-party code** | Nothing. Not supported in v1. |

**Critical principle:** BrowserMCP grants no power the user doesn't already have. It just makes existing user authority easier to wield.

## 3. Threat model

### T1: Local malware reads from BrowserMCP

**Scenario:** Malware running as the same user as Claude Code connects to CDP port 9222 and drives the user's Chrome.

**Likelihood:** Low — requires existing code execution as the user.
**Impact:** High — could exfiltrate session cookies for any logged-in site.
**Mitigations:**
- `--remote-debugging-address=127.0.0.1` (no external network exposure)
- Document the residual risk in this section
- (Future) Optional `--remote-debugging-pipe` mode that uses a Unix socket instead of TCP

**Residual risk:** Same risk profile as Chrome with DevTools open — already accepted by enterprise IT for users with DevTools privileges.

### T2: Skill executes destructive actions without consent

**Scenario:** A buggy or malicious skill clicks "Approve" / "Delete" / "Submit" on a sensitive page.

**Likelihood:** Medium — easy to misconfigure.
**Impact:** Medium-High — depends on what was clicked.
**Mitigations:**
- All `team-skills/*` with `risk: write` must include an explicit confirmation step in the SKILL.md
- The MCP `click` primitive accepts a `confirm_intent` arg; skills that perform writes set this and the user must approve
- PR review for team skills requires a checklist (see §10) flagging any write operations
- Run logs capture exact actions for post-hoc audit

### T3: Skill exfiltrates internal data

**Scenario:** A promoted skill reads sensitive internal data (e.g., from Power BI) and POSTs it to an external server.

**Likelihood:** Low — requires malicious or compromised contributor with PR-merge rights.
**Impact:** High — could leak corporate data.
**Mitigations:**
- Promoted skills run as plain Claude Code prompts that invoke MCP tools — there is no Python execution from a skill
- The MCP server's `navigate()` and `fetch()` tools restrict allowed hosts to:
  - corporate internal domains (`.example.com`)
  - Public domains explicitly listed in `~/.browsermcp/allowed_hosts.toml`
  - (No wildcard "anywhere" by default in production mode)
- Network egress from a skill goes only through these primitives
- PR review checklist (§10) explicitly checks for "data leaving the company"

### T4: PII in logs

**Scenario:** Logs capture page content containing employee or customer PII.

**Likelihood:** High — pages will often contain PII.
**Impact:** Medium — logs are local, but local drives get exfiltrated in incidents.
**Mitigations:**
- `browsermcp/redact.py` runs over every log line before write
- Redactor masks: emails, phones, SSNs, credit cards, anything in fields labeled `password|secret|token|ssn|dob`
- 100% unit test coverage on the redactor
- Logs are time-bound: `~/.browsermcp/runs/` auto-deletes entries older than 30 days
- No log shipping to a central server in v1

### T5: Compromised user account

**Scenario:** A user's corporate account is compromised. The attacker installs BrowserMCP to automate damage.

**Likelihood:** Equal to base account-compromise rate.
**Impact:** Identical to compromise without BrowserMCP — attacker can only do what the user could do anyway.
**Mitigations:**
- Out of scope: BrowserMCP doesn't change the attack surface here. Account security is upstream (Entra ID, MFA, Conditional Access).

### T6: Supply-chain attack via browser-use

**Scenario:** A malicious version of the `browser-use` PyPI package is pushed.

**Likelihood:** Low.
**Impact:** High — could backdoor every install.
**Mitigations:**
- Pin `browser-use` to a specific version + hash in `pyproject.toml`
- Mirror dependencies through an internal Artifactory mirror for production installs
- Dependabot alerts on the BrowserMCP repo
- Periodic `pip-audit` / `pip-licenses` runs in CI

### T7: Skill loops / runaway costs

**Scenario:** A buggy skill loops infinitely, burning the user's Claude Code subscription tokens.

**Likelihood:** Medium — easy to mis-prompt.
**Impact:** Low (user's own subscription) but annoying.
**Mitigations:**
- MCP server enforces a per-flow tool-call cap (default 50; configurable)
- After cap, returns an error to Claude Code: "Skill exceeded its call budget"
- Skill files can declare a `max_steps:` in frontmatter
- Run-time telemetry surfaces costly flows in `/flows-list`

### T8: Phishing via skill description

**Scenario:** A bad skill description tricks users into running something harmful (e.g., "Cleanup old tickets" but actually deletes 1000 tickets).

**Likelihood:** Low.
**Impact:** Medium.
**Mitigations:**
- Pre-run summary always shows the *action plan* before destructive actions
- Confirmation prompts list specific items (e.g., "About to delete: ACIP-1234, ACIP-1235, ...")
- PR review of team skills

### T9: Misattribution / spoofing of `skill` in run logs

**Scenario:** `set_skill_context(skill="...")` writes a process-global module variable that's used as the `skill` field in `~/.browsermcp/runs/r-*.jsonl`. Two failure modes:

1. **Spoofing.** Any caller — including an ad-hoc Claude Code chat — can call `set_skill_context(skill="powerbi-scan")` before doing something unrelated; subsequent tool calls log as `powerbi-scan` until the value is overwritten.
2. **Persistence (stale value).** Because the context is never auto-reset between MCP requests, an ad-hoc chat following a real skill run inherits the previous skill's attribution. Tools fire under the wrong `skill` label.

**Likelihood:** High (the persistence case happens by default in any mixed session).
**Impact:** Low — the `skill` field is an operational convenience for the `/flows-list` dashboard, not a security boundary. The actual tool name + args + result + timestamp remain accurate.
**Mitigations:**
- Documented as accepted risk: the `skill` field is **self-asserted by the caller** and should not be relied upon for security audit. Operational tooling (`/flows-list`) is the only consumer.
- All other audit fields (tool name, args, result_summary, run_id, timestamp) are written by the wrapper itself and are not user-controllable.
- (Future) When Claude Code natively passes skill context in MCP tool calls, we can swap to a wrapper-set value instead of a self-asserted one; that change would eliminate both failure modes.

**Residual risk:** Operators reading run logs must understand that `skill` is descriptive, not authoritative.

## 3a. Power BI drill-down tools (read-only)

Two Power-BI-specific helpers — `powerbi_discover_fields` and `powerbi_set_filter` (see `docs/techflow.md §5`) — let a skill filter a report the user has open. Because `powerbi_discover_fields` inspects the report's own network traffic, it warrants a note against the trust model above.

- **In-memory only, to recover field names.** `powerbi_discover_fields` reloads the report and reads the report's *own* outbound semantic-query request bodies **in memory**, solely to recover the model's `Entity/Property` field references (i.e. column names). Those bodies are parsed, the field map is returned, and the raw bodies are discarded. Nothing is persisted and nothing leaves the machine.
- **No credentials or row data captured.** The capture is scoped to query-shape bodies; it does not read, capture, or log cookies, tokens, auth headers, or row-level result data. As with every tool, run logs record only the tool name, args, and a result summary through the PII redactor (§4, T4) — never the captured bodies.
- **`powerbi_set_filter` only navigates.** It builds a `?filter=Entity/Property eq 'value'` URL and navigates to it. The target is checked against the same host allow-list as `navigate()` (§5), so it can only reach Power BI hosts already permitted. It changes **what data is displayed**, and does not write to, update, or delete anything in any system.
- **Read-only / reporting, not destructive.** Both tools are observe-only in the sense of §6's `risk: read` — no confirmation gate is required because neither performs a write or destructive action. They grant no power beyond what the user could do by pasting a filter URL into their own browser (§12).

## 4. Data flow & where data lives

```
Page content   →   read by MCP server   →   passed to Claude Code (Anthropic API)
                                              │
                                              └──→  not retained by BrowserMCP
                                                    Anthropic's standard retention/policy applies
                                                    (per the user's Claude Code subscription)

Logs           →   ~/.browsermcp/runs/<id>.jsonl (local, PII-redacted, 30-day expiry)

Screenshots    →   ~/.browsermcp/screenshots/ (local, 30-day expiry, manual delete OK)

Cookies/auth   →   Chrome's own profile storage — BrowserMCP never reads or writes these
                   directly. Attach is read-only with respect to credentials.

Skill files    →   ~/.claude/skills/ (personal) or installed plugin folder (team)
```

**Nothing leaves the user's machine** except:
1. Page content passed to Claude Code (the LLM brain) via the user's existing subscription
2. Outbound HTTP requests the user's Chrome makes anyway as part of normal browsing

There is no BrowserMCP central service. There is no telemetry pingback.

### Telemetry (Phase 5+)

Disabled by default. When opted in via `config.telemetry_opt_in`, events are written **LOCALLY ONLY** to `~/.browsermcp/telemetry.jsonl` with PII redacted (via the same `browsermcp/redact.py` that scrubs run logs). The v0 sink in `browsermcp/telemetry.py` is a no-op with respect to the network — nothing leaves the user's machine.

A real telemetry backend requires separate IT/InfoSec review before activation. The `telemetry_endpoint` setting exists as a stub for that future state, but the v0 emit path ignores it.

## 5. Network controls

### Outbound from BrowserMCP server
- The MCP server itself makes **no outbound network calls**. All browsing happens via the user's Chrome.

### Outbound from Chrome (driven by the agent)
- The `navigate()` primitive enforces an allowed-hosts policy:
  - Default allowlist: `*.example.com`, `*.example.org`, `*.example.org`
  - Plus any host explicitly added to `~/.browsermcp/allowed_hosts.toml`
- For external sites (e.g., competitor pricing) users must add domains explicitly; we surface "this is unusual" warnings on first add

### Inbound to BrowserMCP server
- The MCP server listens on **stdio only** (default) or a Unix socket — never a TCP port
- No HTTP server, no port to scan

### Inbound to CDP
- Chrome's remote-debugging port (9222) is bound to `127.0.0.1` only
- We do NOT set `--remote-debugging-address=0.0.0.0` under any circumstance
- A startup check verifies the binding and fails loudly if misconfigured

## 6. Skill review checklist (used in PR review)

Before merging a team skill PR, the reviewer ticks each:

```
[ ] SKILL.md frontmatter is valid and complete
[ ] `risk:` field declared (read | write | destructive)
[ ] If risk=write or destructive, confirmation step is present in the body
[ ] No hardcoded credentials, tokens, URLs with auth info, or PII
[ ] No instructions to navigate to non-corporate domains (unless declared in description + justified)
[ ] No instructions to POST data to external endpoints
[ ] No `system` / `shell` / `exec` patterns (skills shouldn't execute arbitrary code)
[ ] Required args are explicit; defaults are safe
[ ] Skill can be cancelled mid-run cleanly
[ ] Tested locally by the reviewer at least once
[ ] If destructive, has dry-run / preview mode by default
[ ] The skill's frontmatter `name:` field matches the directory name (team-skills/<name>/SKILL.md has frontmatter name=<name>)
[ ] The skill body's first action is set_skill_context(skill="<name>") so /flows-list attributes the run
[ ] If the skill makes write/destructive MCP calls, the body has a documented dry-run-default plus explicit user-confirmation step BEFORE the write fires
[ ] If the skill needs external hosts, they're either in the default allowed_hosts list in browsermcp/config.py OR documented as user-config additions in the skill's "Setup" section
[ ] Reviewer ran the skill locally at least once against the actual target site before approving — note the run_id in the PR comment
[ ] If skill is marked `interactive: false`, all its tool calls must work without any user prompts mid-flow (no confirmation gates that block on user input)
```

## 7. Audit logging

Each run produces a JSONL file with:

```jsonl
{"t":"2026-06-24T11:55:32Z","run_id":"r-abc","skill":"powerbi-scan","user":"<hash>","host":"<hostname>"}
{"t":"...","tool":"chrome_attach","args":{},"result":"ok","duration_ms":120}
{"t":"...","tool":"navigate","args":{"url":"https://powerbi.example.com"},"result":"ok","duration_ms":1840}
...
{"t":"...","run_id":"r-abc","status":"completed","duration_s":47}
```

User identity is hashed in logs (not stored as email). Hostname is captured for incident response.

Logs are local. If/when (Phase 3) we add central log shipping, it'll require an explicit security review and user opt-in.

## 8. Authentication & authorization

### User auth
BrowserMCP itself has **no authentication**. It runs as the user, with the user's privileges. The "auth" comes for free from:
- The user being signed into their macOS/Windows account
- The user's Chrome being signed into their corporate SSO session
- The user being signed into Claude Code

If you can read this paragraph in the user's session, you have all the auth you need.

### Skill authorization
Personal skills: any skill the user writes runs with the user's authority.
Team skills: require a PR merge, gated by `team-skill-reviewers` group on the repo. Membership is granted by the project owner via a documented process.

## 9. Incident response

If a security incident is suspected (e.g., a malicious skill landed):

1. **Stop:** A maintainer cuts a new plugin release that removes the suspect skill.
2. **Notify:** All teammates receive an update message via `claude plugin update browsermcp` — the update notes flag the issue.
3. **Investigate:** Pull run logs from affected users (with their permission); identify scope.
4. **Remediate:** Identify root cause; tighten review checklist if a process failure; add a regression test.
5. **Disclose:** Internal write-up shared with InfoSec.

## 10. IT / InfoSec review checklist

For the conversation with InfoSec:

```
ARCHITECTURE
[ ] Reviewed docs/design.md — understand the 3-component architecture
[ ] Confirmed: no central server, no off-machine credential storage
[ ] Confirmed: Chrome attach uses --remote-debugging-address=127.0.0.1 only

DATA HANDLING
[ ] Reviewed §4 (Data flow & where data lives)
[ ] Confirmed: page content goes only to Anthropic (covered by user's existing Claude Code subscription contract)
[ ] Confirmed: logs are local-only with PII redaction
[ ] Acceptable retention: 30 days local

CHANGE CONTROL
[ ] Reviewed §6 (Skill review checklist)
[ ] Reviewed §8 (Authentication & authorization)
[ ] team-skill-reviewers group membership process is documented

CREDENTIALS & ACCESS
[ ] Confirmed: BrowserMCP does not store or transmit credentials
[ ] Confirmed: agent can do nothing the user couldn't do manually
[ ] Confirmed: MFA / Conditional Access continue to apply (we don't bypass)

NETWORK
[ ] Reviewed §5 (Network controls)
[ ] Confirmed: outbound domain allowlist (default: *.example.com)
[ ] Confirmed: no inbound TCP port

SUPPLY CHAIN
[ ] browser-use pinned to specific version + hash
[ ] Dependencies mirrored through Artifactory for production
[ ] Dependabot enabled on the GitHub repo

INCIDENT RESPONSE
[ ] Reviewed §9 (Incident response)
[ ] Maintainer can cut emergency release within 24h
[ ] Logs sufficient for post-incident analysis

ACCEPTABLE USE
[ ] User-facing acceptable-use note is shipped with the plugin
[ ] Manager-level approval flow for write-capable skills is documented
```

## 11. Known unknowns / open security questions

Things to resolve before broad rollout:

- **Q1.** Does corporate Conditional Access policy flag CDP-attached browsers as "anomalous"? Need to test against a real-account-protected app.
- **Q2.** Does Crowdstrike / Defender / corporate EDR quarantine BrowserMCP's Chrome shim?
- **Q3.** Power BI licensing — does our pattern count as "automated access" requiring a different SKU? (Probably no, since the user is in the loop, but check.)
- **Q4.** For Phase 3 (scheduled/unattended runs), we'll need either a service account or a permitted persistent profile — which is acceptable to InfoSec?

These are flagged in `docs/roadmap.md` as gating items for the appropriate phase.

## 12. Final design statement

BrowserMCP is engineered so that, in the worst case, **a teammate using it can only cause harm that they could already cause manually with their own Chrome.** Everything in this document is in service of upholding that invariant.

Where it adds risk, the risk is bounded (logs, allowlists, confirmations, review). Where it might bypass controls, it doesn't (SSO + MFA + Conditional Access all still apply — we attach to an authenticated session, we don't authenticate ourselves).

For Phase 1 (small pilot, attended use only), this posture is sufficient. For Phase 3 (broad rollout, scheduled runs), additional controls will be added before that phase opens — see roadmap.

---

## 13. Skill governance

> Full governance rules for ownership, promotion, deprecation, and conflict resolution. Companion to §6 (review checklist) and §8 (authorization).

### Skill ownership

Every skill in `team-skills/` has a designated **maintainer** recorded in `team-skills/REGISTRY.md`. The maintainer triages issues, approves PRs touching the skill, and makes deprecation calls. Maintainer changes require a PR signed off by both the outgoing and incoming maintainer. If the current maintainer leaves and no one volunteers within 30 days, the skill is auto-deprecated.

### Promotion checklist (from §6, repeated for convenience)

PR must include:
- ✅ Valid frontmatter (`name`, `description`, `risk`, `arguments` if any)
- ✅ `set_skill_context(skill="<name>")` as step 0 in the body
- ✅ Write/destructive skills: dry-run default + explicit user-confirmation step
- ✅ No hardcoded credentials, tokens, or PII
- ✅ Reviewer ran it locally and noted the `run_id` in the PR comment
- ✅ `REGISTRY.md` row added (name, risk, team, maintainer)

Skills promoted into `team-skills/all/` (universal) require **two approvals**: one from the originating team, one from a `team-skill-reviewers` member outside that team.

### Deprecation (30-day warning)

Add to the skill's frontmatter:

```yaml
deprecated: true
deprecation_date: YYYY-MM-DD   # 30 days from merge
replacement: /new-skill-name   # strongly recommended
```

`/flows-list` surfaces deprecated skills with a warning. Remove the skill directory on or after `deprecation_date`. Earlier removal is allowed only for active security incidents (use the incident response process in §9).

### Name conflicts

If two teams want the same skill name with different behavior:
1. Neither gets the bare name.
2. Each uses a team suffix: `inventory-snapshot-produce`, `inventory-snapshot-hr`.
3. If a universal version later subsumes both, the suffixed variants are deprecated pointing at the universal one.

### What governance does NOT cover

- Personal skills (`~/.claude/skills/`) — the user's own business until promoted.
- Runtime enforcement — that's the MCP server's job (host allowlist, dry-run gates, logging).

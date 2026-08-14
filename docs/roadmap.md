# Roadmap

> Phased delivery plan from PoC to broad rollout.

## Guiding principles

1. **Prove value, then invest.** Don't build phase N+1 capabilities until phase N is in real use.
2. **Each phase has a clear "earned right to continue" criterion.** No phase ships unless the previous one delivered.
3. **Security/IT review happens at phase boundaries, not at the end.**
4. **Default to "fewer, better-known users."** Quality of feedback > quantity of users in early phases.

---

## Phase 0 — Design & docs

**Goal:** lock the design before writing code.

**Status:** ✅ Complete.

**Deliverables:**
- ✅ README.md
- ✅ CLAUDE.md (project guidance for Claude Code)
- ✅ docs/design.md
- ✅ docs/userflow.md
- ✅ docs/techflow.md
- ✅ docs/testing.md
- ✅ docs/security.md
- ✅ docs/roadmap.md (this file)

**Exit criteria:**
- All 7 documents reviewed by at least one other engineer
- Decisions in §10 of `design.md` confirmed or revised
- Open questions (`design.md` §11) have at least a stub answer

---

## Phase 1 — Solo PoC (1–2 weeks)

**Goal:** Sunil can run `/powerbi-scan` against a real Power BI report from his own Claude Code.

**Status:** ✅ Complete (scaffold through the `chrome_find_or_open_window` follow-up).

**Scope:**
- MCP server skeleton in `browsermcp/server.py`
- Primitives: `chrome_attach`, `chrome_new_window`, `navigate`, `click`, `type`, `read_page`, `extract` (fast path only), `screenshot`
- One team skill: `/powerbi-scan` with `report` arg
- Chrome shim that adds `--remote-debugging-port=9222`
- Basic logging to `~/.browsermcp/runs/`
- Local install via `claude plugin install <local-path>` (no GitHub yet)

**Out of scope:**
- Save / promote flow meta-skills
- `/confluence-search`, `/jira-bulk-update`
- Tests beyond the bare minimum
- Multi-user support
- IT review

**Exit criteria:**
- `/powerbi-scan` produces correct KPIs on ≥5 different reports
- No regressions when run repeatedly across a day (session refresh works)
- Code lint clean, basic unit tests for `redact.py` and `tools/navigation.py`
- Demo recording shared with potential pilot users

**Resourcing:** Sunil solo. ~10 working days.

---

## Phase 2 — Pilot with 2–3 willing teammates (2–4 weeks)

**Goal:** prove the multi-user pattern; gather real flow ideas.

**Status:** ✅ Complete (as of 2026-06-25).

**Scope:**
- Repo pushed to `github.com/isunilsharma/BrowserMCP`
- Plugin installable via `claude plugin install <internal-gh-url>`
- Add team skills: `/confluence-search`, `/jira-bulk-update` (with confirmation step)
- Meta-skills: `/save-as-flow`, `/flows-list`
- Integration tests against the fixture site
- README + getting-started doc for pilot teammates

**Delivered:**
- 4 team skills: `powerbi-scan`, `confluence-search`, `jira-bulk-update`, `flows-list`
- 2 meta-skills: `save-as-flow`, `promote-flow` (NOTE: `promote-flow` technically shipped in Phase 3)
- Integration tests + Flask fixture site at `tests/fixtures/site/`
- `docs/getting-started.md` for pilot teammates
- `team-onboarding/` folder with `install.sh`

**Out of scope:**
- `/promote-flow` (defer to Phase 3)
- Scheduled/unattended runs
- Formal InfoSec review (we'll get an informal nod from the team's TL)

**Exit criteria:**
- 2–3 pilot users have it installed
- Each pilot user has run ≥10 flows over the period
- Pilot users have saved ≥1 personal skill each via `/save-as-flow`
- A backlog of 5+ requested team skills exists, captured in GH Issues
- No security incidents or "the bot did something I didn't expect" events

**Resourcing:** Sunil + 2–3 willing pilot users. ~3 weeks elapsed.

**Gating:** This phase happens on opt-in only. We do NOT broadcast wider until Phase 3.

---

## Phase 3 — Team rollout + formal review (1–2 months)

**Goal:** make BrowserMCP usable by the whole immediate team (~20 people).

**Status:** 🟡 In progress (code complete; InfoSec review pending).

**Scope:**
- ✅ `/promote-flow` meta-skill (this commit)
- ✅ Skill review process documented (`docs/security.md` §6 extended)
- ⏳ `team-skill-reviewers` group created on GH (pending external setup)
- ✅ Comprehensive test suite — unit (31 passing) + integration (Flask fixture) + e2e markers
- ✅ E2E smoke tests scaffolded (4 tests, manual invocation)
- ⏳ Formal InfoSec review (pending external review)
- ⏳ Resolve `design.md` §11 + `security.md` §11 open questions (in progress)
- ✅ Acceptable-use doc shipped (`docs/acceptable-use.md`)
- ⏳ Onboarding doc + 5-min intro video (text doc shipped at `docs/getting-started.md`; video deferred)

**Out of scope:**
- Unattended / scheduled runs
- Cross-org rollout (only the immediate team)

**Exit criteria:**
- InfoSec sign-off documented
- ≥20 users installed
- ≥3 team skills promoted from personal flows
- Bug rate / week trending down
- Operational runbook for the maintainer (release process, incident response)

**Resourcing:** Sunil + 1 part-time contributor + InfoSec coordinator.

**Gating items (from `security.md` §11):**
- ✅ Conditional Access compatibility tested
- ✅ EDR / Crowdstrike compatibility confirmed
- ✅ PowerBI licensing question answered
- ✅ Service-account path scoped (for Phase 4)

---

## Phase 4 — Scheduled runs + record-and-replay (3–6 months out)

**Goal:** support flows that run without a human in the loop (e.g., morning digest emails).

**Status:** 🟡 v0.1 shipped (record-and-replay + output piping + scheduler registry + headless flag + session keepalive); execution layer for unattended runs gated on IT decisions.

### What shipped (Phase 4 v0.1)

**Record-and-replay:**
- JS-injected click + input + navigation capture via `recording_install_capture`
- Polling-based event drain via `recording_drain`
- Parameterization heuristics (URLs, dates, tickets, repeated inputs) via `recording_extract_params`
- Self-healing replay via `click(description=...)` fuzzy matching
- Auto-reinjection after navigation events (JS state is lost on full page reload — the skill re-injects each time)

Files that landed: `browsermcp/recording_capture.py`, `browsermcp/recording_replay.py`, `browsermcp/recording_params.py`, `browsermcp/tools/recording.py`, `team-skills/record-flow/SKILL.md`

**Session keepalive:**
- `scripts/keepalive.py` + launchd plist (`scripts/com.browsermcp.keepalive.plist`)
- Touches each configured tab every 30 min to keep SSO tokens warm — does not run skills
- Config: `~/.browsermcp/keepalive.toml` (list of URL patterns to keep alive)
- Install: `bash scripts/install-keepalive.sh`

**Other:**
- Output piping: `notify-slack`, `notify-teams`, `notify-email` team skills
- Scheduler registry stub (`tools/scheduling.py`) — no execution yet
- `interactive: false` frontmatter flag for headless-capable skills

### Known v0.1 rough edges

| Issue | Status |
|---|---|
| JS state lost on full page reload — recorder auto-reinjects but events in the gap are missed | Known; CDP-level injection planned for v1.0 |
| No iframe support | Known; deferred |
| No visual recording indicator (red dot overlay) | Deferred |
| Parameterization is best-effort — user must review before promoting | By design in v0.1 |
| Password field *values* not captured | By design — field name/label still captured for replay targeting |

### How to test record-and-replay

```
# Record:
/record-flow name=my-test mode=record
# → walk through a simple task (e.g. search on a non-auth site like example.com)
# → type "stop" when done

# Replay:
/record-flow name=my-test mode=replay
# → watch the per-step result table — check ok/failed and notes
```

If you see `recording_install_capture` returning `already_installed: false` on every drain cycle, that means the page reloaded and reinjection is working correctly. If replay steps fail with "element not found", the likely cause is stale selector text or a page layout change between record and replay.

### Scheduled execution slices

| Slice | What lands | Gating |
|---|---|---|
| **v0 (shipped)** | Session keepalive — pings warm tabs every 30 min, no skill execution | None — launchd on user's machine |
| **v1 (next)** | Single-skill scheduled run against the user's attended Chrome profile | None — equivalent to user running a slash command |
| **v2 (later)** | Headless Chrome path + `interactive: false` skills unattended | Requires service-account or dedicated-profile decision |

### Remaining scope

- ⏳ Real scheduled execution layer (gated on IT hosting decision — user-laptop vs. shared machine)
- ⏳ Service-account or persistent profile path (gated on InfoSec decision)
- Multi-account flows (aggregate data from N user sessions)

**Exit criteria:**
- One scheduled flow ("morning Power BI digest") running reliably for ≥4 weeks across ≥3 users
- InfoSec re-review covering the new unattended attack surface

**Gating items:**
- Phase 3 stable for at least 6 weeks
- IT decision on where unattended runs execute

---

## Phase 5 — Cross-team expansion (6–12 months out)

**Goal:** broader adoption across other teams; potentially product-ize.

**Status:** 🟡 Scaffolding shipped (multi-team variant template, REGISTRY, governance, telemetry stub); broad rollout gated on Phase 3/4 adoption metrics.

### Layered team-skills model

Skills live in a layered directory under `team-skills/`:

```
team-skills/
├── all/          ← universal — every user gets these
├── produce/      ← produce-team-only (placeholder)
├── hr/           ← HR-team-only (placeholder)
├── finance/      ← finance-team-only (placeholder)
└── <flat>/*      ← legacy Phase 1–4 skills, treated as "all"
```

Install command:

```bash
bash team-onboarding/scripts/install.sh                  # universal only
bash team-onboarding/scripts/install.sh --team=produce   # universal + produce-specific
```

Promotion from personal → team repo requires a PR to either `team-skills/all/` (universal, two-reviewer rule) or `team-skills/<team>/` (single reviewer + team lead). See `docs/security.md §13` for the full governance rules.

**Open question:** How does `install.sh` know the user's team automatically? Today: explicit `--team=` flag. Future: query Microsoft Graph API for Entra ID group membership. Gated on InfoSec scope approval.

### What shipped

- ✅ `--team` flag + layered directory structure in `install.sh`
- ✅ `team-skills/REGISTRY.md` skill marketplace inventory
- ✅ Telemetry opt-in framework (no-op sink; real sink deferred)
- ⏳ Web UI for non-Claude-Code users
- ⏳ Real cross-team adoption (humans, not scaffolding)

**Exit criteria:**
- ≥3 distinct teams using their own customized BrowserMCP plugin variants
- Self-service skill creation works without engineer intervention
- Operational SLOs defined and met

---

## Risk register

Risks that could derail any phase, and what we'd do about them:

| Risk | Likelihood | Impact | Mitigation / Trigger |
|---|---|---|---|
| InfoSec says no | Medium | High | Engage early in Phase 2; have alternatives (API-only mode, service-account model) ready |
| Browser-use upstream breaks API | Medium | Medium | Pin version; allocate buffer time in each phase for upgrades |
| Claude Code MCP API changes | Low | High | Track Anthropic's changelogs; keep MCP surface small |
| Pilot users don't actually use it | Medium | High | Choose pilot users who have *specific* workflows in mind; show working demo before committing them |
| A team-skill PR introduces a security regression | Low | High | Required reviewer + checklist; emergency-release process documented |
| Chrome / Playwright update breaks attach | Medium | Medium | Pin Chrome version in shim; nightly smoke catches early |
| Scheduled-run hosting becomes a blocker | High | Medium | Defer Phase 4 until Phase 3 is solid; user-laptop-only is acceptable initial answer |

---

## Cadence / milestones

```
Month 1   |  Phase 0  (design)        + Phase 1 PoC starts
Month 2   |  Phase 1 wraps            + Phase 2 pilot starts
Month 3   |  Phase 2 wraps
Month 4   |  Phase 3 starts           + InfoSec review begins
Month 5   |  Phase 3 wraps
Month 6   |  Phase 3 stabilization
Month 7   |  Phase 4 starts
Month 9   |  Phase 4 wraps
Month 12  |  Phase 5 starts
```

This is aggressive and depends on Sunil being able to dedicate meaningful time. Adjust as priorities shift.

---

## Decision log

Major decisions and when they were made — to be appended over time.

| Date | Decision | Rationale | See |
|---|---|---|---|
| 2026-06-24 | Use Claude Code as the LLM brain via MCP, not a standalone agent with shared API keys | Avoids credential management; uses existing user entitlements | `design.md` §6 |
| 2026-06-24 | Attach to user's Chrome via CDP (default new-window) rather than headless or dedicated profile | Inherits SSO sessions; non-blocking UX; builds user trust | `design.md` §7 |
| 2026-06-24 | Local-only, no central server in v1 | Smaller attack surface; faster IT review; simpler ops | `design.md` §10 |
| 2026-06-24 | Team sharing via GitHub PR against `BrowserMCP` repo | Uses existing tooling; review built-in; audit trail | `design.md` §10 |
| 2026-06-24 | Defer headless/scheduled to Phase 4 | Don't optimize for unattended runs until attended pattern is proven | this doc |

---

## Recent activity

Quick "what shipped when" reference, most recent first. The repo's history was
squashed into a single initial commit, so these are descriptions rather than
commit links:

- Allow outlook.cloud.microsoft + outlook.office.com in default allowlist
- Phase 2 fix + Phase 3: promote-flow + create-flow + record-flow scaffold
- Phase 2: meta-skills, team skills, integration tests, getting-started
- Add `chrome_find_or_open_window` — reuse existing signed-in tabs
- Allow Microsoft 365 / Power BI domains in default allowlist
- Make Playwright the primary CDP client; require dedicated profile
- tests: unit-test `extraction.py` flat-schema helpers
- docs: update path references from `mcp/` to `browsermcp/`
- Phase 1 scaffold: MCP server + 5 browser primitives + `/powerbi-scan`
- Add `pyproject.toml` — pin `browser-use` and the CDP client
- Add team-onboarding skill + manual install path
- Initial design docs for BrowserMCP

---

## What "v1.0" means

"v1.0" = end of Phase 3 + first ~6 weeks of stable Phase 4 operation. Not a marketing milestone — just the point at which we stop calling it a pilot and start calling it a tool.

Target: ~6 months from Phase 1 start.

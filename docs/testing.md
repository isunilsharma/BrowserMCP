# Testing

> How we'll know BrowserMCP works — and keeps working.

## 1. Testing philosophy

Browser automation is famously flaky. Our strategy reflects that:

1. **Trust nothing** — every layer is tested in isolation before integration.
2. **Test against fixtures, not production** — we run against a local fixture web app, not real Power BI / Jira, except for nightly smoke tests.
3. **Fail loudly, log thoroughly** — when something flakes, we want a clear repro, not a mystery.
4. **Keep tests fast** — slow tests don't get run.

## 2. The test pyramid

```
                    ┌──────────────────┐
                    │   E2E    ~10     │   ← real Chrome, real Claude Code,
                    │  (manual + CI)   │     production-like sites
                    └────────┬─────────┘
                  ┌──────────┴──────────┐
                  │   Integration ~50   │   ← real Chrome + real MCP server,
                  │   (CI on PR)        │     local fixture web app
                  └──────────┬──────────┘
              ┌──────────────┴──────────────┐
              │       Unit  ~200            │   ← every PR, sub-second
              │     (fast, mocked)          │
              └─────────────────────────────┘
```

Numbers are rough targets; ratios matter more than absolute counts.

## 3. Unit tests (mocked, fast)

**What we test:** pure logic in each tool function — input validation, parameter handling, response shaping, error paths.

**What we mock:** Playwright `Page`/`Browser`, browser-use's resolvers, the LLM (for `extract()` slow path).

**Tooling:** `pytest`, `pytest-asyncio`, `pytest-mock`.

### Example test

```python
# tests/tools/test_navigation.py
import pytest
from browsermcp.tools.navigation import navigate, NavigateResult

async def test_navigate_returns_title_and_url(mock_page):
    mock_page.goto.return_value = None
    mock_page.title.return_value = "Power BI"
    mock_page.url = "https://powerbi.example.com/"

    result = await navigate("https://powerbi.example.com/", page=mock_page)

    assert isinstance(result, NavigateResult)
    assert result.title == "Power BI"
    assert result.url == "https://powerbi.example.com/"
    mock_page.goto.assert_called_once_with(
        "https://powerbi.example.com/", wait_until="networkidle"
    )

async def test_navigate_rejects_javascript_urls(mock_page):
    with pytest.raises(ValueError, match="unsafe protocol"):
        await navigate("javascript:alert(1)", page=mock_page)
```

### Coverage target
- 100% on `redact.py` (security-critical)
- 95%+ on `tools/*` (each tool's happy + error paths)
- 90%+ on `skill_helpers/*`

## 4. Integration tests (real Chrome, fixture sites)

**What we test:** the full MCP server driving a real Chrome against a local fixture web app — verifying that primitives compose correctly.

**Fixture app:** a small Flask app in `tests/fixtures/site/` that mimics common patterns:
- A form with required fields and validation
- A paginated table
- A modal that pops up after click
- A page with infinite scroll
- A page that requires "login" (fake)

We can also include fixture pages that *resemble* Power BI / Jira layouts without being real instances.

**Tooling:** `pytest`, `pytest-playwright`, headless Chromium.

### Example test

```python
# tests/integration/test_form_fill.py
async def test_can_fill_and_submit_a_form(fixture_site, mcp_server):
    await mcp_server.call("chrome_attach")
    await mcp_server.call("chrome_new_window")
    await mcp_server.call("navigate", url=f"{fixture_site}/form")
    await mcp_server.call("type", field="email", text="test@example.com")
    await mcp_server.call("type", field="message", text="Hello")
    await mcp_server.call("click", description="Submit button")

    page = await mcp_server.call("read_page")
    assert "Thanks for your message" in page.text
```

### Browser version pinning
Chromium version is pinned via Playwright's version manifest. Bumping it requires a manual sweep of integration tests to make sure nothing regressed.

## 5. End-to-end tests (real sites, low frequency)

**What we test:** that real team skills (`/powerbi-scan`, `/confluence-search`, etc.) work against real internal sites — but in a controlled way.

**When they run:**
- On-demand by an engineer before a release
- Nightly via a scheduled job that uses a dedicated test account with view-only access to staging Power BI / Confluence / Jira
- Never on every PR (too slow, too flaky)

**What they cover:**
- Smoke: "the flow runs to completion without error"
- Light assertions: "the result contains a non-empty KPI list", "the search returns at least one page"

E2E tests don't make precise assertions about content (which changes). They check **shape**, not exact values.

### Example
```python
# tests/e2e/test_powerbi_scan.py
@pytest.mark.e2e
async def test_powerbi_scan_smoke(claude_code_session, real_chrome):
    result = await claude_code_session.run_skill(
        "powerbi-scan",
        args={"report": "Test Report (E2E)"},
    )
    assert result.success
    assert len(result.kpis) > 0
    for kpi in result.kpis:
        assert kpi.name and kpi.value
```

## 6. The `extract()` evaluation harness

`extract()` is the most failure-prone primitive (LLM-influenced). We treat it like a model-eval:

**Eval set:** `tests/extract_evals/` contains 50+ pairs of `(html_snapshot, schema, expected_output)`.

**How it runs:** `pytest --extract-evals` runs each case, scoring extraction accuracy. We track:
- Field-level F1
- Schema-validation pass rate
- Confidence calibration (does `confidence="high"` actually mean ≥95% accurate?)

**Pass threshold:** ≥90% field-level F1 on the eval set. Below that, a PR can't merge.

## 7. Skill testing

Each team skill in `team-skills/<name>/` has a test file in `tests/skills/test_<name>.py`.

Skills are LLM-driven, so we test them indirectly:
- **Determinism check:** run the skill 3× against the fixture site; verify it produces equivalent results
- **Argument handling:** verify required args are enforced, defaults applied
- **Error surfacing:** verify a "session expired" simulation produces the expected user-facing message

We do NOT assert exact MCP tool call sequences — Claude Code may legitimately pick different paths.

## 8. Security tests

A dedicated set covers the highest-risk paths:

| Test | What it verifies |
|---|---|
| `test_no_tokens_in_logs.py` | Run a flow, scan logs for known token shapes. Must find none. |
| `test_pii_redactor.py` | Feed known PII into the redactor, verify all variants get masked. |
| `test_destructive_requires_confirm.py` | Run `/jira-bulk-update` without confirmation. Must abort. |
| `test_javascript_url_blocked.py` | Try `navigate("javascript:...")`. Must reject. |
| `test_remote_debugging_localhost_only.py` | Verify Chrome is launched with `--remote-debugging-address=127.0.0.1`. |
| `test_no_external_network.py` | Run a flow against fixture site; assert no network requests left the machine except to known internal hosts. |

See `docs/security.md` for the full threat model.

## 9. Manual test plan (pre-release checklist)

Before each release, an engineer runs through this manually:

```
[ ] Fresh install on a clean macOS account
[ ] Fresh install on a clean Windows account
[ ] Chrome attach succeeds with default settings
[ ] /powerbi-scan against a real Power BI report
[ ] /confluence-search against an internal Confluence space
[ ] /jira-bulk-update (dry-run only — do NOT actually update)
[ ] /save-as-flow turns a chat into a working personal skill
[ ] /promote-flow opens a PR against the BrowserMCP repo
[ ] /flows-list shows correct history
[ ] Cancel a flow mid-run; verify clean shutdown
[ ] Session-expired flow shows the right error
[ ] Cost of a typical flow stays under 10k tokens
```

Manual checklist lives in `tests/manual_checklist.md`.

## 10. CI configuration

`.github/workflows/ci.yml` runs:

| Job | Trigger | Duration |
|---|---|---|
| `lint` | every push | ~10 s |
| `unit` | every push | ~30 s |
| `integration` | every push (PR only) | ~3 min |
| `extract-evals` | every push (PR only) | ~5 min |
| `e2e-smoke` | nightly, scheduled | ~10 min |
| `security-scan` | every PR (Bandit + Semgrep) | ~1 min |

PRs need lint + unit + integration + extract-evals + security-scan to pass.

## 11. Bug regression tests

Every bug fix lands with a regression test that:
- Is named `tests/regressions/test_<issue-number>_<short_desc>.py`
- Has a docstring linking back to the original issue
- Fails before the fix, passes after

This keeps the test suite organically growing the right shape.

## 12. Performance tests

We don't have strict SLOs but we track:

| Metric | Soft target |
|---|---|
| `chrome_attach` p95 | < 250 ms |
| `click` p95 (after first time on page) | < 300 ms |
| Full `/powerbi-scan` p95 | < 90 s |
| LLM tokens per `/powerbi-scan` p95 | < 5000 in + 1000 out |

Tracked via a small benchmark in `tests/perf/bench.py` that runs on demand.

## 13. What we explicitly don't test

| Skipped | Why |
|---|---|
| Exact LLM-generated text in skill responses | Non-deterministic, low-value to assert |
| Pixel-perfect screenshots | Pages change; visual diffs are flaky |
| Production Power BI / Jira data | Risk + flakiness; covered by E2E smoke instead |
| `browser-use` library internals | Trust the upstream library's tests; integrate via their public API |

## 14. Test data and fixtures

```
tests/
├── fixtures/
│   ├── site/                     # Flask app simulating common patterns
│   │   ├── form.html
│   │   ├── table_paginated.html
│   │   ├── modal_after_click.html
│   │   └── fake_login.html
│   ├── chrome_profile/           # disposable Chrome profile w/ known cookies
│   └── pages/                    # static HTML snapshots for extract evals
├── extract_evals/
│   └── *.json                    # (html, schema, expected) triples
├── tools/                        # unit tests
├── integration/                  # integration tests
├── e2e/                          # end-to-end tests
├── skills/                       # per-skill tests
├── regressions/                  # bug regression tests
└── manual_checklist.md           # pre-release checklist
```

## 15. Definition of "done" for a feature

A feature is done when:

- ✅ Unit tests pass and cover happy + error paths
- ✅ Integration test exists against the fixture site
- ✅ If it's a new MCP tool: documented in `docs/techflow.md` §5
- ✅ If it's a new skill: test in `tests/skills/`
- ✅ If it touches security-sensitive code: security test added
- ✅ Lint + type-check clean
- ✅ Manual checklist updated if the user-visible behavior changed

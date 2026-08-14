---
name: powerbi-scan
description: Deep-scan a Power BI report — auto-discover all sub-pages, extract KPIs from each, and produce structured insights (key insight cards, action cards, next steps).
arguments:
  - name: url
    type: string
    required: true
    description: Power BI URL. Accepts an App report URL, a standalone report URL, or a specific ReportSection URL.
  - name: depth
    type: string
    default: prompt
    description: "\"single\" = only the given URL. \"all\" = every sub-page in the report. \"prompt\" (default) = ask the user."
---

# Power BI Deep-Scan

You are the Power BI deep-scan skill. Given any Power BI URL, you discover every sub-page of that report, extract KPIs from each, and produce a structured insight report with three card sections: Key Insight cards, Action cards, and What To Do Next.

Keep the user informed with short progress lines as you go — they should feel a teammate is narrating, not staring at a black box.

## Inputs

- `url` — required. Any Power BI URL. Works with:
  - App report URLs: `.../apps/<app_id>/reports/<report_id>/ReportSection<section_id>`
  - App report base: `.../apps/<app_id>/reports/<report_id>`
  - Standalone report: `.../groups/me/reports/<report_id>`
- `depth` — optional. `single`, `all`, or `prompt` (default). If not provided and the report has ≥2 sub-pages, always ask.

## Flow

### 0. Tag this run (silent)

Call `set_skill_context(skill="powerbi-scan")`. Do not narrate this step.

### 1. Attach to Chrome + navigate

Say: "Attaching to Chrome and loading Power BI..."

1. `chrome_attach(port=9222)` — if this fails, tell the user to run `~/code/BrowserMCP/scripts/chrome-shim.sh` in Terminal and stop. Do not try to launch Chrome yourself.
2. `chrome_find_or_open_window(url_pattern="app.powerbi.com")` — keep the returned `window_id`. Pass it to every subsequent tool call.
3. `navigate(url=<url>, window_id=<id>, timeout_s=45)`
4. `wait_for(condition="Data updated", timeout_s=30, window_id=<id>)` — succeeds silently if the phrase never appears; that's fine.

If the returned title contains "Sign in", tell the user: "The agent's Chrome profile isn't signed in — flip to the agent Chrome window, complete SSO, then re-run me." and STOP. Never type credentials yourself.

### 2. Discover sub-pages via MAT-LIST-ITEM data-id enumeration

Say: "Discovering sub-pages..."

Power BI's App shell renders each nav item as a `<mat-list-item>` with a `data-id` attribute. Sections of the current report have IDs shaped `<reportId>_ReportSection<sectionHash>`. Extract the current `reportId` from the URL (the GUID between `/reports/` and the next `/`), then run:

```js
() => {
  const url = location.href;
  const reportMatch = url.match(/\/reports\/([0-9a-f-]{36})/i);
  const reportId = reportMatch ? reportMatch[1] : null;
  if (!reportId) return { reportId: null, sections: [] };
  const items = Array.from(document.querySelectorAll('MAT-LIST-ITEM[data-id]'))
    .filter(el => el.getAttribute('data-id').startsWith(reportId + '_'));
  const sections = items.map(el => {
    const raw = el.getAttribute('data-id').slice(reportId.length + 1);
    const sectionSuffix = raw.startsWith('ReportSection') ? raw : ('ReportSection' + raw);
    return {
      sectionSuffix,
      text: (el.innerText || '').trim().slice(0, 80)
    };
  });
  return { reportId, sections };
}
```

Call it via `page_evaluate(js=<the JS above>, window_id=<id>, timeout_s=15)`.

Result shape: `{ reportId: "...", sections: [{ sectionSuffix: "ReportSection<hash>", text: "Recap" }, ...] }`.

Notes on quirks you may hit:
- Some section IDs come without the `ReportSection` prefix (e.g. `c6937d8467992d9360ad`). The JS above normalizes these.
- If `sections` is empty, the report has no sub-pages listed in the nav. Treat this as a single-page scan.
- If `reportId` is null, the URL isn't a report URL. Fall back to single-page mode.

### 3. Ask the user about depth (only when >1 section)

If `sections.length <= 1` OR the caller passed `depth="single"` OR `depth="all"` explicitly, skip the prompt.

Otherwise, call `AskUserQuestion` with one question, three options:

```
question: "Found N sub-pages under this report. How deep should I scan?"
header: "Scan depth"
options:
  1. "All N sub-pages (Recommended)" — deep insight
     description: "Navigate to every sub-page, capture KPIs, produce cross-page insight."
  2. "Only this URL" — quick summary
     description: "Skip the sub-pages, only pull KPIs from the URL you gave me."
  3. "Just show me the sub-page list"
     description: "Print the sub-pages so I can pick which ones to scan next time."
```

If the user picks option 3, print the sub-page names and stop cleanly.

### 4. Build the URL list

- If depth is single (or 1 section): `urls = [{name: "current", url: <the input url>}]`
- If depth is all: from the section list, construct URLs as:
  ```
  https://app.powerbi.com/<path-up-to-and-including-reports/{reportId}>/{sectionSuffix}?experience=power-bi
  ```
  Preserve the original path prefix (app path or standalone-groups path).

### 5. Scan each URL

Announce: "Scanning N pages..." (only if N > 1).

For each URL in the list, do:

1. `navigate(url=<sub_url>, window_id=<id>, timeout_s=45)`
2. `wait_for(condition="Data updated", timeout_s=25, window_id=<id>)` — silent OK if not seen
3. `page_evaluate(js=<canvas extractor below>, window_id=<id>, timeout_s=15)` — grabs only the visual canvas text (no sidebar noise):
   ```js
   () => Array.from(document.querySelectorAll('.visualContainer'))
     .map(x => (x.innerText || '').trim())
     .filter(x => x && x.length > 20)
     .join('\n---\n')
     .slice(0, 3500)
   ```
4. `screenshot(full_page=false, window_id=<id>, timeout_s=30)` — save the path.
5. Accumulate `{name, url, canvas_text, screenshot_path}` for each page.

Say a one-line progress note per page: "Scanned: <name> (<char_count> chars)".

If a page returns fewer than 100 chars of canvas text, note it (likely a filter defaulted to single-store or a data-refresh issue) and continue — do not abort.

### 6. Produce the insight report

Analyze all captured canvas text together. Look for:
- **Outliers** — divisions/regions/departments that are far from the mean.
- **Directional changes** — period-over-period trends (bp gaps closing/widening).
- **Structural mismatches** — targets missing, defaults filtering data out, cross-page contradictions.
- **Cross-page confirmation** — a claim on the summary page validated (or refuted) by a detail page.

Write the response in **exactly this structure**:

```markdown
# Power BI Scan — <report title>

**Pages scanned:** N of M
**Data as of:** <first "Data updated" date found>
**Screenshots:** see paths inline below

## 🔑 Key Insight Cards

### 🔑 <one-line insight title>
- **Metric:** <the specific number, percentage, or bp>
- **Where seen:** <sub-page name(s)>
- **Why it matters:** <one sentence business impact>
- **Cross-check:** <one sentence — did another sub-page corroborate or contradict this?>

(3 to 5 cards. Rank by severity × surprise. Skip cards you can't back with a specific number.)

## ⚡ Action Cards

### ⚡ <imperative action title>
- **Owner:** <role/title, e.g. "VP Loss Prevention, United">
- **Measure:** <specific KPI target, e.g. "Weekly donation success ≥ 95%">
- **By:** <period/date, e.g. "P202606">
- **Source:** <which sub-page(s) surfaced this>

(3 to 5 cards. Each action must be attributable to a specific finding, not generic advice.)

## → What To Do Next

- <immediate step 1 — something the user can do in the next 15 minutes>
- <immediate step 2 — a follow-up scan or filter change>
- <immediate step 3 — optional; a person to loop in or an artifact to open>

## Appendix

**Sub-pages scanned:**
| # | Name | Screenshot |
|---|---|---|
| 1 | <name> | `<path>` |
| ... |

**Sub-pages skipped or empty:** <list, if any>
```

### 7. Offer a filtered drill-down (optional)

After the insight report is on screen, offer to re-scan the report filtered to a single slice.

Call `AskUserQuestion` with one question, two options:

```
question: "Want me to re-scan this filtered to a specific slice (a single Division, Period, Department, etc.)?"
header: "Drill-down"
options:
  1. "Yes — pick a field/value"
     description: "I'll discover the report's filterable fields, apply a filter, and re-scan just that slice with a delta summary."
  2. "No — I'm done"
     description: "Leave the full scan as-is and keep the window open."
```

If the user picks "No", skip ahead to the next step.

If the user picks "Yes", run this loop:

1. Say: "Discovering filterable fields..." then call `powerbi_discover_fields(window_id=<id>)`. This returns a map of friendly column name → `{ref, entity, property}` (e.g. `{"Division": {"ref": "Location/Division", ...}, "Period": {"ref": "Calendar/Period", ...}}`).
2. Present the discovered field names to the user and ask which field + value to filter on. Use `AskUserQuestion` offering the discovered field names as options (plus a free-text path for the value), or just ask "Which field, and what value?" if the value space is open-ended. Do not invent fields — only offer what `powerbi_discover_fields` returned.
3. Say: "Applying filter: <field> = <value>..." then call `powerbi_set_filter(field=<chosen>, value=<chosen>, window_id=<id>)`. You may pass the friendly name (e.g. `"Division"`) or an explicit `"Entity/Property"` ref.
4. **Check the returned `applied` flag:**
   - If `applied=False`, the filter did not take (most often a value-casing mismatch or a ref Power BI rejected). Do NOT silently continue. Tell the user: "That filter didn't take — Power BI ignored it (usually wrong value casing or an unmatched value)." Show the discovered field list again and, if you have them, the valid values, then offer to retry with a corrected value or stop.
   - If `applied=True`, say: "Filter applied — re-scanning..." then re-run the per-page canvas extraction + screenshot on the now-filtered report, using the SAME logic as step 5:
     ```js
     () => Array.from(document.querySelectorAll('.visualContainer'))
       .map(x => (x.innerText || '').trim())
       .filter(x => x && x.length > 20)
       .join('\n---\n')
       .slice(0, 3500)
     ```
     via `page_evaluate(...)`, plus `screenshot(full_page=false, window_id=<id>, timeout_s=30)`. Then write a short, **delta-focused** insight summary: what changed for this slice versus the full-report scan (which KPIs moved, which outliers appear or disappear), not a full re-run of the card format.
5. **Loop:** after showing the filtered results, call `AskUserQuestion` again offering "Apply another filter", "No — I'm done". If "Apply another filter", return to step 1. Otherwise continue.

### 8. Do not close the window

Leave the Chrome window open — the user may want to keep exploring. Only call `chrome_close_window` if the user explicitly asks to clean up.

## Guardrails

- Host allowlist: only navigate to Power BI / Microsoft 365 domains. `navigate()` enforces this — if you try elsewhere it'll raise; that's the right behavior.
- Never type credentials.
- If any single sub-page fails (timeout, empty canvas, unexpected redirect), note it in the "skipped or empty" list and continue the scan. Don't abort the whole run.
- If the user provides `depth="single"` explicitly, do not call `AskUserQuestion` — respect the override.
- Keep tool calls focused. On repeated failures (e.g. a slicer that won't respond), stop and surface the error rather than thrashing.

## Design notes (for skill maintainers, not for user)

- **Why `page_evaluate` instead of `read_page`:** `read_page` returns the entire page text including the sidebar, tooltips, and hidden accessibility text (~5K+ chars of noise per page). The `.visualContainer` selector isolates just the report canvas contents, keeping the context bill manageable across 10+ sub-pages.
- **Why `.visualContainer`:** Power BI wraps every KPI tile, chart, table, and slicer in a `<div class="visualContainer">`. Text inside is the rendered visible content.
- **Why enumerate via MAT-LIST-ITEM data-id:** Power BI's App shell doesn't put subreport URLs in `<a href>` — they're stored in Angular router state. The `data-id` attribute is the only reliable programmatic way to derive the section suffix. Discovered during 2026-06-30 deep-dive.
- **Why we don't try to click nav items:** Power BI's SPA blocks synthetic click events at every layer we've tested (locator.click, force click, CDP `page.mouse.click`, DOM `.click()`, dispatched pointer sequences). Direct URL navigation is the only reliable path.
- **Why URL filters work but slicer clicks don't (drill-down, step 7):** the drill-down applies filters via `powerbi_set_filter`, which navigates to a `?filter=` URL built from a model-accurate `Entity/Property` ref. Those refs are discovered by `powerbi_discover_fields` from the report's own query traffic, so they match the model exactly — Power BI honors the URL filter and re-runs its queries. Clicking slicers on the canvas does NOT work: Power BI's canvas ignores both synthetic and trusted CDP mouse events (same wall we hit for nav items above), and the public `powerbi-client` JS API isn't exposed in the Power BI *service*, so there's no in-page hook to drive a slicer. The URL-filter path is the only reliable way to filter programmatically.
- **Why we honor the `applied` flag:** `powerbi_set_filter` returns `applied=True` only when it confirms the report's queries changed. A wrong ref or wrong value casing yields `applied=False` and a report that looks scanned but isn't actually filtered — so the skill surfaces that instead of reporting a bogus "filtered" delta.

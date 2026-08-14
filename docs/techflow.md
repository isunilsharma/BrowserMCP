# Technical flow

> What actually happens under the hood — sequence diagrams, MCP wire calls, Chrome attach mechanics, data shapes.

## 1. Components in play

```
┌──────────────────────────────┐    ┌──────────────────────────────┐
│  Claude Code Desktop         │    │  BrowserMCP Server           │
│  (Anthropic native app)      │    │  (your Python process)       │
│                              │    │                              │
│  • Hosts the LLM session     │    │  • Implements MCP protocol   │
│  • Reads skill files         │    │  • Wraps browser-use         │
│  • Dispatches MCP tool calls │    │  • Drives Chrome via CDP     │
└──────────────┬───────────────┘    └──────────────┬───────────────┘
               │                                    │
               │       MCP (JSON-RPC over stdio)    │
               ├──────────────────────────────────►│
               │                                    │
               │                                    ▼
               │                    ┌──────────────────────────────┐
               │                    │  Chrome (user's instance)    │
               │                    │  --remote-debugging-port=9222│
               │                    │                              │
               │                    │  • SSO'd to internal apps    │
               │                    │  • Real user profile         │
               │                    └──────────────────────────────┘
               │
               ▼
   ┌─────────────────────────────┐
   │  Anthropic API              │
   │  (uses user's Claude Code   │
   │   subscription credentials) │
   └─────────────────────────────┘
```

Three processes, one machine. No central server.

## 2. The MCP protocol layer

MCP servers communicate with Claude Code over **JSON-RPC 2.0 on stdio** (default) or HTTP/SSE (optional). For BrowserMCP we use stdio because the server runs locally alongside Claude Code.

### Server startup

```
Claude Code → spawns BrowserMCP server process
            → exchanges initialize handshake
            → asks for list of available tools (tools/list)
            ← server replies with tool schemas
```

### Tool invocation (the hot path)

```
Claude Code → tools/call { name: "click", arguments: { description: "Submit button" } }
            ← server returns { content: [{ type: "text", text: "Clicked." }] }
```

Each MCP tool returns structured content (text, JSON, image data). For long-running tools, we stream progress via JSON-RPC notifications.

## 3. Sequence: `/powerbi-scan --report "Q3 Produce Sales"`

The full timeline of a single skill run, showing every wire call:

```
Time   Actor              Action
─────  ─────────────────  ─────────────────────────────────────────────────
T+0    User               Types /powerbi-scan in Claude Code
T+0    Claude Code        Loads team-skills/powerbi-scan/SKILL.md
T+0    Claude Code        Reads frontmatter, prompts user for "report" arg
T+1    User               Types "Q3 Produce Sales"
T+1    Claude Code        Begins LLM session with SKILL.md as system prompt
                          + the user's report arg

T+2    Claude Code → MCP  tools/call  chrome_attach()
T+2    BrowserMCP         Checks if Chrome is running on port 9222
T+2    BrowserMCP         Connects via Playwright CDPSession
T+2    BrowserMCP → CC    { content: [{ text: "Attached. Profile: Default" }] }

T+3    Claude Code → MCP  tools/call  chrome_new_window()
T+3    BrowserMCP         Calls browser.contexts[0].new_window()
T+3    BrowserMCP → CC    { content: [{ text: "Opened window id=w-abc" }] }

T+4    Claude Code → MCP  tools/call  navigate(url="https://powerbi.example.com")
T+4    BrowserMCP         page.goto(...)  + waits for load
T+4    BrowserMCP → CC    { content: [{ text: "Loaded. Title: 'Power BI Home'" }] }

T+5    Claude Code → MCP  tools/call  read_page(viewport_only=true)
T+5    BrowserMCP         Returns accessibility tree + visible text
T+5    BrowserMCP → CC    { content: [{ json: { tree: {...}, text: "..." } }] }

T+6    Claude Code (LLM)  Decides: search for "Q3 Produce Sales"

T+7    Claude Code → MCP  tools/call  click(description="search icon")
T+7    BrowserMCP         Uses browser-use's vision/DOM to resolve target
T+7    BrowserMCP         page.click(<resolved selector>)
T+7    BrowserMCP → CC    { content: [{ text: "Clicked." }] }

T+8    Claude Code → MCP  tools/call  type(field="search input", text="Q3 Produce Sales")
T+9    Claude Code → MCP  tools/call  click(description="Q3 Produce Sales link")
T+10   Claude Code → MCP  tools/call  wait_for(condition="report loaded")
T+15   Claude Code → MCP  tools/call  read_page()
T+15   Claude Code (LLM)  Identifies 8 KPI tiles

T+20   Claude Code → MCP  tools/call  extract(schema=KPIList, prompt="top 5 KPIs")
T+22   BrowserMCP         Runs extract() — uses sub-LLM if needed, or
                          deterministic DOM walk if schema is simple
T+22   BrowserMCP → CC    { content: [{ json: { kpis: [{name:..., value:...}, ...] } }] }

T+23   Claude Code → MCP  tools/call  screenshot()
T+23   BrowserMCP         page.screenshot(path=~/browsermcp-runs/.../shot.png)
T+23   BrowserMCP → CC    { content: [{ image: "...base64..." }] }

T+24   Claude Code        Renders the markdown table to the user
T+24   Claude Code → MCP  tools/call  chrome_close_window(id="w-abc")
T+24   BrowserMCP         Closes the agent window

T+25   Run complete       Log written to ~/browsermcp-runs/<timestamp>.jsonl
```

## 4. Chrome attach: the wire-level detail

### How Chrome is launched

After plugin install, Chrome is launched via a small shim:

```bash
# ~/.local/bin/chrome  (added to PATH by the plugin)
exec /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome" \
  "$@"
```

The `--remote-debugging-address=127.0.0.1` binding is important: only localhost can connect. (See `docs/security.md` for why.)

### How BrowserMCP attaches

```python
# Roughly what the chrome_attach tool does
import playwright.async_api as pw

async def chrome_attach() -> AttachResult:
    p = await pw.async_playwright().start()
    browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    contexts = browser.contexts          # the user's existing profile
    return AttachResult(
        profile_name=contexts[0].pages[0].evaluate("navigator.userAgent"),
        context_id=contexts[0]._impl_obj._guid,
    )
```

### Connection failure modes

| Failure | User-facing message | Cause |
|---|---|---|
| `connection refused` | "Chrome isn't running with remote-debugging. Open Chrome via the browsermcp shim and try again." | Chrome started without the flag |
| `port already in use` | "Another debugger is using port 9222. Close it or change browsermcp's port in `~/.browsermcp/config.toml`." | DevTools, another MCP server, IDE debugger |
| `no contexts` | "Chrome is running but no profile is loaded. Open at least one window first." | Chrome was launched but has no windows |

## 5. MCP tool reference

The full set of tools the server exposes, with their signatures.

### Layer 1 — Primitives

#### `chrome_attach()`
```python
def chrome_attach() -> AttachResult
```
Connect to the running Chrome on port 9222.

#### `chrome_new_window()`
```python
def chrome_new_window() -> WindowRef
```
Open a new window using the attached profile. Returns a `window_id` for later targeting.

#### `navigate(url: str, window_id: str | None = None)`
```python
def navigate(url: str, window_id: str | None = None) -> NavigateResult
```
Go to a URL. If `window_id` is omitted, uses the most recently opened agent window.

#### `click(description: str, window_id: str | None = None)`
```python
def click(description: str, *, window_id: str | None = None) -> ClickResult
```
Click an element described in natural language. browser-use resolves the description to a selector using vision + DOM heuristics.

#### `type(field: str, text: str, *, window_id: str | None = None)`
```python
def type(field: str, text: str, *, window_id: str | None = None) -> TypeResult
```
Type text into a field described in natural language.

#### `read_page(*, viewport_only: bool = True, window_id: str | None = None)`
```python
def read_page(
    viewport_only: bool = True,
    window_id: str | None = None,
) -> PageReadResult
```
Return structured info about the current page:
```python
class PageReadResult(BaseModel):
    title: str
    url: str
    text: str               # visible text only
    elements: list[Element] # interactable elements w/ stable refs
    accessibility_tree: dict
```

#### `extract(schema: dict, prompt: str, *, window_id: str | None = None)`
```python
def extract(
    schema: dict,        # JSON-schema describing wanted shape
    prompt: str,         # natural-language description of what to extract
    window_id: str | None = None,
) -> ExtractResult
```
Pull structured data from the page matching the given schema. If the schema is simple (1-level dict), uses a deterministic DOM walk. For complex extraction, falls back to a sub-LLM call.

#### `screenshot(*, full_page: bool = False, window_id: str | None = None)`
#### `wait_for(condition: str, *, timeout_s: int = 30, window_id: str | None = None)`
#### `scroll(direction: Literal["up","down","top","bottom"], amount: int = 500, window_id: str | None = None)`

### Layer 2 — Conveniences

#### `with_chrome_profile(profile_path: str)`
Attach to a specific Chrome user-data-dir (for the "dedicated bot profile" pattern).

#### `session_save(name: str)` / `session_restore(name: str)`
Snapshot/restore cookies + localStorage for a profile under `~/.browsermcp/sessions/<name>/`.

#### `run_saved_flow(name: str, args: dict)`
Invoke another Claude Code skill from inside a flow. Used for composition.

### Power BI drill-down helpers

Higher-level, Power-BI-specific helpers that let a skill *filter* a report the user has open. Power BI's canvas ignores synthetic clicks on slicers, so the only reliable lever is the URL query-string filter — but that needs the model's real `Entity/Property` field refs, which live only in the report's own semantic-query network traffic. These two tools recover those refs and use them. Both are **read-only / reporting** operations. (See `docs/security.md §3a` for the security posture.)

#### `powerbi_discover_fields(window_id=None, settle_s=9.0, timeout_s=45.0)`
```python
def powerbi_discover_fields(
    window_id: str | None = None,
    settle_s: float = 9.0,
    timeout_s: float = 45.0,
) -> PowerBIFieldsResult
```
Reload the Power BI report open in the window with a network listener armed, capture its semantic-query POST bodies, and return the model's filterable field references. Request bodies are inspected **in memory only** to recover field/column names — nothing is persisted.

Returns:
```python
class PowerBIField(BaseModel):
    ref: str          # e.g. "Location/Division" — feed to powerbi_set_filter
    entity: str       # model table
    property: str     # column name

class PowerBIFieldsResult(BaseModel):
    url: str
    captured: int                          # number of query bodies seen
    fields: dict[str, PowerBIField]        # friendly column name -> ref
    notes: str | None                      # e.g. "no query traffic captured"
```
**When to use:** before filtering a report, to learn the exact `Entity/Property` refs a filter must name (they aren't in the DOM). Also useful on its own to list what a report can be filtered by.

#### `powerbi_set_filter(field, value, window_id=None, verify=True, settle_s=9.0, timeout_s=45.0)`
```python
def powerbi_set_filter(
    field: str,
    value: str,
    window_id: str | None = None,
    verify: bool = True,
    settle_s: float = 9.0,
    timeout_s: float = 45.0,
) -> PowerBISetFilterResult
```
Apply a report-level filter to the open Power BI report by navigating to a `?filter=Entity/Property eq 'value'` URL. `field` may be a friendly column name (resolved via a fresh field discovery) or an explicit `Entity/Property` ref. With `verify=True`, the tool confirms the value reached the report's query `Where` clause, so `applied` reliably distinguishes a real filter from one Power BI silently dropped (wrong ref or mismatched value casing). Navigation only — it changes *what data is displayed*, never writing to any system; the target URL is checked against the host allow-list.

Returns:
```python
class PowerBISetFilterResult(BaseModel):
    ref: str          # the resolved Entity/Property used
    value: str
    url: str          # the filtered report URL navigated to
    applied: bool     # True if the filter reached the query Where clause
    captured: int     # query bodies seen during resolve + verify
    notes: str | None
```
**When to use:** to drill a Power BI report to a specific slice (e.g. `field="Division", value="United"`) when slicer clicks don't work.

### Layer 3 — Skills

Skills are NOT MCP tools; they're `SKILL.md` files Claude Code reads directly. They *use* the above MCP tools. The set of shipped skills lives in `team-skills/`.

## 6. Data shapes (Pydantic models)

All tool inputs/outputs are typed via Pydantic v2 models. Excerpts:

```python
class AttachResult(BaseModel):
    profile_name: str
    context_id: str
    pages_open: int

class Element(BaseModel):
    ref: str               # stable handle BrowserMCP can reuse
    role: str              # "button", "textbox", "link", etc.
    name: str              # accessible name / label
    visible: bool
    bounding_box: BBox | None

class PageReadResult(BaseModel):
    title: str
    url: str
    text: str
    elements: list[Element]
    accessibility_tree: dict

class ExtractResult(BaseModel):
    data: dict             # validated against the requested schema
    source_elements: list[str]  # element refs used
    confidence: Literal["high", "medium", "low"]
```

## 7. Logging & telemetry (local-only)

Every MCP tool call appends a line to `~/.browsermcp/runs/<run-id>.jsonl`:

```json
{"t": "2026-06-24T14:55:32Z", "tool": "click", "args": {"description": "Submit button"}, "result": "ok", "duration_ms": 142}
{"t": "2026-06-24T14:55:33Z", "tool": "read_page", "args": {"viewport_only": true}, "result": "ok", "duration_ms": 89, "bytes": 4421}
```

Args go through a PII redactor before logging (see `browsermcp/redact.py`):
- Email addresses → `<email>`
- Credit card numbers → `<cc>`
- Cookie/token strings → `<token>`
- Anything in a field labeled "password", "ssn", etc. → `<sensitive>`

There is **no central log aggregation in v1**. Each user's runs stay on their machine. (See `docs/security.md`.)

## 8. The `extract()` tool in detail

`extract()` is the trickiest primitive. It has two implementations:

### Fast path — deterministic
If the schema is flat (e.g., `{name: str, value: float}`) and the prompt is simple, BrowserMCP runs a deterministic extraction:

1. Identify candidate elements via DOM heuristics (tables, repeated patterns, ARIA labels)
2. Map elements to schema fields by header/label matching
3. Validate against the Pydantic schema
4. Return with `confidence="high"` if everything fits, `"medium"` if some fields needed fuzzy match

This avoids an LLM call per extraction.

### Slow path — sub-LLM
If the schema is nested or the prompt is complex, BrowserMCP falls back to a sub-LLM call:

1. Send the current `read_page()` output + the schema + the prompt to a small fast model (e.g., Haiku via the user's Claude Code session, or a configurable model)
2. The model returns JSON matching the schema
3. Validate, return with `confidence="medium"` (we never trust the model fully)

This costs tokens but handles arbitrary extraction tasks.

## 9. Error handling & retries

| Layer | What it does |
|---|---|
| Tool implementation | Catches Playwright exceptions, retries idempotent ops once (e.g., a flaky `click`) |
| MCP envelope | If a tool throws, returns `{ isError: true, content: [{text: "..."}] }` — Claude Code sees this and can decide to retry, ask the user, or abort |
| Skill (LLM-driven) | The skill's prompt can instruct Claude to retry differently, fall back to another approach, or surface the error to the user |

We do NOT retry destructive operations automatically. If a `click("Submit")` fails or returns ambiguously, the skill must explicitly re-engage the user.

## 10. Performance characteristics (rough)

| Operation | Latency | LLM tokens (in/out) |
|---|---|---|
| `chrome_attach()` | 50–200 ms | 0 |
| `navigate()` | 500–3000 ms (page load) | 0 |
| `click()` simple | 100–300 ms | 0 (uses cached resolver) |
| `click()` first-time on a page | 300–800 ms | 200 / 50 (vision pass) |
| `read_page()` | 100–500 ms | 0 (returns raw structure) |
| `extract()` fast path | 50–150 ms | 0 |
| `extract()` slow path | 1–3 s | 1500 / 300 |
| Full /powerbi-scan run | 30–60 s | ~3000 / 500 (all in Claude Code's session) |

LLM tokens are billed to the user's Claude Code subscription, not to BrowserMCP.

## 11. Composition: how a skill orchestrates tools

Here's how `/powerbi-scan`'s `SKILL.md` translates to MCP calls under the hood. The skill file says (roughly):

```markdown
1. Attach to Chrome
2. Open a new window
3. Navigate to Power BI
4. Search for the requested report
5. Wait for it to load
6. Read all KPI tiles
7. Return top 5 in a table
```

Claude Code, reading this, generates the sequence of MCP calls. The exact sequence varies run-to-run (different Power BI layouts, etc.) but the skeleton is consistent. This is the **adaptive automation** advantage over hardcoded scripts.

## 12. Where to look in the (forthcoming) code

```
browsermcp/
├── server.py              # main entrypoint, registers tools
├── tools/
│   ├── chrome.py          # chrome_attach, chrome_new_window
│   ├── navigation.py      # navigate, wait_for, scroll
│   ├── interaction.py     # click, type
│   ├── reading.py         # read_page, screenshot
│   └── extraction.py      # extract (fast + slow path)
├── skill_helpers/         # Python helpers usable from SKILL.md
│   ├── powerbi.py         # high-level PowerBI helpers
│   └── jira.py
├── redact.py              # PII redactor for logs
├── logging.py             # JSONL run logger
└── config.py              # ~/.browsermcp/config.toml loader
```

See `docs/testing.md` for how each layer is tested.

---

## 13. Skill frontmatter reference

> All YAML fields a `SKILL.md` file can declare. Both team skills (`team-skills/<name>/SKILL.md`) and personal skills (`~/.claude/skills/<name>/SKILL.md`) use the same schema.

```yaml
---
name: powerbi-scan          # required; matches directory name
description: Scan a Power BI report and return its top KPIs.  # required; one line
arguments:
  - name: report
    type: string            # string | integer | boolean
    required: true
    description: The Power BI report name or URL.
  - name: top_n
    type: integer
    default: 5
    description: How many KPIs to return.
interactive: true           # default true; false = can run unattended (no confirm gates)
max_steps: 30               # default: server cap (50). Set low for tight deterministic skills.
risk: read                  # read | write | destructive
---
```

### Field reference

| Field | Required | Default | Notes |
|---|---|---|---|
| `name` | ✅ | — | Kebab-case; must match directory name |
| `description` | ✅ | — | One sentence; surfaced in `/flows-list` and the slash-command picker |
| `arguments` | — | `[]` | Typed inputs; Claude Code prompts for missing required args before running |
| `interactive` | — | `true` | `false` means no confirm gates, no mid-run questions — required for unattended Phase 4 v2 scheduled runs |
| `max_steps` | — | `50` | Per-run MCP tool call ceiling; server returns error if exceeded |
| `risk` | — | `read` | `write` or `destructive` must ship with dry-run default + explicit confirm step |
| `deprecated` | — | — | `true` triggers warning in `/flows-list`; pair with `deprecation_date` and `replacement` |

### Argument types

- `string` — any text
- `integer` — whole number; Claude Code validates before running the skill
- `boolean` — `true`/`false`; surfaced as a yes/no prompt if required and missing

`required: true` means Claude Code will block and ask the user if the arg isn't provided. `default: <value>` makes it optional. Don't mix both on the same arg.

### The `risk` field and what it requires

- `risk: read` — observe-only. No extra requirements.
- `risk: write` — creates or modifies state (post a comment, fill a form, update a field). Must have a dry-run default and a user-confirmation step before the write fires.
- `risk: destructive` — deletes or takes an irreversible action (close tickets en masse, send email, approve). Same as `write`, plus `interactive: true` is mandatory — destructive skills can never run unattended.

The PR review checklist in `docs/security.md §6` enforces these requirements before merge.

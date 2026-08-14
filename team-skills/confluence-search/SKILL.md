---
name: confluence-search
description: Search internal Confluence (confluence.example.com) by query and return a summary of the top matching pages.
arguments:
  - name: query
    type: string
    required: true
    description: The search query to run against internal Confluence.
  - name: top_n
    type: integer
    default: 5
    description: How many of the top matching pages to summarize.
---

# Confluence Search

You are searching internal corporate Confluence at `confluence.example.com` and returning a summary of the top matching pages to the user. Narrate the work as a teammate would — short progress messages between tool calls so the user knows where you are. Stay read-only: open the search results page, read what's there, and report back. Do not click into individual pages, edit anything, or close the window when you're done.

## Inputs

- `query` — the search query string the user wants to run against Confluence.
- `top_n` — how many results to summarize (defaults to 5 if not provided).

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="confluence-search")`. This is a one-shot, no-side-effect call that tells the BrowserMCP server which Claude Code skill is driving the next batch of tool calls, so the run log under `~/.browsermcp/runs/r-*.jsonl` is attributed correctly (instead of `<ad-hoc>`). Do not narrate this step to the user.

### 1. Attach to the user's Chrome

Say something like: "Attaching to your Chrome session..."

Call `chrome_attach()` with the default port. This connects to the local Chrome that was launched with remote debugging enabled (via `chrome-shim.sh`). If this fails, tell the user they likely need to relaunch Chrome with the shim and stop — do not try to start Chrome yourself.

Note the `pages_open` count from the result so you can mention it ("Connected — found N tabs open").

### 2. Find an existing signed-in Confluence tab — or open a fresh one

Say: "Finding an existing signed-in Confluence tab (or opening a new one)..."

Call `chrome_find_or_open_window(url_pattern="confluence.example.com")` and keep the returned `window_id`. Pass this `window_id` to every subsequent tool call.

**Why find-or-open instead of always-open**: Reusing a tab that's already signed in avoids forcing the user back through the SSO bootstrap. If `chrome_find_or_open_window` returns a brand-new window (no existing tab matched), expect a sign-in prompt in step 4.

### 3. Navigate to the search results page

Say: "Running your Confluence search..."

URL-encode the `query` argument (spaces become `%20`, ampersands become `%26`, etc.) and call:

`navigate(url="https://confluence.example.com/dosearchsite.action?queryString=<URL-encoded query>", window_id=<id>)`

This jumps straight to Confluence's native search results page. `navigate()` enforces the host allowlist, so any drift off `*.example.net` will raise — that's by design.

### 4. Handle sign-in, if shown

After the navigate completes, check the page state. If the user landed on a sign-in page (the title contains "Sign in", "Log in", or similar — Confluence uses Entra ID / corporate SSO), tell them:

"Looks like the agent's Chrome profile isn't signed in to Confluence — open the agent window, complete sign-in, then re-run me."

Then STOP. Do not type credentials yourself.

### 5. Wait for the results to render

Say: "Waiting for the results to load..."

Call `wait_for(condition="search results render", timeout_s=15, window_id=<id>)`. Confluence's search results page loads a list of hits with title, snippet, and metadata; the `wait_for` gives it a beat to populate.

### 6. Read the results page

Say: "Reading the result list..."

Call `read_page(viewport_only=False, window_id=<id>)` so the full result list — including hits below the fold — is captured. Skim the returned `text` and `elements` to confirm the result list is present. If the page text shows a "no results" banner or the list looks empty, surface that honestly in step 8 — do not fabricate hits.

### 7. Identify the top N result entries

From the captured page text and elements, pick out the first `top_n` result entries on the page. For each one, gather:

- **Title** — the link text of the result (the heading of the matching page).
- **Snippet** — the short excerpt Confluence shows under the title (usually a sentence or two with the query terms highlighted).
- **Last updated** — the timestamp or relative date shown on the result row (e.g. "Updated 3 days ago by Jane Doe"). If Confluence doesn't show one for a given hit, use `—`.
- **URL** — the absolute URL the title links to. If only a relative path is visible (e.g. `/display/SPACE/Page+Title`), prepend `https://confluence.example.com`.

If you cannot confidently identify enough entries — for example the page rendered an unfamiliar layout, or the result list is shorter than `top_n` — be honest: return the entries you do have, and note the shortfall.

### 8. Respond to the user

Reply with:

1. A one-line summary: `Top {N} Confluence results for "{query}":` (where N is the actual number you found, which may be fewer than `top_n`).
2. A markdown table with columns: `#`, `Title`, `Snippet`, `Last updated`, `URL`. Number rows starting at 1 — the user will reference these numbers in the follow-up offer below.
3. If the search returned zero hits, skip the table and say so plainly: "Confluence returned no results for that query. Want me to try a different phrasing?"
4. A closing offer on its own line: "Reply with the number to drill into that page (open it, read it, or summarize it), or give me another query to run."

Do not close the window at the end — the user may want to keep exploring or follow up with a drill-in. If they ask to clean up, call `chrome_close_window(window_id=<id>)`.

## Guardrails

- **Read-only.** This skill navigates to the search results page and reads it. Do not click into individual result pages, do not click pagination, do not edit or create anything. If the user asks for a drill-in after step 8, that is a separate follow-up turn.
- **Host allowlist.** Only navigate to `*.example.net` and `*.example.com` domains. `navigate()` enforces this from the BrowserMCP config — any drift will raise.
- **Never type credentials.** SSO is the user's job; you only detect the sign-in page and stop.
- **No fabrication.** If 0 results came back, say so honestly. If the snippet or last-updated field isn't visible for a given hit, use `—` rather than guessing.
- **Fail loud, not thrash.** If `wait_for` times out or `read_page` returns something that doesn't look like a Confluence search result list, surface the problem to the user and stop rather than retrying blindly.

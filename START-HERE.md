# START HERE — BrowserMCP setup

> You just unzipped `BrowserMCP.zip`. This page takes you from zip → working
> `/powerbi-scan` in about 10 minutes. Everything else in `docs/` is background.

**What this is:** an internal MCP server that lets Claude Code drive
*your own* Chrome — Power BI, Jira, Confluence, vendor portals — with no LLM API
key and no loss of your SSO sessions. Claude Code is the brain; this repo is the
hands.

---

## 0. Put the folder in the right place FIRST

Move the unzipped `BrowserMCP` folder to a **non-protected** directory:

```bash
mv ~/Downloads/BrowserMCP ~/code/BrowserMCP     # macOS/Linux
```

```powershell
Move-Item $env:USERPROFILE\Downloads\BrowserMCP C:\bmcp   # Windows
```

Do **not** run it from `~/Downloads`, `~/Desktop`, or `~/Documents`. macOS TCC
protects those three folders, and Claude Code's file tools hit
`Operation not permitted` inside them until you grant Full Disk Access. On
Windows, a short path (`C:\bmcp`) also avoids the 260-char MAX_PATH problem when
the virtualenv is created.

> **Note:** the zip ships **without** `.venv/` — the virtualenv is
> platform-specific and gets rebuilt by the installer in step 2. `.git/` **is**
> included, so `git log`, `git pull`, and branching all work as normal.

---

## 1. Prerequisites

| Need | macOS | Windows |
|---|---|---|
| Claude Desktop | https://claude.ai/download | same |
| Claude Code CLI | `claude --version` works | `claude --version` works |
| git | ships with Xcode CLT | `winget install Git.Git` |
| Python 3.11+ | ships with macOS | installed by `uv` |
| Node.js LTS | optional | required (`winget install OpenJS.NodeJS.LTS`) |
| Google Chrome | installed | installed |
| **Network access to PyPI** | **required** | **required** |

`uv sync` resolves every dependency from PyPI (`pypi.org` and
`files.pythonhosted.org`) and fails if it can't reach them. If your network
needs a proxy or VPN to get there, connect first.

**Optional, but the installer will ask for them** — generate first if you want
the Jira/Confluence/GitHub MCP servers wired up too:

| For | Generate at | Scopes |
|---|---|---|
| GitHub | https://github.com/settings/tokens | `repo` |
| Jira | https://jira.example.com → Profile → Personal Access Tokens | read+write |
| Confluence | https://confluence.example.com → Profile → Personal Access Tokens | read+write |

Press Enter at any PAT prompt to skip it.

---

## 2. Run the installer

**macOS**

```bash
cd ~/code/BrowserMCP
bash team-onboarding/scripts/install.sh
```

**Windows**

```powershell
cd C:\bmcp
powershell -ExecutionPolicy Bypass -File team-onboarding\scripts\install.ps1
```

It is idempotent — safe to re-run any time. In one pass it:

1. installs the GitHub MCP server binary to `~/.local/bin`
2. collects PATs (hidden input; Enter to skip)
3. installs `uv` if missing, then runs `uv sync` to build `.venv/` *(1–2 min)*
4. backs up and updates your `claude_desktop_config.json`
5. installs the Atlassian Claude CLI plugin
6. copies the team skills into `~/.claude/skills/`
7. configures the git credential helper and caches your PAT
8. installs the `bmcp-restart` / `chrome-shim` CLI helpers

Useful flags: `--skip jira,confluence` to leave MCP servers out,
`--team <name>` to also install a team-specific skill set.

**Then fully quit Claude Desktop (`Cmd+Q` / tray → Quit) and relaunch.** Closing
the window is not enough — the MCP config only reloads on a real restart.

---

## 3. Once-per-day: start the agent Chrome

```bash
~/code/BrowserMCP/scripts/chrome-shim.sh        # macOS
```

```powershell
& "$env:USERPROFILE\.local\bin\chrome-shim.cmd"  # Windows
```

This quits any running Chrome and relaunches it with a debugging port on
`127.0.0.1:9222`, which is what BrowserMCP attaches to.

It uses a **dedicated profile** at `~/.browsermcp/chrome-profile` — Chrome 136+
refuses to expose the debugging port on your default profile. Practical
consequence: the agent window starts signed out. In that window, sign in once to
each site you'll use today:

- Power BI — https://app.powerbi.com
- Jira — https://jira.example.com
- Confluence — https://confluence.example.com

Sessions persist for the rest of the day. Tomorrow: relaunch the shim, sign in
again. Your normal Chrome profile stays untouched and private.

---

## 4. Verify it works

```bash
claude mcp list      # expect: browsermcp, github, jira, confluence, filesystem
```

Then in any Claude Code session:

```
/powerbi-scan <paste a Power BI report URL you already have access to>
```

Expected: Claude attaches to Chrome, the agent window navigates to the report,
and you get a table of KPIs plus a screenshot path back in chat.

Other shipped skills: `/confluence-search <query>`,
`/jira-bulk-update <JQL> <change>` (dry-run by default — re-invoke with
`confirm=true` to actually write; hard cap 50 tickets), `/flows-list`,
`/save-as-flow <name>`, `/promote-flow <name>`.

---

## 5. Make it do *your* job

Describe a task in plain English in chat, let Claude do it with the browser
primitives, then:

```
/save-as-flow weekly-shrink-top10
```

It's now `/weekly-shrink-top10` in your slash menu forever. Personal flows live
in `~/.claude/skills/<name>/` and belong to you, not the team repo. To share one
with the team, run `/promote-flow <name>` (opens a PR) or email the `SKILL.md`
to @isunilsharma on GitHub.

---

## 6. Developing on the repo

```bash
uv sync --extra dev      # dev tools (pytest, ruff, mypy)
uv run pytest            # unit tests only (integration/e2e are opt-in)
uv run pytest -m integration   # needs a running Chrome
uv run ruff check .      # lint, line length 100
uv sync --extra web && uv run streamlit run web/app.py   # dashboard
```

Read `CLAUDE.md` before changing code — it has the conventions, the
security rules around chrome-attach, and the dry-run requirement for any tool
that writes.

After editing server code, fully restart Claude Desktop. Hot-reload
(`BROWSERMCP_WATCH=1`) ships **disabled** on purpose: the `os.execv` re-exec
keeps the stdio pipe but never redoes the MCP `initialize` handshake, so every
subsequent tool call fails with `-32602` until you reconnect the server.

---

## 7. When it breaks

| Symptom | Fix |
|---|---|
| `chrome_attach failed: ECONNREFUSED 127.0.0.1:9222` | The agent Chrome isn't running — re-run `chrome-shim.sh`. |
| `Looks like the agent's Chrome profile isn't signed in` | Flip to the agent Chrome window, complete SSO, re-run. |
| `uv sync failed` | Can't reach PyPI. Check that `pypi.org` and `files.pythonhosted.org` resolve (proxy/VPN if your network needs one), then re-run. |
| `host not allowed: <domain>` | Guardrail — domain isn't on the corporate allowlist. Ask Sunil to add it. |
| `confirmation_required` on a write | By design. Re-invoke with `confirm=true`, or tell Claude "yes, proceed". |
| Agent window won't open | Another Chrome is locking the profile dir. Quit all Chrome (`Cmd-Q`), re-run the shim. |
| `/foo` not in the slash menu | Re-run `team-onboarding/scripts/install.sh`. |
| GitHub MCP tools return 403 | Known — corporate proxy vs. the Go server's HEAD requests. Use plain `git`/`curl` from inside Claude Code instead; your PAT is in Keychain. |
| Moved the repo after installing | Re-run the installer to refresh the launcher symlink/shim. |

Every tool call is logged locally to `~/.browsermcp/runs/r-<id>.jsonl` with PII
redacted. Nothing leaves your machine.

---

## Where to read next

1. `docs/getting-started.md` — the fuller version of this page
2. `docs/userflow.md` — what teammates actually experience
3. `docs/design.md` — what we're building and why
4. `docs/techflow.md` — MCP wire calls and the full tool reference
5. `docs/security.md` — threat model and IT review checklist
6. `team-onboarding/MANUAL.md` — do the install by hand (macOS + Windows)
7. `team-skills/powerbi-scan/SKILL.md` — gold-standard example to copy

**Maintainer:** Sunil Sharma — @isunilsharma on GitHub
**Repo:** https://github.com/isunilsharma/BrowserMCP

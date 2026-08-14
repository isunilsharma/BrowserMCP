# Team Claude Code Onboarding

> Give your teammates the same MCP toolkit Sunil uses, with one command.

This folder ships a **Claude Code skill** that installs and configures everything you need to use Claude Desktop + Claude Code effectively on the team:

| Tool | What it lets Claude do |
|---|---|
| **GitHub MCP (Enterprise)** | Read/search code, create issues, open PRs against `github.com` |
| **Jira MCP** | Search Jira tickets, create issues, post comments against `jira.example.com` |
| **Confluence MCP** | Search and read pages from `confluence.example.com` |
| **Filesystem MCP** | Read/write files in the user's home directory |
| **Atlassian plugin** (Claude CLI skills) | `/atlassian:spec-to-backlog`, `/atlassian:triage-issue`, etc. |
| **Git PAT cached in macOS Keychain** | Future `git push/pull` works without prompts |

---

## Quick install

<details>
<summary><strong>macOS</strong></summary>

```bash
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP
bash team-onboarding/scripts/install.sh
```

Optional flags: `--skip jira,confluence`, `--team produce`.
</details>

<details>
<summary><strong>Windows</strong></summary>

```powershell
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP
powershell -ExecutionPolicy Bypass -File team-onboarding\scripts\install.ps1
```

Optional flags: `-Skip jira,confluence`, `-Team produce`. PowerShell 5.1+ (ships with Windows 10/11). No admin rights required — shims land in `%USERPROFILE%\.local\bin`.
</details>

After the installer finishes, fully quit Claude Desktop (`Cmd+Q` on macOS, tray-icon → Quit on Windows) and relaunch.

---

## Two ways to use this

### Option A — Run the Claude Code skill (recommended)

Drop this folder into your `~/.claude/skills/setup-team-tools/` and ask Claude Code:

```
/setup-team-tools
```

Claude walks you through everything interactively — asks for the PATs it needs, installs binaries, edits configs, tests each MCP.

### Option B — Read [`MANUAL.md`](./MANUAL.md) and do it yourself

If you'd rather not run a skill, the same steps are documented step by step in `MANUAL.md`.

---

## What gets installed where

```
~/.local/bin/github-mcp-server               ← Go binary (v1.4.0) for GitHub

~/Library/Application Support/Claude/claude_desktop_config.json
   └─ mcpServers:
        ├─ github          (uses github-mcp-server binary)
        ├─ jira            (npx @atlassian-dc-mcp/jira)
        ├─ confluence      (npx @atlassian-dc-mcp/confluence)
        └─ filesystem      (npx @modelcontextprotocol/server-filesystem ~)

~/.claude/plugins/atlassian@claude-plugins-official    ← Claude CLI plugin
~/.config/git → credential.helper = osxkeychain        ← PAT auto-cached
macOS Keychain: github.com PAT              ← so git push just works
```

---

## What you need before running

You'll need three Personal Access Tokens (PATs). Get them ready:

| For | Generate at | Scopes needed |
|---|---|---|
| **GitHub** | https://github.com/settings/tokens | `repo` (full) |
| **Jira (Atlassian DC)** | https://jira.example.com/secure/ViewProfile.jspa → Personal Access Tokens | full read+write |
| **Confluence (Atlassian DC)** | https://confluence.example.com/users/viewmyprofile.action → Personal Access Tokens | full read+write |

You don't need all three at once — the skill skips ones you don't have a token for and you can add them later.

---

## Files in this folder

```
team-onboarding/
├── README.md                                ← you are here
├── MANUAL.md                                ← step-by-step manual install
├── SKILL.md                                 ← the Claude Code skill body
├── claude_desktop_config.template.json      ← template MCP config
└── scripts/
    └── install.sh                           ← bash installer (idempotent)
```

---

## Sharing with a teammate

Easiest path:

```bash
# Teammate clones the BrowserMCP repo
git clone https://github.com/isunilsharma/BrowserMCP.git
cd BrowserMCP/team-onboarding

# Install the skill into their Claude Code skills folder
mkdir -p ~/.claude/skills/setup-team-tools
cp SKILL.md scripts/install.sh claude_desktop_config.template.json ~/.claude/skills/setup-team-tools/

# Run it
# (in Claude Code Desktop)
/setup-team-tools
```

Or just point them at this folder's `MANUAL.md` and they walk through it themselves.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `github-mcp-server: command not found` after install | Path not refreshed | New terminal window, or `source ~/.zshrc` |
| MCP server returns 403 on tool calls | Corporate proxy choking on HEAD requests | Known issue. Use plain `git`/`curl` via Bash; the underlying API works |
| `git push` prompts for password every time | osxkeychain helper not configured | `git config --global credential.helper osxkeychain` |
| Claude Desktop doesn't see the new MCP | App not fully quit | `Cmd+Q` (not just close window), relaunch |

For anything else, message Sunil (@isunilsharma on GitHub).

---
name: setup-team-tools
description: Install and configure all the corporate MCP servers (GitHub, Jira, Confluence, filesystem) and the Atlassian Claude CLI plugin. Use when a teammate wants to bring their Claude Code / Claude Desktop setup in line with the team's standard toolkit.
arguments:
  - name: skip
    type: string
    required: false
    description: Comma-separated list of MCP servers to skip (e.g., "jira,confluence" if the teammate already has them set up)
---

# Setup Team Tools

When invoked, walk the user through installing and configuring their Claude Code + Claude Desktop environment to match the team standard.

## What you'll install

1. **`github-mcp-server`** v1.4.0 binary at `~/.local/bin/` (Go-based MCP for GitHub)
2. **MCP entries in `claude_desktop_config.json`** for: github, jira, confluence, filesystem
3. **Atlassian plugin** via `claude plugin install`
4. **macOS Keychain credential helper** so `git push` to internal GH stops prompting

## Step-by-step

### Step 1 — Check what's already installed

Run these and tell the user what you found:

```bash
# Binary
ls ~/.local/bin/github-mcp-server 2>/dev/null && echo "✓ github-mcp-server installed" || echo "✗ missing"

# Config
[ -f "$HOME/Library/Application Support/Claude/claude_desktop_config.json" ] && echo "✓ Claude Desktop config exists" || echo "✗ missing"

# Plugin
claude plugin list 2>&1 | grep -q atlassian && echo "✓ atlassian plugin" || echo "✗ missing"

# Credential helper
git config --global credential.helper | grep -q osxkeychain && echo "✓ keychain helper" || echo "✗ missing"
```

### Step 2 — Collect the PATs needed (only ones the user has)

Ask the user which of these they want to set up. They can skip any:

- **GitHub** PAT — get at https://github.com/settings/tokens (needs `repo` scope)
- **Jira (Atlassian DC)** PAT — get at https://jira.example.com → Profile → Personal Access Tokens
- **Confluence (Atlassian DC)** PAT — get at https://confluence.example.com → Profile → Personal Access Tokens

If the user passes `skip=jira,confluence` in the slash command, skip those.

**Do NOT echo PATs back to the user or include them in any log message.** Read them into shell variables only.

### Step 3 — Install the GitHub MCP server binary

If `~/.local/bin/github-mcp-server` doesn't exist:

```bash
mkdir -p ~/.local/bin
cd /tmp

# Detect architecture
ARCH=$(uname -m)
[ "$ARCH" = "arm64" ] && SUFFIX="Darwin_arm64" || SUFFIX="Darwin_x86_64"

# Download latest release
ASSET_URL=$(curl -s https://api.github.com/repos/github/github-mcp-server/releases/latest \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(a['browser_download_url']) for a in d['assets'] if '$SUFFIX' in a['name']]")

curl -L -o github-mcp-server.tar.gz "$ASSET_URL"
tar -xzf github-mcp-server.tar.gz
mv github-mcp-server ~/.local/bin/
chmod +x ~/.local/bin/github-mcp-server
~/.local/bin/github-mcp-server --version
```

### Step 4 — Generate `claude_desktop_config.json`

Read the template at `claude_desktop_config.template.json` (next to this SKILL.md). Substitute the PATs the user provided. **Preserve** any non-team MCP servers the user already has in their config (merge, don't overwrite).

Back up the existing config first:

```bash
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
[ -f "$CFG" ] && cp "$CFG" "$CFG.bak.$(date +%Y%m%d-%H%M%S)"
```

Then write the merged config via a Python script (so JSON stays valid):

```python
import json, os
cfg_path = os.path.expanduser('~/Library/Application Support/Claude/claude_desktop_config.json')
template_path = os.path.expanduser('~/.claude/skills/setup-team-tools/claude_desktop_config.template.json')

# Load existing or start fresh
try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {"mcpServers": {}}

with open(template_path) as f:
    template = json.load(f)

# Substitute PATs and merge
for name, server_cfg in template['mcpServers'].items():
    if name in user_skipped_servers:
        continue
    # Substitute {{GITHUB_PAT}}, {{JIRA_PAT}}, {{CONFLUENCE_PAT}}
    # with values the user provided
    ...
    cfg['mcpServers'][name] = server_cfg

with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
```

### Step 5 — Install the Atlassian Claude CLI plugin

```bash
claude plugin install atlassian@claude-plugins-official
```

### Step 6 — Configure git credential helper + cache GitHub PAT

```bash
git config --global credential.helper osxkeychain

# Cache the GitHub PAT (if user provided it)
printf "protocol=https\nhost=github.com\nusername=%s\npassword=%s\n" \
  "<USERNAME>" "<GITHUB_PAT>" \
  | git credential-osxkeychain store
```

Replace `<USERNAME>` with the user's GitHub username and `<GITHUB_PAT>` with the value they provided. **Do not print these.**

### Step 7 — Summary & restart

Tell the user:

1. ✅ What got installed
2. ✅ What was already set up
3. ⚠️ They need to **quit Claude Desktop fully (Cmd+Q)** and relaunch before the MCP changes take effect

### Step 8 — Verify (optional, after they restart)

If they come back and say they've restarted, try a smoke test:
- For each new MCP server, attempt one read-only tool call
- Report success/failure
- If anything fails, point them to `team-onboarding/README.md` troubleshooting section

## Guardrails

- ⚠️ **Never log, print, or echo any PAT value.** Read them into shell vars only.
- ⚠️ **Always back up the existing `claude_desktop_config.json`** before modifying it.
- ⚠️ **Preserve other MCP servers** the user has — only add/update the ones in the template.
- ⚠️ If `github-mcp-server` is already installed and is a newer version than the template's pin, leave it alone.
- ⚠️ Test the GitHub PAT against `https://api.github.com/user` with a single curl before caching it — fail fast if it returns anything other than 200.

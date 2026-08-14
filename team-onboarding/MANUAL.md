# Manual install (no skill needed)

> Same outcome as `/setup-team-tools`, just done by hand. ~10 minutes.

## Prereqs

- macOS (Intel or Apple Silicon)
- Claude Desktop installed (https://claude.ai/download)
- Claude Code CLI installed (`claude` command available)
- `git` installed (comes with Xcode CLT)
- `python3` installed (comes with macOS)

## What you'll need ready

Generate these PATs in your browser first. You can skip any you don't want:

| For | Generate at | Scopes |
|---|---|---|
| GitHub | https://github.com/settings/tokens | `repo` |
| Jira | https://jira.example.com → Profile → Personal Access Tokens | full read+write |
| Confluence | https://confluence.example.com → Profile → Personal Access Tokens | full read+write |

---

## Step 1 — Install the GitHub MCP server binary

```bash
mkdir -p ~/.local/bin
cd /tmp

# Detect your Mac's architecture
ARCH=$(uname -m)
[ "$ARCH" = "arm64" ] && SUFFIX="Darwin_arm64" || SUFFIX="Darwin_x86_64"

# Get the latest release URL
ASSET_URL=$(curl -s https://api.github.com/repos/github/github-mcp-server/releases/latest \
  | python3 -c "import json,sys; d=json.load(sys.stdin); [print(a['browser_download_url']) for a in d['assets'] if '$SUFFIX' in a['name']]")

# Download & install
curl -L -o github-mcp-server.tar.gz "$ASSET_URL"
tar -xzf github-mcp-server.tar.gz
mv github-mcp-server ~/.local/bin/
chmod +x ~/.local/bin/github-mcp-server

# Verify
~/.local/bin/github-mcp-server --version
```

Make sure `~/.local/bin` is on your PATH (it usually is on macOS — check with `echo $PATH`). If not, add this to `~/.zshrc`:
```bash
export PATH="$HOME/.local/bin:$PATH"
```

---

## Step 2 — Configure Claude Desktop MCP servers

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add the `mcpServers` block. The full template is in [`claude_desktop_config.template.json`](./claude_desktop_config.template.json) — copy it and replace the `{{...}}` placeholders.

**Back up first** (especially if you already have MCP servers configured — you'll want to merge, not replace):

```bash
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
cp "$CFG" "$CFG.bak.$(date +%Y%m%d-%H%M%S)"
```

Then replace the placeholders in the template:
- `{{HOME}}` → your home dir (e.g., `/Users/jdoe`)
- `{{GITHUB_PAT}}` → your GitHub PAT
- `{{JIRA_PAT}}` → your Jira PAT
- `{{CONFLUENCE_PAT}}` → your Confluence PAT

If you don't have one of the PATs, **remove that whole `"jira": {...}` / `"confluence": {...}` block** from the config instead of leaving the placeholder.

---

## Step 3 — Install the Atlassian Claude CLI plugin

```bash
claude plugin install atlassian@claude-plugins-official
```

Verify with `claude plugin list` — you should see `atlassian@claude-plugins-official ✔ enabled`.

---

## Step 4 — Configure git credential helper

```bash
git config --global credential.helper osxkeychain
```

Now cache your GitHub PAT so future `git push` won't prompt:

```bash
# Replace YOUR_USERNAME with your GitHub username (e.g., isunilsharma)
# Replace YOUR_GITHUB_PAT with your PAT
printf "protocol=https\nhost=github.com\nusername=YOUR_USERNAME\npassword=YOUR_GITHUB_PAT\n" \
  | git credential-osxkeychain store

echo "✓ PAT cached"
```

Test it:
```bash
git ls-remote https://github.com/isunilsharma/BrowserMCP.git | head -2
```
Should print the repo's refs without prompting for credentials.

---

## Step 5 — Restart Claude Desktop

`Cmd+Q` to fully quit (not just close the window), then relaunch.

---

## Step 6 — Verify

Open Claude Desktop and try:

| Test | Expected |
|---|---|
| Ask: *"List my GitHub repos"* | A list (via the github MCP) |
| Ask: *"Search Jira for tickets assigned to me"* | A list of Jira issues |
| Ask: *"Find Confluence pages about X"* | Search results |

If any MCP fails:
1. Check the MCP server logs at `~/Library/Logs/Claude/`
2. Verify the PAT is valid: `curl -H "Authorization: Bearer $YOUR_PAT" https://api.github.com/user`
3. See the README's troubleshooting table

---

## Known issues

### GitHub MCP returns 403 on tool calls

The corporate proxy in front of `github.com` doesn't handle the Go MCP server's HEAD requests cleanly. Tool calls (`get_me`, `list_branches`, etc.) currently fail.

**Workaround:** Use plain `git` + `curl` commands from inside Claude Code. Your PAT is cached in Keychain, so they Just Work. This is being tracked upstream at [`github/github-mcp-server`](https://github.com/github/github-mcp-server).

### Atlassian plugin "needs authentication"

After install, run any `/atlassian:*` command — Claude Code will prompt you to authenticate via browser (OAuth flow against `mcp.atlassian.com`). One-time.

### Moving the BrowserMCP repo after install

The Claude Desktop config points at `~/.local/bin/browsermcp-launcher`, which is a symlink to `<your-repo>/scripts/launch-browsermcp.sh`. The launcher resolves the repo from its own real path at runtime.

If you move the repo, re-run `bash team-onboarding/scripts/install.sh` — it'll refresh the symlink to the new location. No config edit needed.

### Dev hot-reload (`BROWSERMCP_WATCH`) — off by default

`BROWSERMCP_WATCH=1` starts a watcher thread that re-execs the server via `os.execv` on any `.py` change. **It ships disabled (`"0"`) because the re-exec breaks the live MCP session:** `os.execv` preserves the stdio pipe but the fresh process never re-runs the MCP `initialize` handshake, so Claude Code's already-negotiated session goes stale and every subsequent tool call fails with `-32602: Invalid request parameters` until you reconnect the server. (Some corporate EDR tools also score the self-replacing-process pattern as suspicious.)

If you're actively editing server code and want hot-reload anyway, set `BROWSERMCP_WATCH=1` in the `env` block of the `browsermcp` entry in `~/Library/Application Support/Claude/claude_desktop_config.json` — but be aware that after each reload you must **reconnect the server** (`/mcp` → browsermcp → Reconnect) for tools to work again. With the flag off (the default), just fully restart Claude Desktop after a code change. `bmcp-restart` only does anything when the flag is on.

---

## Windows manual install

> Parallel to the macOS steps above, for Windows 10/11. ~10–15 minutes. The scripted path (`powershell -ExecutionPolicy Bypass -File team-onboarding\scripts\install.ps1`) does all of this automatically — only follow these steps if you'd rather do it by hand.

### Prereqs (Windows)

- Windows 10 1607+ or Windows 11 (LongPathsEnabled recommended — see Pitfalls below)
- Claude Desktop for Windows installed (https://claude.ai/download)
- Claude Code CLI on PATH (`claude --version` works in a new terminal)
- Git for Windows (`winget install Git.Git`)
- Node.js LTS (`winget install OpenJS.NodeJS.LTS`) — required for the `npx`-based Jira/Confluence/Filesystem MCP servers
- `uv` for the Python venv (the scripted installer auto-installs this; only needed for manual installs): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

### Step 1 — GitHub MCP server binary

```powershell
$Bin = "$env:USERPROFILE\.local\bin"
New-Item -ItemType Directory -Path $Bin -Force | Out-Null
# Download the Windows asset for github-mcp-server v1.4.0 (adjust SUFFIX if on ARM64):
$Url = "https://github.com/github/github-mcp-server/releases/download/v1.4.0/github-mcp-server_Windows_x86_64.zip"
Invoke-WebRequest -Uri $Url -OutFile "$env:TEMP\gh-mcp.zip"
Unblock-File "$env:TEMP\gh-mcp.zip"   # clear Defender SmartScreen mark-of-the-web
Expand-Archive "$env:TEMP\gh-mcp.zip" -DestinationPath $Bin -Force
& "$Bin\github-mcp-server.exe" --version
```

### Step 2 — Create the BrowserMCP Python venv

From the cloned repo root:

```powershell
cd <path-to>\BrowserMCP
uv sync
# Should produce .venv\Scripts\python.exe
```

### Step 3 — Install the launcher / restart / chrome shims

Copy the three `.cmd` shims from `scripts\` into `%USERPROFILE%\.local\bin`:

```powershell
$Bin = "$env:USERPROFILE\.local\bin"
Copy-Item scripts\launch-browsermcp.cmd "$Bin\browsermcp-launcher.cmd" -Force
Copy-Item scripts\bmcp-restart.cmd      "$Bin\bmcp-restart.cmd"        -Force
Copy-Item scripts\chrome-shim.cmd       "$Bin\chrome-shim.cmd"         -Force
```

Add `%USERPROFILE%\.local\bin` to your **user** PATH (no admin needed):

```powershell
setx PATH "$env:USERPROFILE\.local\bin;$env:PATH"
```

Open a new terminal so the PATH update takes effect.

### Step 4 — Configure Claude Desktop MCP servers

Edit `%APPDATA%\Claude\claude_desktop_config.json` (typically `C:\Users\<user>\AppData\Roaming\Claude\claude_desktop_config.json`). Back it up first:

```powershell
$Cfg = "$env:APPDATA\Claude\claude_desktop_config.json"
Copy-Item $Cfg "$Cfg.bak.$(Get-Date -Format yyyyMMdd-HHmmss)" -Force
```

Open `team-onboarding\claude_desktop_config.template.json` and replace placeholders. **Use forward slashes** in paths (a single backslash in JSON is an escape character — easy to silently break the config):

- `{{HOME}}` → `C:/Users/<you>`
- `{{LAUNCHER_PATH}}` → `C:/Users/<you>/.local/bin/browsermcp-launcher.cmd`
- `{{GITHUB_PAT}}` / `{{JIRA_PAT}}` / `{{CONFLUENCE_PAT}}` → your PATs (or delete that whole server block if you don't have one)

Note: Claude Desktop does **not** expand `%USERPROFILE%` or `${HOME}` inside the JSON — you must materialize fully absolute paths.

### Step 5 — Atlassian plugin

```powershell
claude plugin install atlassian@claude-plugins-official
claude plugin list   # expect: atlassian@claude-plugins-official ✔ enabled
```

### Step 6 — Git credential helper

```powershell
git config --global credential.helper manager
```

Then on first `git push` to `github.com`, Git Credential Manager will pop a browser to cache your PAT.

### Step 7 — Restart Chrome with the debugging port

Use the installed shim (it kills lingering Chrome instances and relaunches with `--remote-debugging-port` against the `%USERPROFILE%\.browsermcp\chrome-profile` user-data-dir):

```powershell
& "$env:USERPROFILE\.local\bin\chrome-shim.cmd"
```

### Step 8 — Restart Claude Desktop and verify

Right-click the Claude Desktop tray icon → Quit (or `Ctrl+Q`), relaunch, then in a new terminal:

```powershell
claude mcp list
```

You should see `browsermcp`, `github`, `jira`, `confluence`, `filesystem` (minus any you skipped).

### Windows-specific pitfalls

- **JSON backslashes:** prefer forward slashes in `claude_desktop_config.json`. `"C:\Users\..."` is invalid JSON; `"C:\\Users\\..."` works; `"C:/Users/..."` is simpler and Windows APIs accept it.
- **Spaces in profile paths** (`C:\Users\First Last\...`) require every `.cmd` variable expansion to be quoted. The shipped shims already do this; hand-written ones often don't.
- **PowerShell execution policy:** always invoke installers with `-ExecutionPolicy Bypass`, otherwise unsigned `.ps1` files fail silently with a red banner.
- **MAX_PATH 260-char limit:** deeply nested `.venv\Lib\site-packages\...` can exceed 260 chars. Enable LongPathsEnabled (`reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f`, requires admin) or clone the repo to a short path like `C:\bmcp`.
- **Defender SmartScreen / corporate EDR:** downloaded `.exe` and `.zip` files carry a mark-of-the-web — run `Unblock-File` on them. Corporate-managed laptops may need an exception filed for the BrowserMCP repo path.
- **Chrome on Windows:** `taskkill /IM chrome.exe /F` before relaunching with `--remote-debugging-port`. Chrome 136+ still refuses the default user-data-dir — use `%USERPROFILE%\.browsermcp\chrome-profile`.
- **Moving the repo after install:** the generated launcher `.cmd` shim hardcodes the absolute repo root at install time (no symlink resolution like the macOS version). If you move the repo, re-run `install.ps1` to regenerate the shim.
- **Line endings:** if you edit the repo on Windows, ensure `.gitattributes` keeps shell scripts at LF — `core.autocrlf=true` will inject CRLF into `chrome-shim.cmd` companion bash helpers and break them. The `.cmd` files themselves should stay CRLF.

<#
.SYNOPSIS
  install.ps1 — Windows installer for the team Claude Code MCP toolkit.

.DESCRIPTION
  Mirrors install.sh (macOS) for Windows. Idempotent — re-run any time. Reads
  GITHUB_PAT / JIRA_PAT / CONFLUENCE_PAT from env vars (preferred) or prompts
  silently. Writes %APPDATA%\Claude\claude_desktop_config.json with fully
  materialized absolute paths.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File install.ps1
  powershell -ExecutionPolicy Bypass -File install.ps1 -Skip jira,confluence
  powershell -ExecutionPolicy Bypass -File install.ps1 -Team produce

.NOTES
  PowerShell 5.1+ (ships with Windows 10/11). Does NOT require pwsh 7.
#>

[CmdletBinding()]
param(
  [string[]] $Skip = @(),
  [string]   $Team = ''
)

Set-StrictMode -Version 3.0
$ErrorActionPreference = 'Stop'

# ─── pretty printing ─────────────────────────────────────────────
function Write-Section($msg) { Write-Host ""; Write-Host "━━━ $msg ━━━" -ForegroundColor Cyan }
function Write-Ok($msg)      { Write-Host "✓ $msg" -ForegroundColor Green }
function Write-Warn2($msg)   { Write-Host "⚠ $msg" -ForegroundColor Yellow }
function Write-Info($msg)    { Write-Host $msg -ForegroundColor Yellow }
function Write-Err2($msg)    { Write-Host "✗ $msg" -ForegroundColor Red }

function Test-Skip([string]$name) { return ($Skip -contains $name.ToLower()) }

# Validate --team is kebab-case (matches install.sh).
if ($Team -ne '') {
  if ($Team -notmatch '^[a-z0-9]+(-[a-z0-9]+)*$') {
    Write-Err2 "--team must be kebab-case (lowercase letters, digits, hyphens); got: '$Team'"
    exit 1
  }
}

# Resolve repo paths from this script's location: <repo>/team-onboarding/scripts/install.ps1
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OnboardingRoot = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $OnboardingRoot

# ─── Step 0 / Prereqs ────────────────────────────────────────────
Write-Section "Checking prerequisites"

function Test-Cmd([string]$name) {
  return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

if (-not (Test-Cmd 'uv')) {
  Write-Info "uv not found — installing via astral.sh..."
  try {
    Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression
  } catch {
    Write-Err2 "uv install failed: $($_.Exception.Message)"
    Write-Err2 'Try manually: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
    exit 1
  }
  # The uv installer adds %USERPROFILE%\.local\bin or %USERPROFILE%\.cargo\bin to PATH
  # in the user environment, but the current PowerShell session won't see it until
  # restart. Prepend manually so the rest of this script can call uv.
  $env:PATH = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.cargo\bin;$env:PATH"
  if (-not (Test-Cmd 'uv')) {
    Write-Err2 "uv installed but not callable in this session. Open a NEW terminal and re-run this installer."
    exit 1
  }
  Write-Ok "uv installed: $((& uv --version) 2>&1)"
} else {
  Write-Ok "uv"
}

if (-not (Test-Cmd 'git')) {
  Write-Warn2 "git not found on PATH — credential-helper step will be skipped. Install Git for Windows: https://git-scm.com/download/win"
} else {
  Write-Ok "git"
}

if (-not (Test-Cmd 'node')) {
  Write-Warn2 "node not found — npx-based MCP servers (jira/confluence/filesystem) will fail to launch."
  Write-Warn2 "Install Node LTS:  winget install OpenJS.NodeJS.LTS"
}

$HasClaude = Test-Cmd 'claude'
if ($HasClaude) { Write-Ok "claude CLI" } else { Write-Warn2 "claude CLI not on PATH — Atlassian plugin step will be skipped." }

# ─── Step 1 / github-mcp-server binary ──────────────────────────
Write-Section "Step 1 / GitHub MCP server binary"
$GhMcpBinDir = Join-Path $env:USERPROFILE '.local\bin'
New-Item -ItemType Directory -Path $GhMcpBinDir -Force | Out-Null
$GhMcpExe = Join-Path $GhMcpBinDir 'github-mcp-server.exe'
if (Test-Path $GhMcpExe) {
  Write-Ok "Already installed: $GhMcpExe"
} else {
  # PIN: match install.sh's GHMCP_VERSION. Bump in both places when upgrading.
  $GhMcpVersion = 'v1.4.0'
  $arch = if ([Environment]::Is64BitOperatingSystem) {
    if ((Get-CimInstance Win32_Processor).Architecture -eq 12) { 'arm64' } else { 'x86_64' }
  } else { 'i386' }
  $assetName = "github-mcp-server_Windows_$arch.zip"
  $assetUrl  = "https://github.com/github/github-mcp-server/releases/download/$GhMcpVersion/$assetName"
  Write-Info "Downloading github-mcp-server $GhMcpVersion ($arch)..."
  $tmpZip = Join-Path $env:TEMP "gh-mcp-$([guid]::NewGuid().Guid.Substring(0,8)).zip"
  try {
    Invoke-WebRequest -Uri $assetUrl -OutFile $tmpZip -UseBasicParsing -ErrorAction Stop
  } catch {
    Write-Err2 "Failed to download $assetUrl"
    Write-Err2 "Check network / bump `$GhMcpVersion in install.ps1 if the asset moved."
    exit 1
  }
  # Clear Defender SmartScreen "mark-of-the-web" so the unzipped .exe runs without warning.
  try { Unblock-File $tmpZip } catch { }
  Expand-Archive -Path $tmpZip -DestinationPath $GhMcpBinDir -Force
  Remove-Item $tmpZip -Force
  if (-not (Test-Path $GhMcpExe)) {
    Write-Err2 "Extract finished but $GhMcpExe is missing. The release asset may have a different layout."
    exit 1
  }
  try { Unblock-File $GhMcpExe } catch { }
  Write-Ok "Installed: $GhMcpExe"
}

# ─── Step 2 / PATs ───────────────────────────────────────────────
Write-Section "Step 2 / Collect PATs"
# Prefer env vars (CI / non-interactive). Otherwise prompt securely.
function Read-Pat([string]$label, [string]$envName) {
  $v = [Environment]::GetEnvironmentVariable($envName)
  if ($v) { Write-Info "  using $envName from environment"; return $v }
  $sec = Read-Host -Prompt "$label (or Enter to skip)" -AsSecureString
  $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
  try   { return [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr) }
  finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

$GithubPat     = Read-Pat "GitHub PAT" "GITHUB_PAT"
$JiraPat       = Read-Pat "Jira PAT"              "JIRA_PAT"
$ConfluencePat = Read-Pat "Confluence PAT"        "CONFLUENCE_PAT"

if ($GithubPat) {
  Write-Info "Testing GitHub PAT..."
  try {
    $resp = Invoke-WebRequest -Uri 'https://api.github.com/user' `
              -Headers @{ Authorization = "Bearer $GithubPat" } `
              -UseBasicParsing -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { Write-Ok "GitHub PAT valid" }
    else { Write-Err2 "GitHub PAT returned HTTP $($resp.StatusCode) — aborting"; exit 1 }
  } catch {
    Write-Err2 "GitHub PAT validation failed: $($_.Exception.Message)"
    exit 1
  }
}

# ─── Step 2b / uv sync ──────────────────────────────────────────
Write-Section "Step 2b / BrowserMCP Python environment"
$VenvPython = Join-Path $RepoRoot '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
  Write-Ok "venv already present at $RepoRoot\.venv"
} else {
  Write-Info "Creating venv via uv sync (1–2 min first run)..."
  Push-Location $RepoRoot
  try {
    & uv sync
    if ($LASTEXITCODE -ne 0) { Write-Err2 "uv sync failed (exit $LASTEXITCODE). Check VPN and re-run."; exit 1 }
  } finally { Pop-Location }
  Write-Ok "venv ready at $RepoRoot\.venv"
}

# ─── Step 6 (early) / CLI helpers — build launcher first so config can point at it ───
Write-Section "Step 6 / BrowserMCP CLI helpers"
$BinDir = Join-Path $env:USERPROFILE '.local\bin'
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

# Source shims live in the repo. If they're missing we still create a minimal
# launcher.cmd that boots the venv python against browsermcp.server.
$LauncherSrc  = Join-Path $RepoRoot 'scripts\launch-browsermcp.cmd'
$RestartSrc   = Join-Path $RepoRoot 'scripts\bmcp-restart.cmd'
$ChromeShim   = Join-Path $RepoRoot 'scripts\chrome-shim.cmd'

$LauncherDst  = Join-Path $BinDir 'browsermcp-launcher.cmd'
$RestartDst   = Join-Path $BinDir 'bmcp-restart.cmd'
$ChromeDst    = Join-Path $BinDir 'chrome-shim.cmd'

function Install-Shim([string]$src, [string]$dst, [string]$generated) {
  # For launcher + bmcp-restart we ALWAYS write a generated shim with the absolute
  # repo path baked in. Reason: the source .cmd in scripts/ uses %~dp0 self-
  # resolution to find the repo root, which works when invoked from inside the
  # repo but BREAKS after copying into ~/.local/bin (%~dp0 then points at the
  # shim dir, not the repo). Generated shims avoid that trap.
  # For chrome-shim and similar that don't need repo-path resolution, the caller
  # passes a $null generated string and we just copy the source verbatim.
  if ($generated) {
    Set-Content -Path $dst -Value $generated -Encoding ASCII
    Write-Ok "Installed (generated): $dst"
  } elseif (Test-Path $src) {
    Copy-Item -Path $src -Destination $dst -Force
    Write-Ok "Installed (copied):    $dst"
  } else {
    Write-Warn2 "(skipped — source missing: $src)"
  }
}

# Launcher and bmcp-restart get generated shims with absolute paths baked in.
# Why generated: the source .cmd files use %~dp0 self-resolution which breaks
# when copied to a different directory. Baking the absolute repo path here
# avoids that whole class of bug.
$LauncherFallback = @"
@echo off
REM Auto-generated by install.ps1 — DO NOT EDIT. Re-run install.ps1 if the repo moves.
REM Launches BrowserMCP via the repo venv. Forwards exit code so Claude Desktop
REM sees the right errorlevel on server crash.
setlocal
set "REPO=$RepoRoot"
set "VENV_PY=%REPO%\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo browsermcp-launcher: venv missing at "%VENV_PY%" 1>&2
  echo Run: cd /d "%REPO%" ^&^& uv sync 1>&2
  endlocal & exit /b 1
)
set "PYTHONPATH=%REPO%"
"%VENV_PY%" -m browsermcp.server %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%
"@

$RestartFallback = @"
@echo off
REM Auto-generated by install.ps1 — DO NOT EDIT. Re-run install.ps1 if the repo moves.
REM Touches browsermcp\state.py so the in-server file-watcher re-execs.
setlocal
set "TARGET=$RepoRoot\browsermcp\state.py"
if not exist "%TARGET%" (
  echo bmcp-restart: cannot find "%TARGET%" 1>&2
  echo Is the BrowserMCP repo intact at "$RepoRoot"? 1>&2
  endlocal & exit /b 1
)
powershell -NoProfile -Command "(Get-Item -LiteralPath '%TARGET%').LastWriteTime = Get-Date"
if errorlevel 1 (
  echo bmcp-restart: failed to update timestamp on "%TARGET%" 1>&2
  endlocal & exit /b 1
)
echo browsermcp: restart triggered (watcher will re-exec within ~1s)
endlocal & exit /b 0
"@

# Launcher + bmcp-restart: always GENERATE (3rd arg non-null) so abs path is baked in.
Install-Shim $LauncherSrc $LauncherDst $LauncherFallback
Install-Shim $RestartSrc  $RestartDst  $RestartFallback
# chrome-shim: just copy verbatim (no repo-path resolution needed; finds chrome
# via env vars at runtime which work from any dir).
Install-Shim $ChromeShim  $ChromeDst   $null

# Prepend BinDir to user PATH (user-scope, no admin) if not already present.
$userPath = [Environment]::GetEnvironmentVariable('PATH', 'User')
if (-not $userPath) { $userPath = '' }
if (($userPath -split ';') -notcontains $BinDir) {
  $newPath = "$BinDir;$userPath".TrimEnd(';')
  [Environment]::SetEnvironmentVariable('PATH', $newPath, 'User')
  Write-Ok "Prepended $BinDir to user PATH (new terminals will see it)"
} else {
  Write-Ok "$BinDir already on user PATH"
}

# ─── Step 3 / Claude Desktop config ──────────────────────────────
Write-Section "Step 3 / Update Claude Desktop config"
$ClaudeDir = Join-Path $env:APPDATA 'Claude'
New-Item -ItemType Directory -Path $ClaudeDir -Force | Out-Null
$CfgPath  = Join-Path $ClaudeDir 'claude_desktop_config.json'
$Template = Join-Path $OnboardingRoot 'claude_desktop_config.template.json'

if (-not (Test-Path $Template)) {
  Write-Err2 "Template not found: $Template"; exit 1
}

if (Test-Path $CfgPath) {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $bak = "$CfgPath.bak.$stamp"
  Copy-Item $CfgPath $bak -Force
  Write-Ok "Backed up existing config to: $bak"
}

# Load existing (or empty) config and template.
if (Test-Path $CfgPath) {
  $existing = Get-Content $CfgPath -Raw | ConvertFrom-Json
} else {
  $existing = [pscustomobject]@{ mcpServers = [pscustomobject]@{} }
}
if (-not ($existing.PSObject.Properties.Name -contains 'mcpServers') -or -not $existing.mcpServers) {
  $existing | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
}

$tmplRaw = Get-Content $Template -Raw

# Substitute placeholders.
# Note: JSON requires escaped backslashes. Forward slashes also work on Windows
# and are safer in JSON, so we normalize Windows paths to forward slashes.
function To-JsonPath([string]$p) { return $p -replace '\\','/' }

$homeFwd     = To-JsonPath $env:USERPROFILE
$launcherFwd = To-JsonPath $LauncherDst

# PS 5.1-safe placeholder substitution: plain String.Replace with pre-resolved
# strings. Empty PATs become empty strings (those servers are skipped at merge
# time anyway).
$gh = if ($GithubPat)     { $GithubPat }     else { '' }
$jr = if ($JiraPat)       { $JiraPat }       else { '' }
$cf = if ($ConfluencePat) { $ConfluencePat } else { '' }

$tmplFilled = $tmplRaw.Replace('{{HOME}}',           $homeFwd).
                       Replace('{{LAUNCHER_PATH}}',  $launcherFwd).
                       Replace('{{GITHUB_PAT}}',     $gh).
                       Replace('{{JIRA_PAT}}',       $jr).
                       Replace('{{CONFLUENCE_PAT}}', $cf)

# Windows-specific: the github-mcp-server binary is .exe. Claude Desktop's
# spawn path is strict about extensions on some Windows builds, so we
# explicitly append .exe here (the template uses an extension-less path).
$tmplFilled = $tmplFilled.Replace('/.local/bin/github-mcp-server"', '/.local/bin/github-mcp-server.exe"')

$tmpl = $tmplFilled | ConvertFrom-Json

# Decide which servers to install:
$needsToken = @{
  'github'     = [bool]$GithubPat
  'jira'       = [bool]$JiraPat
  'confluence' = [bool]$ConfluencePat
  'filesystem' = $true
  'browsermcp' = $true
}

$added = @(); $skipped = @()
foreach ($prop in $tmpl.mcpServers.PSObject.Properties) {
  $name = $prop.Name
  if (Test-Skip $name) { $skipped += "$name (--skip)"; continue }
  $required = $true
  if ($needsToken.ContainsKey($name)) { $required = $needsToken[$name] }
  if (-not $required) { $skipped += "$name (no PAT)"; continue }
  # Force-set property on existing.mcpServers
  if ($existing.mcpServers.PSObject.Properties.Name -contains $name) {
    $existing.mcpServers.PSObject.Properties.Remove($name)
  }
  $existing.mcpServers | Add-Member -NotePropertyName $name -NotePropertyValue $prop.Value -Force
  $added += $name
}

# Strip _comment keys from the merged object.
foreach ($p in @($existing.PSObject.Properties)) {
  if ($p.Name -like '_*') { $existing.PSObject.Properties.Remove($p.Name) }
}

$json = $existing | ConvertTo-Json -Depth 20
Set-Content -Path $CfgPath -Value $json -Encoding UTF8
Write-Ok "Config updated: $CfgPath"
Write-Info ("  Added:   " + ($(if ($added.Count)   { $added   -join ', ' } else { '(none)' })))
Write-Info ("  Skipped: " + ($(if ($skipped.Count) { $skipped -join ', ' } else { '(none)' })))

# ─── Step 4 / Atlassian plugin ───────────────────────────────────
Write-Section "Step 4 / Atlassian Claude CLI plugin"
if ($HasClaude) {
  $installed = $false
  try {
    $plugins = & claude plugin list 2>&1 | Out-String
    if ($plugins -match 'atlassian') { $installed = $true }
  } catch { }
  if ($installed) {
    Write-Ok "Already installed"
  } else {
    Write-Info "Installing..."
    & claude plugin install atlassian@claude-plugins-official
    if ($LASTEXITCODE -ne 0) { Write-Warn2 "Atlassian plugin install exited $LASTEXITCODE — continuing" }
  }
} else {
  Write-Warn2 "Skipped — claude CLI not on PATH."
}

# ─── Step 4b / Team skills ───────────────────────────────────────
Write-Section "Step 4b / Install team skills"
$SkillsSrc = Join-Path $RepoRoot 'team-skills'
$SkillsDst = Join-Path $env:USERPROFILE '.claude\skills'
New-Item -ItemType Directory -Path $SkillsDst -Force | Out-Null

function Copy-SkillDir([string]$sub, [string]$label) {
  $src = Join-Path $SkillsSrc $sub
  if (-not (Test-Path $src)) { Write-Warn2 "  (skip) $label — $src does not exist"; return }
  $count = 0
  Get-ChildItem -Path $src -Directory -ErrorAction SilentlyContinue | ForEach-Object {
    $skillMd = Join-Path $_.FullName 'SKILL.md'
    if (-not (Test-Path $skillMd)) { return }
    $dst = Join-Path $SkillsDst $_.Name
    if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
    Copy-Item -Recurse -Path $_.FullName -Destination $dst
    Write-Ok "  installed: $($_.Name)  ($label)"
    $count++
  }
  if ($count -eq 0) { Write-Warn2 "  (none) $label — no SKILL.md under $src" }
}

# Layer 1: universal
Copy-SkillDir 'all' 'all (universal)'

# Layer 2: team-specific
if ($Team) {
  $teamDir = Join-Path $SkillsSrc $Team
  if (-not (Test-Path $teamDir)) {
    Write-Err2 "--team='$Team' was passed but $teamDir does not exist."
    Write-Info "  Known teams:"
    Get-ChildItem -Path $SkillsSrc -Directory -ErrorAction SilentlyContinue | ForEach-Object {
      if ($_.Name -eq 'all') { return }
      if (Test-Path (Join-Path $_.FullName 'SKILL.md')) { return }  # flat skill
      Write-Host "    --team=$($_.Name)"
    }
    exit 1
  }
  Copy-SkillDir $Team "team:$Team"
} else {
  Write-Info "  (info) No --team flag — only 'all' + flat (legacy) skills will be installed."
}

# Layer 3: legacy flat skills (team-skills/<skill>/SKILL.md)
$flatCount = 0
Get-ChildItem -Path $SkillsSrc -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  if ($_.Name -eq 'all') { return }
  $skillMd = Join-Path $_.FullName 'SKILL.md'
  if (-not (Test-Path $skillMd)) { return }  # team bucket without root SKILL.md
  $dst = Join-Path $SkillsDst $_.Name
  if (Test-Path $dst) { Remove-Item -Recurse -Force $dst }
  Copy-Item -Recurse -Path $_.FullName -Destination $dst
  Write-Ok "  installed: $($_.Name)  (flat/legacy)"
  $flatCount++
}
if ($flatCount -eq 0) { Write-Warn2 "  (none) no flat/legacy skills found" }

# ─── Step 5 / Git credential helper ──────────────────────────────
Write-Section "Step 5 / Git credential helper"
if (Test-Cmd 'git') {
  $current = ''
  try { $current = (& git config --global credential.helper) 2>$null } catch {}
  if ($current -eq 'manager') {
    Write-Ok "Already set (manager)"
  } else {
    & git config --global credential.helper manager
    Write-Ok "Configured credential.helper=manager (Git Credential Manager)"
  }
} else {
  Write-Warn2 "git not on PATH — skipped."
}

# ─── Step 7 / Done ───────────────────────────────────────────────
Write-Section "All done"
Write-Info "→ Fully quit Claude Desktop (right-click tray icon → Quit, or Ctrl+Q), then relaunch"
Write-Info "→ Restart Chrome via $ChromeDst to enable remote-debugging port"
Write-Info "→ Open a NEW terminal so the updated PATH takes effect, then verify with: claude mcp list"
Write-Info "→ Dev tip: edit a skill, then run 'bmcp-restart' — no Claude restart needed"
Write-Info "→ Issues? See: team-onboarding\MANUAL.md (Known issues)"

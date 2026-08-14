#!/usr/bin/env bash
# install.sh — idempotent setup of the team Claude Code MCP toolkit.
# Run interactively. Will prompt for PATs (input is hidden). Run it again any
# time — it skips steps already done.
#
# Usage:
#   bash install.sh
#   bash install.sh --skip jira,confluence   # skip specific MCP servers
#   bash install.sh --team produce           # install the "all" skills + the "produce" team's skills
#
# Layered team-skills install model (Phase 5):
#   • team-skills/all/        → universal skills, copied for EVERY user regardless of --team
#   • team-skills/<team>/     → team-specific skills, copied only when --team=<team> is passed
#   • team-skills/*/SKILL.md  → legacy flat layout (current shipped set). Skills living directly
#                               under team-skills/ — i.e. NOT inside an `all/` or `<team>/`
#                               subdir — are treated as universal and always installed. This
#                               keeps the existing 8 skills working without forcing a migration.
#
# If --team is omitted: install team-skills/all/* + all flat (legacy) team-skills/*/.
# If --team=<name>:     install team-skills/all/* + team-skills/<name>/* + all flat (legacy).
#
# Future: --team will be auto-detected from the user's Entra ID / corporate AD group
# instead of being passed by hand. See docs/phase5-multi-team.md "Open question".

set -euo pipefail

SKIP=""
TEAM=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip) SKIP="$2"; shift 2 ;;
    --skip=*) SKIP="${1#--skip=}"; shift ;;
    --team) TEAM="$2"; shift 2 ;;
    --team=*) TEAM="${1#--team=}"; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# Validate --team is kebab-case and path-safe BEFORE it gets interpolated
# into any cp source / dst path. Without this, --team='../../etc' would let a
# caller traverse out of team-skills/ when copying with `cp -R`.
if [[ -n "$TEAM" ]]; then
  if [[ ! "$TEAM" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "✗ --team must be kebab-case (lowercase letters, digits, hyphens); got: '$TEAM'" >&2
    exit 1
  fi
fi

skip_has() { [[ ",$SKIP," == *",$1,"* ]]; }

# ─── pretty printing ─────────────────────────────────────────────
c_green() { printf "\033[32m%s\033[0m\n" "$*"; }
c_yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
c_red() { printf "\033[31m%s\033[0m\n" "$*"; }
c_cyan() { printf "\033[36m%s\033[0m\n" "$*"; }
section() { echo; c_cyan "━━━ $1 ━━━"; }

# ─── prereq check ────────────────────────────────────────────────
section "Checking prerequisites"
for cmd in git python3 curl claude; do
  if command -v "$cmd" >/dev/null 2>&1; then
    c_green "✓ $cmd"
  else
    c_red "✗ $cmd not found — please install it first"
    exit 1
  fi
done

# ─── 1. github-mcp-server binary ─────────────────────────────────
section "Step 1 / GitHub MCP server binary"
mkdir -p "$HOME/.local/bin"
if [[ -x "$HOME/.local/bin/github-mcp-server" ]]; then
  c_green "✓ Already installed: $($HOME/.local/bin/github-mcp-server --version | head -1)"
else
  # PIN to a specific release tag — never auto-upgrade.
  # When bumping, also update GHMCP_SHA256_* below by downloading the asset and
  # running: shasum -a 256 github-mcp-server_${SUFFIX}.tar.gz
  GHMCP_VERSION="v1.4.0"
  # TODO: pin SHA256 of each Darwin/Linux/Windows asset and verify before mv.
  # See docs/security.md §3 T6 (supply-chain). Tracked as a follow-up.

  ARCH=$(uname -m)
  [[ "$ARCH" == "arm64" ]] && SUFFIX="Darwin_arm64" || SUFFIX="Darwin_x86_64"
  c_yellow "Downloading github-mcp-server $GHMCP_VERSION ($SUFFIX)..."
  ASSET_URL="https://github.com/github/github-mcp-server/releases/download/${GHMCP_VERSION}/github-mcp-server_${SUFFIX}.tar.gz"
  TMP=$(mktemp -d)
  if ! curl -fsSL -o "$TMP/gh-mcp.tar.gz" "$ASSET_URL"; then
    c_red "✗ Failed to download $ASSET_URL — check network or bump GHMCP_VERSION"
    rm -rf "$TMP"
    exit 1
  fi
  tar -xzf "$TMP/gh-mcp.tar.gz" -C "$TMP"
  mv "$TMP/github-mcp-server" "$HOME/.local/bin/"
  chmod +x "$HOME/.local/bin/github-mcp-server"
  rm -rf "$TMP"
  c_green "✓ Installed: $($HOME/.local/bin/github-mcp-server --version | head -1)"
fi

# ─── 2. PATs (silent prompts) ────────────────────────────────────
section "Step 2 / Collect PATs (input is hidden — Enter to skip)"

prompt_secret() {
  local label="$1"
  local var=""
  if ! skip_has "${1,,}"; then
    printf "%s (or Enter to skip): " "$label" >&2
    read -rs var
    echo
  fi
  echo "$var"
}

GITHUB_PAT=$(prompt_secret "GitHub PAT")
JIRA_PAT=$(prompt_secret "Jira PAT")
CONFLUENCE_PAT=$(prompt_secret "Confluence PAT")

if [[ -n "$GITHUB_PAT" ]]; then
  c_yellow "Testing GitHub PAT..."
  HTTP=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer $GITHUB_PAT" \
    https://api.github.com/user)
  if [[ "$HTTP" == "200" ]]; then
    c_green "✓ GitHub PAT valid"
  else
    c_red "✗ GitHub PAT returned HTTP $HTTP — aborting before saving"
    exit 1
  fi
fi

# ─── 2b. BrowserMCP Python venv ─────────────────────────────────
# The config block written in Step 3 points at {{REPO_ROOT}}/.venv/bin/python,
# so the venv has to exist BEFORE Claude Desktop tries to launch the server.
section "Step 2b / BrowserMCP Python environment"
REPO_FOR_VENV="$(cd "$(dirname "$0")/../.." && pwd)"
if [[ -x "$REPO_FOR_VENV/.venv/bin/python" ]]; then
  c_green "✓ venv already present at $REPO_FOR_VENV/.venv"
else
  if ! command -v uv >/dev/null 2>&1; then
    c_yellow "uv not found — installing via astral.sh..."
    curl -LsSf https://astral.sh/uv/install.sh | sh || {
      c_red "✗ uv install failed. Try manually: curl -LsSf https://astral.sh/uv/install.sh | sh"
      exit 1
    }
    # The uv installer drops the binary at ~/.local/bin (or ~/.cargo/bin on older
    # versions). Source the env file it writes, or fall back to PATH-prepending.
    [[ -f "$HOME/.local/bin/env" ]] && source "$HOME/.local/bin/env"
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv >/dev/null 2>&1; then
      c_red "✗ uv installed but not on PATH. Restart your terminal and re-run this installer."
      exit 1
    fi
    c_green "✓ uv installed: $(uv --version)"
  fi
  c_yellow "Creating venv via uv sync (this can take 1-2 min on first run)..."
  ( cd "$REPO_FOR_VENV" && uv sync ) || {
    c_red "✗ uv sync failed. Check that pypi.org and files.pythonhosted.org are reachable (proxy/VPN if your network needs one), then re-run."
    exit 1
  }
  c_green "✓ venv ready at $REPO_FOR_VENV/.venv"
fi

# ─── 3. claude_desktop_config.json ───────────────────────────────
section "Step 3 / Update Claude Desktop config"
CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
TEMPLATE="$(cd "$(dirname "$0")/.." && pwd)/claude_desktop_config.template.json"
if [[ ! -f "$TEMPLATE" ]]; then
  c_red "✗ Template not found: $TEMPLATE"
  exit 1
fi

if [[ -f "$CFG" ]]; then
  BAK="$CFG.bak.$(date +%Y%m%d-%H%M%S)"
  cp "$CFG" "$BAK"
  c_green "✓ Backed up existing config to: $BAK"
fi

REPO_ROOT_FOR_CFG="$(cd "$(dirname "$0")/../.." && pwd)"
GITHUB_PAT="$GITHUB_PAT" JIRA_PAT="$JIRA_PAT" CONFLUENCE_PAT="$CONFLUENCE_PAT" \
  CFG_PATH="$CFG" TEMPLATE_PATH="$TEMPLATE" SKIP="$SKIP" \
  REPO_ROOT_FOR_CFG="$REPO_ROOT_FOR_CFG" \
  python3 - <<'PY'
import json, os, sys

cfg_path = os.environ['CFG_PATH']
tmpl_path = os.environ['TEMPLATE_PATH']
skip = set(s.strip() for s in os.environ.get('SKIP','').split(',') if s.strip())

# Load existing
try:
    with open(cfg_path) as f:
        cfg = json.load(f)
except FileNotFoundError:
    cfg = {"mcpServers": {}}

cfg.setdefault('mcpServers', {})

with open(tmpl_path) as f:
    tmpl = json.load(f)

# Substitute placeholders
def sub(obj):
    if isinstance(obj, dict):
        return {k: sub(v) for k,v in obj.items() if not k.startswith('_')}
    if isinstance(obj, list):
        return [sub(x) for x in obj]
    if isinstance(obj, str):
        return (obj
                .replace('{{HOME}}', os.path.expanduser('~'))
                .replace('{{LAUNCHER_PATH}}', os.path.expanduser('~') + '/.local/bin/browsermcp-launcher')
                .replace('{{REPO_ROOT}}', os.environ.get('REPO_ROOT_FOR_CFG',''))
                .replace('{{GITHUB_PAT}}', os.environ.get('GITHUB_PAT',''))
                .replace('{{JIRA_PAT}}', os.environ.get('JIRA_PAT',''))
                .replace('{{CONFLUENCE_PAT}}', os.environ.get('CONFLUENCE_PAT','')))
    return obj

tmpl_clean = sub(tmpl)

# Merge: only add servers the user has tokens for (and that aren't skipped)
added, skipped = [], []
for name, server in tmpl_clean.get('mcpServers', {}).items():
    if name in skip:
        skipped.append(f'{name} (--skip)')
        continue
    # Skip if a token placeholder wasn't filled in
    needs_token = {
        'github':     bool(os.environ.get('GITHUB_PAT')),
        'jira':       bool(os.environ.get('JIRA_PAT')),
        'confluence': bool(os.environ.get('CONFLUENCE_PAT')),
        'filesystem': True,  # no token needed
        'browsermcp': True,  # local server, no token needed
    }
    if not needs_token.get(name, True):
        skipped.append(f'{name} (no PAT)')
        continue
    cfg['mcpServers'][name] = server
    added.append(name)

with open(cfg_path, 'w') as f:
    json.dump(cfg, f, indent=2)
print('Added:', ', '.join(added) or '(none)')
print('Skipped:', ', '.join(skipped) or '(none)')
PY
c_green "✓ Config updated: $CFG"

# ─── 4. Atlassian plugin ────────────────────────────────────────
section "Step 4 / Atlassian Claude CLI plugin"
if claude plugin list 2>&1 | grep -q atlassian; then
  c_green "✓ Already installed"
else
  c_yellow "Installing..."
  claude plugin install atlassian@claude-plugins-official 2>&1 | tail -5
fi

# ─── 4b. Team skills (layered: all/ + <team>/ + flat legacy) ────
section "Step 4b / Install team skills"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SKILLS_SRC="$REPO_ROOT/team-skills"
SKILLS_DST="$HOME/.claude/skills"
mkdir -p "$SKILLS_DST"

copy_skill_dir() {
  # copy_skill_dir <src_subdir_under_team-skills> <human_label>
  local sub="$1"
  local label="$2"
  local src="$SKILLS_SRC/$sub"
  if [[ ! -d "$src" ]]; then
    c_yellow "  (skip) $label — $src does not exist"
    return 0
  fi
  local count=0
  # Each immediate child directory of $src that contains SKILL.md is a skill.
  shopt -s nullglob
  for d in "$src"/*/; do
    [[ -f "$d/SKILL.md" ]] || continue
    local name
    name="$(basename "$d")"
    rm -rf "$SKILLS_DST/$name"
    cp -R "$d" "$SKILLS_DST/$name"
    c_green "  ✓ installed: $name  ($label)"
    count=$((count+1))
  done
  shopt -u nullglob
  if [[ $count -eq 0 ]]; then
    c_yellow "  (none) $label — no SKILL.md found under $src"
  fi
}

# Layer 1: universal — team-skills/all/
copy_skill_dir "all" "all (universal)"

# Layer 2: team-specific — team-skills/<team>/  (only if --team was passed)
if [[ -n "$TEAM" ]]; then
  if [[ ! -d "$SKILLS_SRC/$TEAM" ]]; then
    c_red "✗ --team='$TEAM' was passed but $SKILLS_SRC/$TEAM does not exist."
    c_yellow "  Known teams:"
    shopt -s nullglob
    for d in "$SKILLS_SRC"/*/; do
      n="$(basename "$d")"
      # Skip the universal bucket and any flat skills (those have SKILL.md directly inside).
      [[ "$n" == "all" ]] && continue
      [[ -f "$d/SKILL.md" ]] && continue
      echo "    --team=$n"
    done
    shopt -u nullglob
    exit 1
  fi
  copy_skill_dir "$TEAM" "team:$TEAM"
else
  c_yellow "  (info) No --team flag — only 'all' + flat (legacy) skills will be installed."
fi

# Layer 3: legacy flat layout — team-skills/<skill>/SKILL.md
# Existing shipped skills live one level deep with SKILL.md directly inside. Treat
# them as universal until they migrate into team-skills/all/ or a team subdir.
shopt -s nullglob
flat_count=0
for d in "$SKILLS_SRC"/*/; do
  name="$(basename "$d")"
  # Skip the layered buckets so we don't double-install.
  [[ "$name" == "all" ]] && continue
  [[ -d "$SKILLS_SRC/$name" && ! -f "$d/SKILL.md" ]] && continue  # team bucket (no SKILL.md at root)
  [[ -f "$d/SKILL.md" ]] || continue
  rm -rf "$SKILLS_DST/$name"
  cp -R "$d" "$SKILLS_DST/$name"
  c_green "  ✓ installed: $name  (flat/legacy)"
  flat_count=$((flat_count+1))
done
shopt -u nullglob
[[ $flat_count -eq 0 ]] && c_yellow "  (none) no flat/legacy skills found"

# ─── 5. git credential helper ───────────────────────────────────
section "Step 5 / Git credential helper"
if [[ "$(git config --global credential.helper || true)" == "osxkeychain" ]]; then
  c_green "✓ Already set"
else
  git config --global credential.helper osxkeychain
  c_green "✓ Configured"
fi

if [[ -n "$GITHUB_PAT" ]]; then
  GH_USER=$(curl -s -H "Authorization: Bearer $GITHUB_PAT" \
    https://api.github.com/user | python3 -c "import json,sys; print(json.load(sys.stdin)['login'])")
  printf "protocol=https\nhost=github.com\nusername=%s\npassword=%s\n" \
    "$GH_USER" "$GITHUB_PAT" | git credential-osxkeychain store
  c_green "✓ Cached GitHub PAT in Keychain for user: $GH_USER"
fi

# ─── 6. BrowserMCP CLI helpers (launcher + bmcp-restart) ────────
section "Step 6 / BrowserMCP CLI helpers"
# Two symlinks into ~/.local/bin:
#   browsermcp-launcher → the wrapper Claude Desktop spawns. Resolves the repo
#       root from its own real path at runtime, so claude_desktop_config.json
#       has no absolute repo path baked in. Moving the repo only requires
#       re-running this installer to refresh the symlink.
#   bmcp-restart      → touches browsermcp/state.py to trigger the in-server
#       file-watcher to re-exec without restarting Claude. NOTE: the watcher
#       ships OFF (BROWSERMCP_WATCH=0) because the re-exec breaks the live MCP
#       session (stale initialize handshake → -32602 on every tool call). This
#       helper is a no-op unless you opt back in by setting BROWSERMCP_WATCH=1.
mkdir -p "$HOME/.local/bin"

for pair in \
    "launch-browsermcp.sh:browsermcp-launcher" \
    "bmcp-restart:bmcp-restart"
do
  src_name="${pair%%:*}"
  dst_name="${pair##*:}"
  src="$REPO_ROOT/scripts/$src_name"
  dst="$HOME/.local/bin/$dst_name"
  if [[ ! -f "$src" ]]; then
    c_yellow "(skipped $dst_name — $src missing)"
    continue
  fi
  chmod +x "$src"
  ln -sf "$src" "$dst"
  c_green "✓ Installed: $dst → $src"
done

# Warn if ~/.local/bin isn't on PATH. The launcher works regardless (Claude
# Desktop uses the absolute path); the warning is for bmcp-restart usability.
case ":$PATH:" in
  *":$HOME/.local/bin:"*)
    c_green "✓ ~/.local/bin is on PATH — type 'bmcp-restart' anywhere"
    ;;
  *)
    c_yellow "⚠ ~/.local/bin is NOT on PATH. Add this to ~/.zshrc for"
    c_yellow "  'bmcp-restart' to work as a plain command:"
    c_yellow '    export PATH="$HOME/.local/bin:$PATH"'
    c_yellow "  (The launcher itself works regardless — Claude Desktop uses"
    c_yellow "  the absolute symlink path.)"
    ;;
esac

# ─── 7. Done ─────────────────────────────────────────────────────
section "All done"
c_yellow "→ Cmd+Q Claude Desktop (fully quit), then relaunch"
c_yellow "→ Verify with: claude mcp list"
c_yellow "→ Dev tip: edit a skill, then run 'bmcp-restart' — no Claude restart needed"
c_yellow "→ Issues? See: team-onboarding/MANUAL.md (Known issues)"

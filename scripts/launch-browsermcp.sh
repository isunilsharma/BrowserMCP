#!/usr/bin/env bash
# Launcher for the BrowserMCP server, used as the Claude Desktop MCP 'command'.
#
# Resolves the repo root from this script's REAL path (following symlinks), so
# claude_desktop_config.json doesn't bake in an absolute repo path. Moving the
# repo only requires re-running team-onboarding/scripts/install.sh to refresh
# the symlink at ~/.local/bin/browsermcp-launcher — no config edit needed.

set -euo pipefail

# realpath follows symlinks; python3 fallback for macOS systems without coreutils.
SCRIPT_PATH="$(readlink -f "$0" 2>/dev/null \
  || python3 -c "import os,sys; print(os.path.realpath(sys.argv[1]))" "$0")"

REPO_ROOT="$(cd "$(dirname "$SCRIPT_PATH")/.." && pwd)"
VENV_PY="$REPO_ROOT/.venv/bin/python"

if [[ ! -x "$VENV_PY" ]]; then
  echo "browsermcp-launcher: venv missing at $VENV_PY" >&2
  echo "Run: cd $REPO_ROOT && uv sync" >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT"
exec "$VENV_PY" -m browsermcp.server

#!/usr/bin/env bash
# setup.sh
#
# One-time local setup for BrowserMCP on a developer's macOS machine.
#
# This script is idempotent — running it twice is safe. It:
#   1. Creates ~/.browsermcp/        (config + runtime root for the MCP server)
#   2. Creates ~/.browsermcp/runs/   (JSONL run logs land here)
#   3. Installs chrome-shim.sh to ~/.local/bin/chrome with the executable bit
#      so the user can launch a CDP-enabled Chrome by typing `chrome`.
#   4. Prints next steps for finishing the install (uv sync, Claude Code MCP
#      registration, etc.).
#
# It does NOT touch ~/.browsermcp/config.toml if it already exists, so user-edited
# settings are preserved across re-runs.
#
# Usage:
#   bash scripts/setup.sh

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

readonly BROWSERMCP_DIR="${HOME}/.browsermcp"
readonly RUNS_DIR="${BROWSERMCP_DIR}/runs"
readonly LOCAL_BIN="${HOME}/.local/bin"
readonly SHIM_SRC="${SCRIPT_DIR}/chrome-shim.sh"
readonly SHIM_DEST="${LOCAL_BIN}/chrome"

echo "setup: creating ${BROWSERMCP_DIR}"
mkdir -p "${BROWSERMCP_DIR}"

echo "setup: creating ${RUNS_DIR}"
mkdir -p "${RUNS_DIR}"

if [[ ! -f "${SHIM_SRC}" ]]; then
  echo "setup: chrome-shim source not found at ${SHIM_SRC}" >&2
  exit 1
fi

echo "setup: installing chrome shim to ${SHIM_DEST}"
mkdir -p "${LOCAL_BIN}"
install -m 0755 "${SHIM_SRC}" "${SHIM_DEST}"

echo
echo "setup: complete."
echo
echo "Next steps:"
echo "  1. Ensure ${LOCAL_BIN} is on your PATH. If not, add this to ~/.zshrc:"
echo "       export PATH=\"\${HOME}/.local/bin:\${PATH}\""
echo
echo "  2. Install Python dependencies from the repo root:"
echo "       cd ${REPO_ROOT}"
echo "       uv sync"
echo
echo "  3. Launch a CDP-enabled Chrome (uses your normal profile):"
echo "       chrome"
echo
echo "  4. Register the MCP server with Claude Code. From the repo root:"
echo "       claude mcp add browsermcp -- uv run browsermcp"
echo
echo "  5. If running outside Claude Code, export your Anthropic API key:"
echo "       export ANTHROPIC_API_KEY=sk-ant-..."
echo
echo "  Logs land in ${RUNS_DIR}/<run-id>.jsonl"

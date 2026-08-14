#!/usr/bin/env bash
# install-keepalive.sh
#
# One-time installer for the Phase 4 v0 session-keepalive launchd agent.
#
# What it does (idempotent — safe to re-run):
#   1. Ensures ~/.browsermcp/keepalive.toml exists — drops a commented-out template
#      if not. The user edits this file to add their own URL patterns.
#   2. Copies scripts/com.browsermcp.keepalive.plist into
#      ~/Library/LaunchAgents/, substituting __BROWSERMCP_REPO__ and __HOME__
#      with absolute paths for the current machine.
#   3. Runs `launchctl load` on the plist. If the agent was already loaded,
#      unloads it first so the new copy takes effect.
#   4. Reports success and the next ping time (~30 min from load).
#
# What it does NOT do:
#   - It does NOT install Chrome / uv / Python deps — run scripts/setup.sh and
#     `uv sync` first.
#   - It does NOT touch ~/.browsermcp/keepalive.toml if it already exists.
#   - It does NOT attempt to sign anything in. The keepalive only reads tabs
#     that are already signed in; if a session has expired it logs a warning
#     and moves on.
#
# Usage:
#   bash scripts/install-keepalive.sh

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

readonly BROWSERMCP_DIR="${HOME}/.browsermcp"
readonly KEEPALIVE_TOML="${BROWSERMCP_DIR}/keepalive.toml"

readonly PLIST_NAME="com.browsermcp.keepalive.plist"
readonly PLIST_LABEL="com.browsermcp.keepalive"
readonly PLIST_SRC="${SCRIPT_DIR}/${PLIST_NAME}"
readonly LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"
readonly PLIST_DEST="${LAUNCH_AGENTS_DIR}/${PLIST_NAME}"

c_green() { printf '\033[32m%s\033[0m\n' "$*"; }
c_yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
c_red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }

# --- 1. keepalive.toml ----------------------------------------------------

mkdir -p "${BROWSERMCP_DIR}"

if [[ -f "${KEEPALIVE_TOML}" ]]; then
  c_yellow "keepalive.toml already exists at ${KEEPALIVE_TOML} — leaving it alone."
else
  cat > "${KEEPALIVE_TOML}" <<'TEMPLATE'
# ~/.browsermcp/keepalive.toml
#
# URLs the keepalive agent reads every 30 min to refresh your SSO sessions.
# Add one [[urls]] block per site you want kept warm. The `pattern` matches
# substrings of any tab URL — first match wins.
#
# Uncomment a block to enable it.

# [[urls]]
# pattern = "powerbi.example.com"
# description = "Power BI"

# [[urls]]
# pattern = "confluence.example.com"
# description = "Confluence"

# [[urls]]
# pattern = "outlook.office.com"
# description = "Outlook on the web"
TEMPLATE
  c_green "wrote template ${KEEPALIVE_TOML} — edit it to add your URL patterns."
fi

# --- 2. install plist with substituted paths ------------------------------

if [[ ! -f "${PLIST_SRC}" ]]; then
  c_red "plist source missing at ${PLIST_SRC}"
  exit 1
fi

mkdir -p "${LAUNCH_AGENTS_DIR}"

# Substitute __BROWSERMCP_REPO__ and __HOME__ with real absolute paths.
# Using bash + printf instead of sed -i (which differs across BSD/GNU).
plist_contents="$(cat "${PLIST_SRC}")"
plist_contents="${plist_contents//__BROWSERMCP_REPO__/${REPO_ROOT}}"
plist_contents="${plist_contents//__HOME__/${HOME}}"
printf '%s' "${plist_contents}" > "${PLIST_DEST}"

c_green "installed ${PLIST_DEST}"

# --- 3. load via launchctl ------------------------------------------------

# Unload first if already loaded — otherwise launchctl load is a no-op.
if launchctl list | grep -q "${PLIST_LABEL}"; then
  c_yellow "agent already loaded — unloading first."
  launchctl unload "${PLIST_DEST}" 2>/dev/null || true
fi

launchctl load "${PLIST_DEST}"

c_green "loaded ${PLIST_LABEL} — first run in ~30 min."
echo
echo "Next steps:"
echo "  1. Edit ${KEEPALIVE_TOML} and uncomment the URLs you want kept warm."
echo "  2. Watch the log to confirm it ran:"
echo "       tail -f ${BROWSERMCP_DIR}/keepalive.err.log"
echo "  3. To trigger a run now (instead of waiting 30 min):"
echo "       launchctl start ${PLIST_LABEL}"
echo "  4. To uninstall:"
echo "       launchctl unload ${PLIST_DEST} && rm ${PLIST_DEST}"

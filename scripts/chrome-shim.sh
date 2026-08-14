#!/usr/bin/env bash
# chrome-shim.sh
#
# Launches Google Chrome on macOS with the Chrome DevTools Protocol (CDP)
# remote debugging endpoint enabled on 127.0.0.1:9222, using the user's
# default Chrome profile directory.
#
# BrowserMCP attaches to this endpoint via browser-use's CDP client so the
# MCP server drives the same Chrome the user is already signed into
# (SSO sessions, cookies, bookmarks, extensions all intact).
#
# Behavior:
#   1. Quit any running Chrome instance gracefully (a running Chrome holds
#      a singleton lock on the user-data-dir and will refuse the new flags).
#   2. Wait briefly for the process to actually exit.
#   3. Relaunch Chrome via `open -na` with the debugging flags and pass
#      any extra arguments straight through to Chrome.
#
# Usage:
#   chrome-shim.sh                          # launch with defaults
#   chrome-shim.sh https://example.com      # launch and open a URL
#   chrome-shim.sh --incognito              # forward any extra flag

set -euo pipefail

readonly CHROME_APP="Google Chrome"
readonly CHROME_BIN="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
readonly DEBUG_PORT="9222"
readonly DEBUG_ADDR="127.0.0.1"
# Chrome 136+ refuses to enable remote-debugging on the default profile dir
# (security hardening). We use a dedicated profile under ~/.browsermcp/ instead.
# First launch is unauthenticated — user signs into corporate SSO once and the
# session cookies persist in this profile across reboots.
readonly USER_DATA_DIR="${HOME}/.browsermcp/chrome-profile"

if [[ ! -x "${CHROME_BIN}" ]]; then
  echo "chrome-shim: Chrome not found at ${CHROME_BIN}" >&2
  echo "chrome-shim: install Google Chrome from https://www.google.com/chrome/" >&2
  exit 1
fi

if pgrep -x "${CHROME_APP}" >/dev/null 2>&1; then
  echo "chrome-shim: quitting running Chrome to release the profile lock..."
  osascript -e 'tell application "Google Chrome" to quit' >/dev/null 2>&1 || true

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! pgrep -x "${CHROME_APP}" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done

  if pgrep -x "${CHROME_APP}" >/dev/null 2>&1; then
    echo "chrome-shim: Chrome did not exit after 5s; forcing termination" >&2
    pkill -x "${CHROME_APP}" >/dev/null 2>&1 || true
    sleep 1
  fi
fi

echo "chrome-shim: launching Chrome with --remote-debugging-port=${DEBUG_PORT}"
exec "${CHROME_BIN}" \
  --remote-debugging-port="${DEBUG_PORT}" \
  --remote-debugging-address="${DEBUG_ADDR}" \
  --user-data-dir="${USER_DATA_DIR}" \
  "$@"

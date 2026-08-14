@echo off
REM ============================================================================
REM chrome-shim.cmd
REM
REM Launches Google Chrome on Windows with the Chrome DevTools Protocol (CDP)
REM remote debugging endpoint enabled on 127.0.0.1:9222, using a dedicated
REM Chrome profile directory under %USERPROFILE%\.browsermcp\chrome-profile.
REM
REM BrowserMCP attaches to this endpoint via browser-use's CDP client so the
REM MCP server drives the same Chrome the user is already signed into
REM (SSO sessions, cookies, bookmarks, extensions all intact).
REM
REM IMPORTANT: The user MUST close all running Chrome windows BEFORE invoking
REM this script. A running Chrome process holds a singleton lock on its
REM user-data-dir, and Chrome will silently ignore --remote-debugging-port
REM if any other instance is already using that profile. If port 9222 is not
REM responding after launch, close every Chrome window (check the system tray
REM too) and re-run. You can force-kill with:  taskkill /IM chrome.exe /F
REM
REM Chrome 136+ also refuses to enable remote-debugging on the *default*
REM Chrome profile dir (security hardening); that's why we use a dedicated
REM profile under %USERPROFILE%\.browsermcp\chrome-profile. First launch is
REM unauthenticated -- user signs into corporate SSO once and the session
REM cookies persist in this profile across reboots.
REM
REM Usage:
REM   chrome-shim.cmd                          REM launch with defaults
REM   chrome-shim.cmd https://example.com      REM launch and open a URL
REM   chrome-shim.cmd --incognito              REM forward any extra flag
REM ============================================================================

setlocal

set "DEBUG_PORT=9222"
set "DEBUG_ADDR=127.0.0.1"
set "USER_DATA_DIR=%USERPROFILE%\.browsermcp\chrome-profile"

set "CHROME_BIN="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
) else if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
) else if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" (
    set "CHROME_BIN=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
)

if not defined CHROME_BIN (
    echo chrome-shim: chrome.exe not found in any of: 1>&2
    echo   %ProgramFiles%\Google\Chrome\Application\chrome.exe 1>&2
    echo   %ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe 1>&2
    echo   %LOCALAPPDATA%\Google\Chrome\Application\chrome.exe 1>&2
    echo chrome-shim: install Google Chrome from https://www.google.com/chrome/ 1>&2
    exit /b 1
)

if not exist "%USER_DATA_DIR%" (
    mkdir "%USER_DATA_DIR%" 2>nul
)

echo chrome-shim: launching Chrome with --remote-debugging-port=%DEBUG_PORT%
echo chrome-shim: if port %DEBUG_PORT% is unreachable, close ALL Chrome windows and re-run.

start "" "%CHROME_BIN%" ^
    --remote-debugging-port=%DEBUG_PORT% ^
    --remote-debugging-address=%DEBUG_ADDR% ^
    --user-data-dir="%USER_DATA_DIR%" ^
    %*

endlocal
exit /b 0

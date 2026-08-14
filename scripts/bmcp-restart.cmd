@echo off
REM Trigger the BrowserMCP server's file-watcher to re-exec the process.
REM Useful in dev when you've edited a skill or browsermcp/*.py file and want
REM the running MCP server to pick up the change without restarting Claude Code.
REM
REM Requires BROWSERMCP_WATCH=1 in the MCP server's env (set by install.ps1).
REM Without that, this still touches the file but the server won't re-exec.

setlocal

REM Resolve the repo root from the location of this script.
REM %~dp0 = drive+directory of this .cmd (with trailing backslash).
REM Note: on Windows %~dp0 does NOT follow symlinks; the installer is expected
REM to either copy this shim into %USERPROFILE%\.local\bin or hardlink it,
REM or users invoke it directly from the repo's scripts\ dir.
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"

set "TARGET=%REPO_ROOT%\browsermcp\state.py"

if not exist "%TARGET%" (
  echo bmcp-restart: cannot find "%TARGET%" 1>&2
  echo Is the BrowserMCP repo intact at "%REPO_ROOT%"? 1>&2
  exit /b 1
)

REM Update LastWriteTime via PowerShell. cmd.exe has no built-in `touch`.
REM PowerShell's Get-Item / .LastWriteTime is the most reliable method:
REM   - works on files held open in shared-read mode by the watcher
REM   - does not modify file contents (unlike `copy /b file +,, file`)
REM   - watchdog / ReadDirectoryChangesW on NTFS picks up the change cleanly
powershell -NoProfile -Command "(Get-Item -LiteralPath '%TARGET%').LastWriteTime = Get-Date"
if errorlevel 1 (
  echo bmcp-restart: failed to update timestamp on "%TARGET%" 1>&2
  exit /b 1
)

echo browsermcp: restart triggered (watcher will re-exec within ~1s)
endlocal
exit /b 0

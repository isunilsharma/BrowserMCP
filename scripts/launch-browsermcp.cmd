@echo off
rem Launcher for the BrowserMCP server, used as the Claude Desktop MCP 'command' on Windows.
rem
rem Claude Desktop on Windows spawns this via cmd.exe. We resolve the repo root from this
rem script's own location (%~dp0) so claude_desktop_config.json doesn't bake in an absolute
rem repo path. Note: unlike Unix readlink, %~f0 / %~dp0 do NOT follow symlinks — installers
rem should either copy this .cmd into the PATH dir, use an NTFS hardlink (mklink /H, same
rem volume), or generate a tiny shim .cmd that forwards to this absolute path.

setlocal

rem %~f0 = fully qualified path of this .cmd as invoked; %~dp0 = its drive+dir with trailing \
set "SCRIPT_DIR=%~dp0"

rem Repo root is the parent of scripts\ — strip the trailing backslash, then take dirname.
for %%I in ("%SCRIPT_DIR%.") do set "REPO_ROOT=%%~dpI"
rem Strip trailing backslash from REPO_ROOT for cleanliness.
if "%REPO_ROOT:~-1%"=="\" set "REPO_ROOT=%REPO_ROOT:~0,-1%"

set "VENV_PY=%REPO_ROOT%\.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
  echo browsermcp-launcher: venv missing at "%VENV_PY%" 1>&2
  echo Run: cd /d "%REPO_ROOT%" ^&^& uv sync 1>&2
  endlocal
  exit /b 1
)

set "PYTHONPATH=%REPO_ROOT%"

rem cmd has no exec; call python and forward its exit code. endlocal before exit so the
rem parent env stays clean, and use /b so we don't kill the parent cmd.exe Claude spawned.
"%VENV_PY%" -m browsermcp.server
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%

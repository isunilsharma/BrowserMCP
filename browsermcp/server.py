"""FastMCP server entrypoint that exposes BrowserMCP primitives to Claude Code."""

from __future__ import annotations

import os

# Disable browser_use telemetry BEFORE any import that might pull it in.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_TELEMETRY_DISABLED", "1")

import asyncio
import functools
import inspect
import socket
import sys
import time

# Dev hot-reload: when BROWSERMCP_WATCH=1, watch browsermcp/*.py and re-exec
# the server process on any change. os.execv replaces the process image while
# keeping the same PID and inherited stdio fds, so the pipe stays open — BUT the
# fresh process does NOT re-run the MCP `initialize` handshake, so Claude Code's
# already-negotiated session goes stale and every tool call fails with
# -32602 until the client reconnects. Hence OFF by default; only enable while
# editing server code, and reconnect (/mcp → browsermcp) after each reload.
if os.environ.get("BROWSERMCP_WATCH") == "1":
    import threading
    from pathlib import Path as _Path

    def _watch_and_reexec() -> None:
        watch_dir = _Path(__file__).parent
        mtimes: dict[_Path, float] = {}
        for p in watch_dir.rglob("*.py"):
            try:
                mtimes[p] = p.stat().st_mtime
            except OSError:
                pass
        while True:
            time.sleep(1.0)
            for p in watch_dir.rglob("*.py"):
                try:
                    mt = p.stat().st_mtime
                except OSError:
                    continue
                prev = mtimes.get(p)
                if prev is None:
                    mtimes[p] = mt
                    continue
                if mt > prev:
                    print(f"[browsermcp watch] {p.name} changed → re-exec", file=sys.stderr)
                    os.execv(sys.executable, [sys.executable, "-m", "browsermcp.server"])

    threading.Thread(target=_watch_and_reexec, daemon=True).start()

from mcp.server.fastmcp import FastMCP

from .logging_jsonl import run_logger
from .tools.chrome import (
    chrome_attach,
    chrome_close_window,
    chrome_find_or_open_window,
    chrome_new_window,
)
from .tools.context import set_skill_context
from .tools.evaluate import page_evaluate
from .tools.extraction import extract
from .tools.interaction import click, type_text
from .tools.navigation import navigate, scroll, wait_for
from .tools.notify import notify_email, notify_slack, notify_teams
from .tools.powerbi import powerbi_discover_fields, powerbi_set_filter
from .tools.reading import read_page, screenshot
from .tools.recording import (
    recording_drain,
    recording_drain_session,
    recording_extract_params,
    recording_install_capture,
    recording_list,
    recording_load,
    recording_replay,
    recording_save,
    recording_start_session,
    recording_stop_session,
)
from .tools.scheduling import schedule_add, schedule_list, schedule_remove

_PRIMITIVES = (
    set_skill_context,
    chrome_attach,
    chrome_new_window,
    chrome_find_or_open_window,
    chrome_close_window,
    navigate,
    wait_for,
    scroll,
    click,
    type_text,
    read_page,
    screenshot,
    extract,
    page_evaluate,
    powerbi_discover_fields,
    powerbi_set_filter,
    recording_save,
    recording_load,
    recording_list,
    recording_start_session,
    recording_drain_session,
    recording_stop_session,
    recording_install_capture,
    recording_drain,
    recording_replay,
    recording_extract_params,
    notify_slack,
    notify_teams,
    notify_email,
    schedule_list,
    schedule_add,
    schedule_remove,
)


def _wrap_with_logging(fn):
    """Wrap a tool function so every call appends a JSONL event via run_logger."""
    tool_name = getattr(fn, "__name__", repr(fn))

    if inspect.iscoroutinefunction(fn):

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            call_args = {"args": list(args), "kwargs": dict(kwargs)} if args else dict(kwargs)
            start = time.perf_counter()
            with run_logger() as log:
                try:
                    result = await fn(*args, **kwargs)
                    return result
                finally:
                    duration_ms = int((time.perf_counter() - start) * 1000)
                    summary = repr(locals().get("result", None))[:200]
                    log(tool_name, call_args, summary, duration_ms)

        return async_wrapper

    @functools.wraps(fn)
    def sync_wrapper(*args, **kwargs):
        call_args = {"args": list(args), "kwargs": dict(kwargs)} if args else dict(kwargs)
        start = time.perf_counter()
        with run_logger() as log:
            try:
                result = fn(*args, **kwargs)
                return result
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                summary = repr(locals().get("result", None))[:200]
                log(tool_name, call_args, summary, duration_ms)

    return sync_wrapper


def _build_server():
    server = FastMCP("browsermcp")
    for fn in _PRIMITIVES:
        wrapped = _wrap_with_logging(fn)
        server.tool()(wrapped)
    return server


def check_health() -> dict:
    """Report Python version, telemetry env, and Chrome CDP reachability."""
    return {
        "python_version": sys.version.split()[0],
        "anonymized_telemetry": os.environ.get("ANONYMIZED_TELEMETRY"),
        "chrome_reachable": _chrome_reachable(),
    }


def _chrome_reachable(host: str = "127.0.0.1", port: int = 9222) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1.0)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def main() -> None:
    """Run the BrowserMCP FastMCP server on stdio."""
    health = check_health()
    if health.get("anonymized_telemetry") != "false":
        raise SystemExit(
            "Refusing to start: ANONYMIZED_TELEMETRY must be 'false' "
            f"(got {health.get('anonymized_telemetry')!r}). "
            "BrowserMCP disables browser_use telemetry by policy."
        )
    if not health.get("chrome_reachable"):
        print(
            "Warning: Chrome CDP endpoint not reachable on 127.0.0.1:9222. "
            "Start Chrome with --remote-debugging-port=9222 before using chrome_attach.",
            file=sys.stderr,
        )

    server = _build_server()
    server.run()


if __name__ == "__main__":
    main()

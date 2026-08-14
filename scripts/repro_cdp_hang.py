"""Standalone CDP-hang repro for browsermcp / Chrome 149+.

Usage:
    DEBUG=pw:protocol .venv/bin/python scripts/repro_cdp_hang.py 2>&1 | tee /tmp/cdp.log

The script spins a Flask app on a random localhost port, attaches to the
running Chrome at --cdp-port via Playwright, opens a tab, and tries page.goto
with a configurable wait_until. On hang it prints readyState + current URL
and exits 1 — never blocks forever. Use the triage flags to bisect the cause.

Triage matrix:
    --wait-until commit          (skip the load-event wait — does CDP at least commit?)
    --wait-until domcontentloaded (default — what navigate() uses)
    --wait-until load             (full page load)
    --fresh-context               (browser.new_context() instead of contexts[0])
    --url https://example.com     (skip the local Flask — was loopback the issue?)
"""
from __future__ import annotations

import argparse
import asyncio
import socket
import sys
import threading
import time


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"port never came up: {host}:{port}")


def _start_flask() -> str:
    from flask import Flask

    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return (
            "<!doctype html><html><head><title>Repro</title></head>"
            "<body>Hello from Flask</body></html>"
        )

    port = _find_free_port()

    def _run() -> None:
        app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

    threading.Thread(target=_run, daemon=True, name="repro-flask").start()
    _wait_for_port("127.0.0.1", port)
    return f"http://127.0.0.1:{port}"


async def _run_repro(args: argparse.Namespace) -> int:
    from playwright.async_api import TimeoutError as PWTimeoutError
    from playwright.async_api import async_playwright

    if args.url:
        target_url = args.url
    else:
        target_url = f"{_start_flask()}/"

    print(f"target           : {target_url}")
    print(f"wait_until       : {args.wait_until}")
    print(f"fresh-context    : {args.fresh_context}")
    print(f"chrome cdp       : http://127.0.0.1:{args.cdp_port}")
    print(f"goto timeout (s) : {args.timeout}")

    pw = await async_playwright().start()
    try:
        attach_started = time.monotonic()
        browser = await asyncio.wait_for(
            pw.chromium.connect_over_cdp(f"http://127.0.0.1:{args.cdp_port}"),
            timeout=10,
        )
        print(f"connected        : {int((time.monotonic() - attach_started) * 1000)} ms")

        if args.fresh_context:
            context = await browser.new_context()
        elif browser.contexts:
            context = browser.contexts[0]
        else:
            context = await browser.new_context()

        page = await context.new_page()
        goto_started = time.monotonic()
        try:
            await asyncio.wait_for(
                page.goto(
                    target_url,
                    timeout=int(args.timeout * 1000),
                    wait_until=args.wait_until,
                ),
                timeout=args.timeout + 2.0,
            )
        except (asyncio.TimeoutError, PWTimeoutError) as exc:
            elapsed = time.monotonic() - goto_started
            try:
                ready = await asyncio.wait_for(
                    page.evaluate("() => document.readyState"), timeout=1.0
                )
            except Exception:
                ready = "<unknown>"
            current_url = page.url or "<unknown>"
            print(
                f"HUNG after {elapsed:.1f}s; readyState={ready!r}, "
                f"url={current_url!r}; cause={type(exc).__name__}: {exc}"
            )
            return 1

        elapsed = time.monotonic() - goto_started
        print(f"OK in {elapsed:.2f}s")
        try:
            title = await asyncio.wait_for(page.title(), timeout=2.0)
        except Exception as exc:
            title = f"<title fetch failed: {exc}>"
        print(f"title            : {title!r}")
        return 0
    finally:
        try:
            await pw.stop()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Probe Chrome 149+ CDP navigate hang.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--cdp-port", type=int, default=9222,
        help="Chrome remote-debugging port (default 9222)",
    )
    parser.add_argument(
        "--wait-until",
        choices=("load", "domcontentloaded", "commit", "networkidle"),
        default="domcontentloaded",
        help="page.goto wait_until value (default domcontentloaded)",
    )
    parser.add_argument(
        "--fresh-context", action="store_true",
        help="Use browser.new_context() instead of reusing contexts[0]",
    )
    parser.add_argument(
        "--url", default=None,
        help="Navigate to this URL instead of the local Flask repro",
    )
    parser.add_argument(
        "--timeout", type=float, default=15.0,
        help="Per-call goto timeout in seconds (default 15)",
    )
    args = parser.parse_args()
    return asyncio.run(_run_repro(args))


if __name__ == "__main__":
    sys.exit(main())

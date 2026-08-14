"""Load recent BrowserMCP tool-call runs from ~/.browsermcp/runs/*.jsonl.

Each `r-<hex>.jsonl` file is one run; each line is one tool call written by
`browsermcp/logging_jsonl.py`. Every line has the same flat shape:

    {"t", "run_id", "skill", "tool", "args", "result_summary", "duration_ms"}

This module aggregates per-file events into a single run summary the UI can
drop into a table, and also keeps the full event list around for the
drilldown. PII has already been redacted at write time, but every string we
return passes through `safe_text()` again as defense in depth (in case a log
was hand-edited or a future tool wrote unredacted content).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from browsermcp.config import RUNS_DIR

from .redaction import safe_text, safe_value

# Substrings that indicate a failed tool call (matched against the stringified
# `result_summary` field). Same list /flows-list uses so the two surfaces stay
# consistent.
_ERROR_MARKERS = ("ok=False", '"ok": false', "Error", "Traceback", "confirmation_required")


def _classify_status(result_summary: str) -> str:
    """Return "error" if any marker is present, else "ok"."""
    if any(marker in result_summary for marker in _ERROR_MARKERS):
        return "error"
    return "ok"


def _format_duration(ms: int) -> str:
    """Render a duration in ms as a compact human string ("4.3s" or "1m 12s")."""
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remainder = int(seconds % 60)
    return f"{minutes}m {remainder}s"


def _parse_run_file(path: Path) -> dict[str, Any] | None:
    """Read one r-*.jsonl file and return a run summary. None if unreadable."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    events: list[dict[str, Any]] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError:
            # Fail soft per row, not per file.
            continue

    if not events:
        return None

    # Per-event status, summed for the run.
    statuses = []
    total_duration = 0
    for ev in events:
        result = ev.get("result_summary", "")
        if isinstance(result, str):
            statuses.append(_classify_status(result))
        else:
            statuses.append("ok")
        dur = ev.get("duration_ms", 0)
        if isinstance(dur, (int, float)):
            total_duration += int(dur)
    overall_status = "error" if "error" in statuses else "ok"

    # Pick the most-recent timestamp from the file's events; fall back to mtime.
    try:
        latest_t = max(ev.get("t", "") for ev in events if ev.get("t"))
    except ValueError:
        latest_t = ""
    timestamp = latest_t or datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    ).isoformat().replace("+00:00", "Z")

    # Skill name: first non-null skill seen in any event.
    skill: str | None = None
    for ev in events:
        s = ev.get("skill")
        if s:
            skill = s
            break

    run_id = events[0].get("run_id") or path.stem

    # Redact every event before exposing it to the UI layer.
    redacted_events = [safe_value(ev) for ev in events]

    return {
        "run_id": run_id,
        "skill": skill or "<ad-hoc>",
        "timestamp": timestamp,
        "timestamp_pretty": _pretty_timestamp(timestamp),
        "tool_count": len(events),
        "status": overall_status,
        "duration_ms": total_duration,
        "duration_pretty": _format_duration(total_duration),
        "path": str(path),
        "events": redacted_events,
    }


def _pretty_timestamp(iso: str) -> str:
    """Render an ISO timestamp as `YYYY-MM-DD HH:MM` in local time."""
    if not iso:
        return ""
    try:
        # Tolerate both `Z` and `+00:00` suffixes.
        normalized = iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        return safe_text(iso)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M")


def load_recent_runs(limit: int = 100, since_days: int = 30) -> list[dict[str, Any]]:
    """Walk ~/.browsermcp/runs/*.jsonl and return up to `limit` runs newest-first.

    Skips files whose mtime is older than `since_days` (default 30 — matches
    the retention contract documented in docs/security.md). Skips files whose
    content can't be parsed as a run.
    """
    runs_dir = Path(os.path.expanduser(str(RUNS_DIR)))
    if not runs_dir.exists():
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp()
    candidates = []
    for path in runs_dir.glob("r-*.jsonl"):
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime < cutoff:
            continue
        candidates.append((mtime, path))
    candidates.sort(key=lambda x: x[0], reverse=True)

    out: list[dict[str, Any]] = []
    for _mtime, path in candidates:
        summary = _parse_run_file(path)
        if summary is None:
            continue
        out.append(summary)
        if len(out) >= limit:
            break
    return out

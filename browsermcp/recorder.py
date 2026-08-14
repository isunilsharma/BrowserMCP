"""Phase 3 scaffold for /record-flow.

Public API:
    save_recording(name, events) -> Path
    load_recording(name) -> Recording
    list_recordings() -> list[str]

This module ships the **storage layer only**. The actual event capture (clicks,
keystrokes, semantic actions) is Phase 4 work — see docs/phase4-record-replay.md
for the design. Today the /record-flow skill calls save_recording() with a list
of snapshot dicts the user tagged manually in chat.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from .redact import redact

RECORDINGS_DIR = Path(os.path.expanduser("~/.browsermcp/recordings"))

# Same kebab-case rule used by /save-as-flow and /create-flow for skill names.
# Rejects "../foo", absolute paths, slashes, and anything that could escape RECORDINGS_DIR.
_VALID_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}[a-z0-9]$")


def _validate_name(name: str) -> None:
    if not isinstance(name, str) or not _VALID_NAME_RE.fullmatch(name):
        raise ValueError(
            f"Invalid recording name {name!r}: must be kebab-case, 2-40 chars, "
            f"[a-z0-9-] only, no slashes or path components."
        )


class RecordingEvent(BaseModel):
    timestamp: str
    kind: str  # "snapshot" | "navigate" | "click" | "input" | "type" | "key"
    description: str | None = None
    url: str | None = None
    title: str | None = None
    text_excerpt: str | None = None  # first ~500 chars of read_page text
    # Phase 4 capture fields (all optional for backwards compat with Phase 3 recordings)
    role: str | None = None
    tag: str | None = None
    field: str | None = None
    value: str | None = None
    # Phase 4 v0.2 — which tab this event came from (Option C multi-tab)
    window_id: str | None = None
    # Phase 4 v0.3 — distinguishes load / popstate / pushState / replaceState
    nav_source: str | None = None


class Recording(BaseModel):
    name: str
    created_at: str
    events: list[RecordingEvent]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _redact_for_recording(event: dict) -> dict:
    """Redact an event WITHOUT mangling input.value.

    The generic redact() rewrites emails/phones/SSN/CC in string values to
    placeholder strings (e.g. 'alice@x.com' → '<email>'). That's correct for
    log lines but BREAKS recording playback: replay types the literal
    placeholder into the form field. So for kind='input' events we preserve
    `value` verbatim and only redact other fields. The client-side recorder
    already filters password fields before they reach Python.
    """
    if not isinstance(event, dict):
        return event
    if event.get("kind") == "input":
        # Preserve value verbatim; redact everything else (description, field, url, etc.)
        preserved_value = event.get("value")
        event_copy = {k: v for k, v in event.items() if k != "value"}
        redacted = redact(event_copy)
        if preserved_value is not None:
            redacted["value"] = preserved_value
        return redacted
    # For non-input events (click, navigate, snapshot), full redaction is safe.
    return redact(event)


def save_recording(name: str, events: list[dict]) -> Path:
    """Write a recording to ~/.browsermcp/recordings/<name>.jsonl. Returns the path.

    The first line is a meta record with {"meta": {"name": ..., "created_at": ...}}.
    Each subsequent line is one event. Events are passed through
    _redact_for_recording() which preserves input.value (so replay works) while
    masking PII in every other string.
    """
    _validate_name(name)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    path = RECORDINGS_DIR / f"{name}.jsonl"
    meta = {"meta": {"name": name, "created_at": _now_iso()}}
    redacted = [_redact_for_recording(e) for e in events]
    with path.open("w") as f:
        f.write(json.dumps(meta) + "\n")
        for e in redacted:
            f.write(json.dumps(e) + "\n")
    return path


def load_recording(name: str) -> Recording:
    """Read a recording from disk. Raises FileNotFoundError if missing."""
    _validate_name(name)
    path = RECORDINGS_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No recording named {name!r} at {path}")
    lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

    # First line MAY be a meta header (new format). Older files start straight with events.
    created_at: str
    event_lines: list[dict]
    if lines and isinstance(lines[0], dict) and "meta" in lines[0]:
        created_at = lines[0]["meta"].get("created_at", _now_iso())
        event_lines = lines[1:]
    else:
        created_at = _now_iso()
        event_lines = lines

    # Defense in depth: redact on load too (same input-value preservation rule)
    # in case a recording was hand-edited or written by a non-recorder path.
    redacted_events = [_redact_for_recording(e) for e in event_lines]
    return Recording(
        name=name,
        created_at=created_at,
        events=[RecordingEvent(**e) for e in redacted_events],
    )


def list_recordings() -> list[str]:
    """Return the names of all saved recordings."""
    if not RECORDINGS_DIR.exists():
        return []
    return sorted(p.stem for p in RECORDINGS_DIR.glob("*.jsonl"))

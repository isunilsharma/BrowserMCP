"""MCP tool wrappers for /record-flow.

Two modes co-exist:
  • Session mode (Option C) — multi-tab, fresh anchor tab.
      recording_start_session()  → opens anchor tab, injects all existing tabs
      recording_drain_session()  → sweeps all tracked tabs for events
      recording_stop_session()   → final drain, removes listener, returns events
  • Single-tab mode (backwards compat) — original v0.1 API.
      recording_install_capture(window_id)
      recording_drain(window_id)

Both modes share the same save/load/list/replay/extract-params layer.
"""

from __future__ import annotations

from ..recorder import (
    Recording,
    load_recording,
    list_recordings,
    save_recording,
)
from ..recording_capture import (
    install_recorder,
    drain_events,
    start_recording_session,
    drain_session_events,
    stop_recording_session,
)
from ..recording_replay import replay_recording
from ..recording_params import extract_parameters


# ── Session mode (Option C) ───────────────────────────────────────────────────

async def recording_start_session() -> dict:
    """Open a fresh anchor tab, inject the recorder into all open tabs, and
    hook new tabs as they open. Returns the anchor_window_id the user should
    start their task from, plus existing_tabs count.

    Call this instead of recording_install_capture when you want multi-tab
    capture (Option C UX).
    """
    return await start_recording_session()


async def recording_drain_session() -> dict:
    """Sweep all tracked tabs and return events captured since the last drain.
    Re-injects into any tab that lost JS state due to a full page reload."""
    events = await drain_session_events()
    kinds: dict[str, int] = {}
    for e in events:
        k = e.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1
    return {"events": events, "count": len(events), "by_kind": kinds}


async def recording_stop_session() -> dict:
    """Final drain, remove the new-page listener, clear the session.
    Returns all events captured across all tabs this session."""
    events = await stop_recording_session()
    return {"events": events, "count": len(events)}


# ── Single-tab mode (backwards compat) ───────────────────────────────────────

async def recording_install_capture(window_id: str) -> dict:
    """Inject the event recorder into a single registered window. Idempotent."""
    return await install_recorder(window_id)


async def recording_drain(window_id: str) -> dict:
    """Drain and return all events captured in a single window since last drain."""
    events = await drain_events(window_id)
    return {"events": events, "count": len(events)}


# ── Shared layer ──────────────────────────────────────────────────────────────

async def recording_save(name: str, events: list[dict]) -> dict:
    """Persist a recording at ~/.browsermcp/recordings/<name>.jsonl."""
    path = save_recording(name, events)
    return {"ok": True, "path": str(path), "events": len(events)}


async def recording_load(name: str) -> dict:
    """Read a recording back as a dict."""
    rec: Recording = load_recording(name)
    return rec.model_dump()


async def recording_list() -> dict:
    """List all saved recordings by name."""
    return {"recordings": list_recordings()}


async def recording_replay(name: str, window_id: str) -> dict:
    """Replay a saved recording. Returns per-step results."""
    results = await replay_recording(name, window_id)
    return {"name": name, "steps": results, "total": len(results)}


async def recording_extract_params(events: list[dict]) -> dict:
    """Extract parameter suggestions from a list of recorded events."""
    params = extract_parameters(events)
    return {"parameters": [p.model_dump() for p in params]}


__all__ = [
    # Session mode
    "recording_start_session",
    "recording_drain_session",
    "recording_stop_session",
    # Single-tab compat
    "recording_install_capture",
    "recording_drain",
    # Shared
    "recording_save",
    "recording_load",
    "recording_list",
    "recording_replay",
    "recording_extract_params",
]

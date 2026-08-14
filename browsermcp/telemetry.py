"""Phase 5 telemetry stub.

Opt-in only (config.telemetry_opt_in must be True). Even when opted in,
this v0 implementation is a NO-OP — it writes to a local file at
~/.browsermcp/telemetry.jsonl instead of phoning home. A real backend
arrives post-IT review.
"""
from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .config import load_settings
from .redact import redact

TELEMETRY_FILE = Path(os.path.expanduser("~/.browsermcp/telemetry.jsonl"))


def emit(event_type: str, properties: dict) -> bool:
    """Record a telemetry event. Returns True if recorded, False if opted out."""
    settings = load_settings()
    if not settings.telemetry_opt_in:
        return False
    TELEMETRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "t": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event_type,
        "properties": redact(properties),
    }
    with TELEMETRY_FILE.open("a") as f:
        f.write(json.dumps(record) + "\n")
    return True

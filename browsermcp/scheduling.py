"""Phase 4 scheduling registry (no execution layer yet).

Persists scheduled runs to ~/.browsermcp/schedules.toml. The actual cron
execution is deferred until the service-account vs persistent-profile
decision lands. For now this is storage + listing only.
"""
from __future__ import annotations
import os
from pathlib import Path
from pydantic import BaseModel

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import tomli_w  # write-side

SCHEDULES_FILE = Path(os.path.expanduser("~/.browsermcp/schedules.toml"))


class ScheduledRun(BaseModel):
    skill_name: str
    args: dict
    cron: str            # e.g. "0 9 * * 1-5"
    interactive: bool = True
    enabled: bool = True


def _load_raw() -> dict:
    if not SCHEDULES_FILE.exists():
        return {"schedules": []}
    with SCHEDULES_FILE.open("rb") as f:
        return tomllib.load(f) or {"schedules": []}


def list_scheduled() -> list[ScheduledRun]:
    raw = _load_raw()
    return [ScheduledRun(**e) for e in raw.get("schedules", [])]


def add_scheduled(run: ScheduledRun) -> None:
    SCHEDULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    raw = _load_raw()
    raw.setdefault("schedules", []).append(run.model_dump())
    with SCHEDULES_FILE.open("wb") as f:
        tomli_w.dump(raw, f)


def remove_scheduled(skill_name: str, cron: str) -> bool:
    raw = _load_raw()
    before = len(raw.get("schedules", []))
    raw["schedules"] = [
        e for e in raw.get("schedules", [])
        if not (e.get("skill_name") == skill_name and e.get("cron") == cron)
    ]
    after = len(raw["schedules"])
    if after != before:
        with SCHEDULES_FILE.open("wb") as f:
            tomli_w.dump(raw, f)
        return True
    return False

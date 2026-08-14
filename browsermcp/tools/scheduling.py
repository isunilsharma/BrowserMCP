"""MCP tool wrappers around browsermcp.scheduling.

These are thin async wrappers that Claude Code skills can invoke. The
underlying `scheduling` module is registry-only: it persists scheduled-run
entries to ~/.browsermcp/schedules.toml but does NOT execute anything on a
cron. The execution layer is deferred until the service-account vs
persistent-profile decision lands.
"""

from __future__ import annotations

from ..scheduling import (
    ScheduledRun,
    add_scheduled,
    list_scheduled,
    remove_scheduled,
)


async def schedule_list() -> dict:
    """List all scheduled runs currently in the registry.

    Returns {"schedules": [<ScheduledRun.model_dump()>, ...], "count": N}.
    Reads from ~/.browsermcp/schedules.toml; returns an empty list if the
    file does not yet exist.
    """
    runs = list_scheduled()
    return {
        "schedules": [r.model_dump() for r in runs],
        "count": len(runs),
    }


async def schedule_add(
    skill_name: str,
    args: dict,
    cron: str,
    interactive: bool = True,
    enabled: bool = True,
) -> dict:
    """Add a new scheduled run to the registry.

    Args:
        skill_name: The Claude Code skill to invoke (e.g. "powerbi-scan").
        args: Dict of arguments to pass to the skill on each run.
        cron: Standard 5-field cron expression (e.g. "0 9 * * 1-5").
        interactive: Whether the run expects a user-attended Chrome session.
            Defaults to True; non-interactive (service-account) runs are
            blocked until the execution layer lands.
        enabled: Whether the entry is active. Defaults to True.

    Returns {"ok": True, "scheduled": <ScheduledRun.model_dump()>}.

    Note: This only writes to the registry. No cron job is installed and
    no run is actually triggered yet — the execution layer is deferred.
    """
    run = ScheduledRun(
        skill_name=skill_name,
        args=args,
        cron=cron,
        interactive=interactive,
        enabled=enabled,
    )
    add_scheduled(run)
    return {"ok": True, "scheduled": run.model_dump()}


async def schedule_remove(skill_name: str, cron: str) -> dict:
    """Remove a scheduled run from the registry by (skill_name, cron) key.

    Returns {"ok": True, "removed": True} if a matching entry was found
    and dropped, or {"ok": True, "removed": False} if nothing matched.
    Multiple matches (same skill + cron) are all removed.
    """
    removed = remove_scheduled(skill_name, cron)
    return {"ok": True, "removed": removed}


__all__ = [
    "schedule_list",
    "schedule_add",
    "schedule_remove",
]

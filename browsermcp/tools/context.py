"""MCP tool that lets a Claude Code skill tag the current run with its name.

Skills should call `set_skill_context(skill="<name>")` as their first action so
that the JSONL run logs are attributed to the right skill instead of
`<ad-hoc>`. See `browsermcp/_context.py` for the underlying store.
"""

from __future__ import annotations

from .. import _context


async def set_skill_context(skill: str) -> dict:
    """Record the currently-executing Claude Code skill name.

    Stashes `skill` in the module-level context so every subsequent log line
    written by `run_logger` is tagged with it. The next `set_skill_context`
    call (from the next skill invocation) overwrites the value — we
    deliberately do NOT auto-reset between MCP tool calls.

    Args:
        skill: The skill's canonical name (e.g. "powerbi-scan").

    Returns:
        A dict echoing the skill name and an ok flag, suitable for an MCP
        tool response.
    """
    _context.set_current_skill(skill)
    return {"skill": skill, "ok": True}

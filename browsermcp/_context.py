"""Module-level current-skill context for BrowserMCP run attribution.

The MCP server wraps every tool call in `run_logger` (see `logging_jsonl.py`),
but the wrapper has no in-band signal telling it *which* Claude Code skill is
currently executing. To bridge that gap, skills call `set_skill_context` (their
first action), which stashes the skill name here. The logger then reads it back
at log time so every JSONL line is correctly attributed.

The context is process-global and intentionally *not* auto-reset between MCP
tool calls: a single skill run usually fires many tool calls, and we want every
one of them tagged with the same skill. The next `set_skill_context` call (from
the next skill invocation) overwrites the value.

`get_current_skill` also honors an `BROWSERMCP_SKILL` environment variable as a
fallback so external launchers (cron, headless wrappers) can tag runs without
making an MCP call.
"""

from __future__ import annotations

import os

_CURRENT_SKILL: str | None = None


def get_current_skill() -> str | None:
    """Return the active skill name, or None if no skill has tagged itself.

    Prefers the in-process value set by `set_skill_context`. Falls back to the
    `BROWSERMCP_SKILL` environment variable so external launchers can tag runs
    even when no skill explicitly calls `set_skill_context`.
    """
    if _CURRENT_SKILL is not None:
        return _CURRENT_SKILL
    env_value = os.environ.get("BROWSERMCP_SKILL")
    if env_value:
        return env_value
    return None


def set_current_skill(name: str | None) -> None:
    """Set (or clear) the active skill name for subsequent log lines."""
    global _CURRENT_SKILL
    _CURRENT_SKILL = name

"""Tool function re-exports for the BrowserMCP server."""

from __future__ import annotations

from .chrome import (
    chrome_attach,
    chrome_close_window,
    chrome_find_or_open_window,
    chrome_new_window,
)
from .context import set_skill_context
from .extraction import extract
from .interaction import click, type_text
from .navigation import navigate, scroll, wait_for
from .notify import notify_email, notify_slack, notify_teams
from .reading import read_page, screenshot
from .recording import (
    recording_drain,
    recording_extract_params,
    recording_install_capture,
    recording_list,
    recording_load,
    recording_replay,
    recording_save,
)
from .scheduling import schedule_add, schedule_list, schedule_remove

__all__ = [
    "chrome_attach",
    "chrome_new_window",
    "chrome_find_or_open_window",
    "chrome_close_window",
    "navigate",
    "wait_for",
    "scroll",
    "click",
    "type_text",
    "read_page",
    "screenshot",
    "extract",
    "set_skill_context",
    "recording_save",
    "recording_load",
    "recording_list",
    "recording_install_capture",
    "recording_drain",
    "recording_replay",
    "recording_extract_params",
    "notify_slack",
    "notify_teams",
    "notify_email",
    "schedule_list",
    "schedule_add",
    "schedule_remove",
]

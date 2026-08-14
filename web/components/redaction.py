"""Thin wrapper around browsermcp.redact for the Streamlit UI.

Every string that the UI is about to render goes through `safe_text()` first.
Dicts and lists go through `safe_value()`. Both delegate to the upstream
`browsermcp.redact.redact()` which already understands emails, phones, SSNs,
credit card numbers, and sensitive dict keys (password, token, ssn, dob, etc).

We re-export the upstream symbols rather than re-implementing the regexes — the
single source of truth is `browsermcp/redact.py`, which is also used by the
logger at write-time. This wrapper exists so pages don't have to import the
private `_redact_str` helper directly, and so we have a single line to change
if we add UI-only redaction (e.g. truncating very long URLs) later.
"""

from __future__ import annotations

from typing import Any

from browsermcp.redact import _redact_str, redact


def safe_text(value: str | None) -> str:
    """Redact a single string for on-screen rendering.

    Returns the empty string for None so callers can drop the result straight
    into a Streamlit widget without a None check.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return _redact_str(value)


def safe_value(value: Any) -> Any:
    """Redact an arbitrary structure (dict / list / scalar) for on-screen use.

    Pass-through delegate to `browsermcp.redact.redact()`. Use this for
    anything heading into `st.json` or `st.dataframe`.
    """
    return redact(value)

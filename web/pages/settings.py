"""Settings page — read-only Settings view + webhook env-var validator.

We never POST anything from this page. The "Test webhooks" section only
verifies that the env vars exist and their hostnames match the host
allowlist enforced by `browsermcp.notify` (`hooks.slack.com` for Slack,
`*.webhook.office.com` / `*.outlook.com` for Teams). The actual `send_*`
calls run in dry-run mode — we just call `_validate_text` to confirm the
text path works, and inspect the URL.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

import streamlit as st

from browsermcp.config import CONFIG_DIR, CONFIG_FILE, RUNS_DIR, load_settings
from browsermcp.notify import _SLACK_HOST, _TEAMS_HOST_SUFFIXES, _validate_text

from web.components.redaction import safe_text


def _validate_slack_url(url: str) -> tuple[bool, str]:
    """Return (ok, message) for the Slack webhook URL allowlist check."""
    if not url:
        return False, "No SLACK_WEBHOOK_URL env var set."
    host = urlparse(url).hostname or ""
    if host != _SLACK_HOST:
        return False, f"Host {host!r} not allowed — Slack webhooks must use {_SLACK_HOST!r}."
    return True, f"URL hostname {host!r} matches the Slack allowlist."


def _validate_teams_url(url: str) -> tuple[bool, str]:
    if not url:
        return False, "No TEAMS_WEBHOOK_URL env var set."
    host = urlparse(url).hostname or ""
    if not any(host.endswith(s) for s in _TEAMS_HOST_SUFFIXES):
        return False, (
            f"Host {host!r} not allowed — Teams webhooks must end with "
            f"one of {_TEAMS_HOST_SUFFIXES}."
        )
    return True, f"URL hostname {host!r} matches the Teams allowlist."


def render() -> None:
    st.title("Settings")
    st.caption(
        "Live `browsermcp.config.Settings`. Read-only here — edit "
        f"`{safe_text(str(CONFIG_FILE))}` to change values."
    )

    settings = load_settings()

    col1, col2 = st.columns(2)
    col1.metric("Chrome CDP port", settings.chrome_port)
    col2.metric("Log retention (days)", settings.log_retention_days)

    col3, col4 = st.columns(2)
    col3.metric("Max tool calls / run", settings.max_tool_calls_per_run)
    col4.metric("Telemetry opt-in", str(settings.telemetry_opt_in))

    st.markdown("**Config locations**")
    st.markdown(
        f"- Config dir: `{safe_text(str(CONFIG_DIR))}`\n"
        f"- Config file: `{safe_text(str(CONFIG_FILE))}` "
        f"({'exists' if CONFIG_FILE.exists() else 'missing — defaults in use'})\n"
        f"- Runs dir: `{safe_text(str(RUNS_DIR))}`"
    )

    st.subheader("Allowed hosts")
    st.caption(
        "URLs whose hostname matches one of these patterns may be visited by "
        "`navigate()`. Anything else raises an error before Chrome ever sees it."
    )
    for pattern in settings.allowed_hosts:
        st.markdown(f"- `{safe_text(pattern)}`")

    st.divider()
    st.subheader("Test webhooks (dry-run)")
    st.caption(
        "Validates that your `SLACK_WEBHOOK_URL` and `TEAMS_WEBHOOK_URL` env "
        "vars are set and their hostnames are allowed by `browsermcp.notify`. "
        "Nothing is POSTed."
    )

    slack_url = os.environ.get("SLACK_WEBHOOK_URL", "")
    teams_url = os.environ.get("TEAMS_WEBHOOK_URL", "")

    with st.expander("Slack webhook", expanded=False):
        if st.button("Validate Slack webhook", key="validate_slack"):
            ok, msg = _validate_slack_url(slack_url)
            if ok:
                # Also exercise the redaction code path on a canned message,
                # so the user gets full confidence the send path would work.
                try:
                    _validate_text("BrowserMCP dry-run validation")
                    st.success(f"{msg}\nText validator passed (no POST issued).")
                except ValueError as e:
                    st.error(f"Text validator failed: {e}")
            else:
                st.warning(msg)
        else:
            st.caption(
                "Click to confirm the env var is set and the host is allowed."
            )

    with st.expander("Teams webhook", expanded=False):
        if st.button("Validate Teams webhook", key="validate_teams"):
            ok, msg = _validate_teams_url(teams_url)
            if ok:
                try:
                    _validate_text("BrowserMCP dry-run validation")
                    st.success(f"{msg}\nText validator passed (no POST issued).")
                except ValueError as e:
                    st.error(f"Text validator failed: {e}")
            else:
                st.warning(msg)
        else:
            st.caption(
                "Click to confirm the env var is set and the host is allowed."
            )


render()

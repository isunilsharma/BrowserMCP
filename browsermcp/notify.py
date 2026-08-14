"""Phase 4 output piping helpers.

Each function POSTs to a webhook URL (Slack/Teams) or sends an SMTP email.
Webhook URL host is validated against an allowlist; payload text is
redacted via browsermcp.redact._redact_str() before being sent.

Reads webhook URL from arg OR from env var fallback:
  - SLACK_WEBHOOK_URL
  - TEAMS_WEBHOOK_URL
  - SMTP_HOST / SMTP_PORT / SMTP_FROM (for send_email)

SECURITY HARDENING (post-review):
- title args are passed through _validate_text (redacted + length-capped)
- email `to` validated against an email regex
- Teams webhook accepts ONLY *.webhook.office.com (NOT *.outlook.com, which
  is consumer-mail and not where Teams webhooks live)
- SMTP host accepted only if it ends with one of _SMTP_HOST_SUFFIXES
  (default: corporate mail gateways). Pass an explicit override only
  if you really know what you're doing.
"""
from __future__ import annotations
import json
import os
import re
import smtplib
from email.mime.text import MIMEText
from urllib import request, parse
from urllib.error import URLError, HTTPError

from .redact import _redact_str

_SLACK_HOST = "hooks.slack.com"
_TEAMS_HOST_SUFFIXES = (".webhook.office.com",)  # NOT .outlook.com — that's consumer mail
# Placeholder corporate mail domains — replace with your own before use.
_SMTP_HOST_SUFFIXES = (".example.com", ".example.net", ".example.org")
_MAX_TEXT_CHARS = 4000

_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_text(text: str, label: str = "text") -> str:
    """Redact PII and cap length. Raises ValueError on empty/oversized."""
    if not text or len(text) > _MAX_TEXT_CHARS:
        raise ValueError(f"{label} must be 1..{_MAX_TEXT_CHARS} chars; got {len(text)}")
    return _redact_str(text)


def _validate_email(addr: str, label: str = "email") -> str:
    """Reject malformed addresses or anything with newlines (header-injection guard)."""
    if not addr or not _EMAIL_RE.fullmatch(addr) or "\n" in addr or "\r" in addr:
        raise ValueError(f"{label} is not a valid email address: {addr!r}")
    return addr


def send_slack(text: str, title: str | None = None,
               webhook_url: str | None = None) -> dict:
    url = webhook_url or os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        raise ValueError("No Slack webhook URL provided (arg or SLACK_WEBHOOK_URL env)")
    host = parse.urlparse(url).hostname or ""
    if host != _SLACK_HOST:
        raise ValueError(f"Slack webhook host must be {_SLACK_HOST!r}; got {host!r}")
    text = _validate_text(text, "text")
    if title is not None:
        title = _validate_text(title, "title")
    payload = {"text": (f"*{title}*\n{text}" if title else text)}
    req = request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            return {"ok": resp.status == 200, "status": resp.status}
    except (HTTPError, URLError) as e:
        return {"ok": False, "error": str(e)[:200]}


def send_teams(text: str, title: str | None = None,
               webhook_url: str | None = None) -> dict:
    url = webhook_url or os.environ.get("TEAMS_WEBHOOK_URL")
    if not url:
        raise ValueError("No Teams webhook URL provided (arg or TEAMS_WEBHOOK_URL env)")
    host = parse.urlparse(url).hostname or ""
    if not any(host.endswith(s) for s in _TEAMS_HOST_SUFFIXES):
        raise ValueError(
            f"Teams webhook host must end with one of {_TEAMS_HOST_SUFFIXES}; got {host!r}"
        )
    text = _validate_text(text, "text")
    if title is not None:
        title = _validate_text(title, "title")
    payload = {
        "@type": "MessageCard", "@context": "https://schema.org/extensions",
        "summary": title or "Notification", "text": text,
    }
    if title:
        payload["title"] = title
    req = request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with request.urlopen(req, timeout=10) as resp:
            return {"ok": resp.status == 200, "status": resp.status}
    except (HTTPError, URLError) as e:
        return {"ok": False, "error": str(e)[:200]}


def send_email(to: str, subject: str, body: str,
               smtp_host: str | None = None, smtp_port: int = 587,
               from_addr: str | None = None) -> dict:
    smtp_host = smtp_host or os.environ.get("SMTP_HOST")
    from_addr = from_addr or os.environ.get("SMTP_FROM")
    if not smtp_host or not from_addr:
        raise ValueError("smtp_host + from_addr required (or SMTP_HOST/SMTP_FROM env)")
    # SMTP-host allowlist — only corporate gateways. Otherwise a malicious
    # caller could relay mail through an arbitrary third-party SMTP server.
    if not any(smtp_host.endswith(s) for s in _SMTP_HOST_SUFFIXES):
        raise ValueError(
            f"smtp_host must end with one of {_SMTP_HOST_SUFFIXES} (corporate gateway); "
            f"got {smtp_host!r}"
        )
    to = _validate_email(to, "to")
    from_addr = _validate_email(from_addr, "from_addr")
    subject = _validate_text(subject, "subject")
    body = _validate_text(body, "body")
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.send_message(msg)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}

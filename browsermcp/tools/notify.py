"""MCP tool wrappers around browsermcp.notify."""
from __future__ import annotations
from ..notify import send_email, send_slack, send_teams

async def notify_slack(text: str, title: str | None = None,
                       webhook_url: str | None = None) -> dict:
    """POST a message to a Slack incoming webhook."""
    return send_slack(text, title=title, webhook_url=webhook_url)

async def notify_teams(text: str, title: str | None = None,
                       webhook_url: str | None = None) -> dict:
    """POST a message to a Microsoft Teams connector webhook."""
    return send_teams(text, title=title, webhook_url=webhook_url)

async def notify_email(to: str, subject: str, body: str,
                       smtp_host: str | None = None, smtp_port: int = 587,
                       from_addr: str | None = None) -> dict:
    """Send an email via SMTP (host + from_addr from arg or env)."""
    return send_email(to, subject, body, smtp_host=smtp_host,
                      smtp_port=smtp_port, from_addr=from_addr)

__all__ = ["notify_slack", "notify_teams", "notify_email"]

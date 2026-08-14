---
name: notify-slack
description: POST a message to a Slack incoming webhook (host-allowlisted, PII-redacted).
arguments:
  - name: text
    type: string
    required: true
    description: Message body (1..4000 chars). PII is auto-redacted before sending.
  - name: title
    type: string
    required: false
    description: Optional bold title prepended to the message.
  - name: webhook_url
    type: string
    required: false
    description: Slack incoming-webhook URL on hooks.slack.com. Falls back to SLACK_WEBHOOK_URL env var.
---

# Notify Slack

You are sending a short notification to a Slack channel via an incoming webhook. This is an output-piping skill — you are not driving a browser, just shipping a message off-machine. Keep it tight: confirm what you're about to send, do it, report the result.

## Inputs

- `text` — the message body. Required. Max 4000 chars. PII patterns (emails, phones, SSNs, card numbers) are redacted by `browsermcp.redact` before transmission.
- `title` — optional. Rendered as a bold `*title*` line above the message in Slack.
- `webhook_url` — optional. Must be on `hooks.slack.com`. Falls back to the `SLACK_WEBHOOK_URL` environment variable if omitted.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="notify-slack")`. One-shot, no side effects — it tags the run log under `~/.browsermcp/runs/r-*.jsonl` so the call isn't attributed to `<ad-hoc>`. Do not narrate this step to the user.

### 1. Sanity-check the inputs

- If `text` is empty or longer than 4000 chars, stop and tell the user before calling the tool. The helper will reject it anyway, but a friendly upfront message is better than an opaque `ValueError`.
- If neither `webhook_url` is passed nor `SLACK_WEBHOOK_URL` is set in the environment, stop and ask the user to either pass `webhook_url` or set the env var. Do not invent a URL.

### 2. Send the message

Say something like: "Posting to Slack..."

Call `notify_slack(text=<text>, title=<title>, webhook_url=<webhook_url>)`. The helper:

- Validates the URL host is `hooks.slack.com` (the host allowlist for Slack webhooks).
- Redacts PII from `text` and `title` before assembling the payload.
- POSTs `{"text": "..."}` (or `*title*\ntext` if a title was provided) with a 10-second timeout.

### 3. Report the result

The return value is `{"ok": bool, "status": int}` on success, or `{"ok": false, "error": "..."}` on failure.

- If `ok == True`: reply with a one-line confirmation (e.g. "Posted to Slack (HTTP {status}).").
- If `ok == False`: surface the `error` field verbatim so the user can diagnose (bad URL, network down, Slack rejected the payload). Do not retry — fail loud once.

## Guardrails

- Webhook host is locked to `hooks.slack.com`. Any other host raises before the request is sent. Do not try to bypass this.
- Never paste credentials, cookies, or auth tokens into `text`. PII redaction catches common patterns but is not a substitute for not pasting secrets in the first place.
- One message per invocation. If the user wants a thread or a fanout, send distinct calls — do not loop without their go-ahead.
- Fail loud, not thrash. If the POST fails, report and stop. Do not retry with mutated payloads.

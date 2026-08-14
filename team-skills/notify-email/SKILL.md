---
name: notify-email
description: Send an email via SMTP (host + from address from arg or env; subject/body PII-redacted).
arguments:
  - name: to
    type: string
    required: true
    description: Recipient email address.
  - name: subject
    type: string
    required: true
    description: Email subject (1..4000 chars). PII is auto-redacted before sending.
  - name: body
    type: string
    required: true
    description: Plain-text email body (1..4000 chars). PII is auto-redacted before sending.
  - name: smtp_host
    type: string
    required: false
    description: SMTP server hostname. Falls back to SMTP_HOST env var.
  - name: smtp_port
    type: integer
    default: 587
    description: SMTP port. Defaults to 587 (STARTTLS).
  - name: from_addr
    type: string
    required: false
    description: From address. Falls back to SMTP_FROM env var.
---

# Notify Email

You are sending a single plain-text email via SMTP. This is an output-piping skill — you are not driving a browser, just shipping a message off-machine. Keep it tight: confirm what you're about to send, do it, report the result.

## Inputs

- `to` — recipient address. Required.
- `subject` — email subject. Required. Max 4000 chars. PII redacted before send.
- `body` — plain-text body. Required. Max 4000 chars. PII redacted before send.
- `smtp_host` — SMTP server hostname. Falls back to the `SMTP_HOST` environment variable.
- `smtp_port` — SMTP port. Defaults to 587 (STARTTLS).
- `from_addr` — From address. Falls back to the `SMTP_FROM` environment variable.

## Flow

### 0. Tag this run with the skill name

Before anything else, call `set_skill_context(skill="notify-email")`. One-shot, no side effects — it tags the run log under `~/.browsermcp/runs/r-*.jsonl` so the call isn't attributed to `<ad-hoc>`. Do not narrate this step to the user.

### 1. Sanity-check the inputs

- If `subject` or `body` is empty or longer than 4000 chars, stop and tell the user before calling the tool. The helper will reject it anyway, but a friendly upfront message is better than an opaque `ValueError`.
- If neither `smtp_host` is passed nor `SMTP_HOST` is set, stop and ask the user to either pass the arg or set the env var. Same for `from_addr` / `SMTP_FROM`. Do not invent values.
- If `to` doesn't contain `@`, flag it as suspicious and confirm with the user before sending.

### 2. Send the email

Say something like: "Sending email via SMTP..."

Call `notify_email(to=<to>, subject=<subject>, body=<body>, smtp_host=<smtp_host>, smtp_port=<smtp_port>, from_addr=<from_addr>)`. The helper:

- Resolves `smtp_host` / `from_addr` from arg or env, raising `ValueError` if neither source supplies them.
- Redacts PII from `subject` and `body` before constructing the MIME message.
- Opens an SMTP connection with a 10-second timeout, calls `STARTTLS`, and sends the message.

### 3. Report the result

The return value is `{"ok": True}` on success, or `{"ok": False, "error": "<ExceptionType>: <message>"}` on failure.

- If `ok == True`: reply with a one-line confirmation (e.g. "Email sent to {to}.").
- If `ok == False`: surface the `error` field verbatim so the user can diagnose (auth failure, host unreachable, TLS handshake failed, recipient rejected). Do not retry — fail loud once.

## Guardrails

- This skill does not authenticate the SMTP connection beyond STARTTLS. If your SMTP server requires SMTP AUTH (login/password), use a relay that allows the sender's IP or extend the helper — do not paste credentials into args.
- Never paste credentials, cookies, or auth tokens into `subject` or `body`. PII redaction catches common patterns but is not a substitute for not pasting secrets in the first place.
- One email per invocation. If the user wants a fanout across recipients, send distinct calls — do not loop without their go-ahead.
- Plain text only — this skill does not send HTML or attachments. If the user asks for either, tell them and stop.
- Fail loud, not thrash. If the send fails, report and stop. Do not retry with mutated payloads.

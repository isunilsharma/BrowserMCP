# Acceptable Use

> What BrowserMCP is — and isn't — allowed to be used for on the team.

If you're considering installing BrowserMCP on your work machine, read this page first. It takes about three minutes and tells you what's in scope, what's hard-off-limits, and who to ask when you're unsure.

## What this tool is

BrowserMCP is an internal tool that lets Claude Code drive your own Chrome browser. It's aimed at the long tail of small-but-real automations inside the company — the work that lives in Power BI dashboards, Workday, ServiceNow, Salesforce, vendor portals, and similar systems where there's either no API or the API is gated behind a multi-month integration ticket. Instead of waiting for IT to build an integration, you describe the flow you want and Claude Code drives your existing SSO'd browser session to do it. Everything runs locally on your own machine, under your own identity, using credentials you already have.

## What you can do with it

- Automate repetitive UI tasks on internal sites you already have access to
- Read reports, search Confluence, triage Jira tickets, fill forms across sites
- Save personal flows to `~/.claude/skills/` for your own reuse
- Share flows with the team via `/promote-flow` (PR-reviewed)

## What you absolutely shouldn't do

- Scrape data you don't have permission to access (BrowserMCP runs as YOU — if a site lets you see something, it'll let the bot see it; you're accountable)
- Use it to bypass security controls (MFA, conditional access, manager approvals)
- Share your agent Chrome's session cookies or screenshots with anyone outside the company
- Share `/record-flow` recordings from `~/.browsermcp/recordings/` directly with teammates — they contain page text that, even after redaction, may carry internal information the recipient isn't cleared to see. Promote the *skill* via `/promote-flow` (which is reviewed); don't email the raw `.jsonl` file
- Automate against customer-facing apps (don't drive store.example.com via BrowserMCP)
- Use it for personal non-work tasks (no shopping bots, no personal Gmail automation)
- Send company data to external services without explicit approval (no slack-notify to a external workspace, no posting to public pastebins, etc.)
- Have BrowserMCP type your password — you sign in manually

## How auditing works

Every MCP tool call BrowserMCP makes is logged to `~/.browsermcp/runs/<run_id>.jsonl` on your own machine. The logs run through a PII redactor before they're written — emails, phones, SSNs, credit cards, and any field labeled `password|secret|token|ssn|dob` are masked. Each line records the tool that was called, the (redacted) arguments, a short result summary, and how long it took.

These logs are **local-only** — they don't ship to a central server. But "local" doesn't mean "private from your employer." If a security incident involves your account, these logs are discoverable as part of standard corporate incident response, the same way any file on your work machine is. They're retained for 30 days and then auto-deleted.

The practical upshot: treat the logs as your own paper trail. If something goes sideways with a flow you ran, the `run_id` in the chat is the breadcrumb that ties everything together.

## When in doubt, ask

If you're not sure whether something is OK, ask before you run it. The escalation path:

1. **Sunil Sharma** (@isunilsharma on GitHub) — project owner; fastest answer for "is this an OK use of the tool"
2. **Your manager** — for "is this an OK use of my time / my access"
3. **InfoSec** — for anything that smells like a policy or compliance question (data classification, third-party data sharing, regulated data, etc.)

There's no penalty for asking. There's a real penalty for running something you shouldn't have.

## Reporting incidents

If a skill behaves unexpectedly — clicks something it shouldn't have, reads from a page you didn't intend, sends data somewhere surprising:

1. **Stop running it.** Cancel the current chat / close the agent Chrome window.
2. **Capture the run_id** from the chat (it'll look like `r-abc12345`). The matching log file lives at `~/.browsermcp/runs/<run_id>.jsonl`.
3. **Message Sunil** (@isunilsharma on GitHub) with the run_id and a one-line description of what happened. Don't wait — even a "this looked weird" message is worth sending.

For anything that crosses into a **security incident** (data exposure, credential compromise, unauthorized access), don't route it through this project — follow the **standard corporate incident response process** and notify InfoSec directly. This project is a tool; security incident response is a company-wide process that takes precedence.

---
name: telegram-ingest-ops
description: Maintain HawkFi Telegram ingestion backing the hawkfi-telegram MCP: add/maintain allowlist chat_ids, install/restart/status the launchd daemon, and troubleshoot missing dialogs/messages/search results.
---

# telegram-ingest-ops

Operate the local Telegram ingestion service that backs the `hawkfi-telegram` MCP server.

## Use this skill when
- Adding more Telegram groups/channels to monitor (allowlist)
- Restarting the ingest daemon (launchd)
- Debugging “why TG data/search is empty”

## References
- MCP usage: `references/telegram-mcp.md`
- Allowlist + restart runbook: `references/allowlist-runbook.md`

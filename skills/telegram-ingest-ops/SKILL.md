---
name: telegram-ingest-ops
description: Operate HawkFi Telegram Service ingestion (allowlist chat_ids, launchd daemon install/restart/status), and debug Telegram MCP data availability.
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

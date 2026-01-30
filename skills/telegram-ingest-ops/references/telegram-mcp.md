# Telegram MCP (hawkfi-telegram)

This workspace can query local Telegram history through HawkFi Telegram Service.

## What it is
- A local FastAPI service (`hawkfi-telegram-service`) stores Telegram messages in SQLite (FTS5).
- A thin MCP stdio adapter (`hawkfi-telegram-mcp`) exposes tools that forward to the HTTP API.
- We register it in **mcporter** as server name: `hawkfi-telegram`.

## Prereqs
- Local service reachable: `http://127.0.0.1:8000/health`

## MCP tools (via mcporter)

Health:
- `mcporter call hawkfi-telegram.health --json`

List dialogs:
- `mcporter call hawkfi-telegram.dialogs --json`

Search dialogs:
- `mcporter call hawkfi-telegram.dialogs_search query="关键词" --json`

Search messages:
- `mcporter call hawkfi-telegram.search q="关键词" limit=50 --json`

Fetch channel messages:
- `mcporter call hawkfi-telegram.messages chat_id=123456 limit=100 --json`

Notes:
- Prefer searching first, then fetch messages by chat_id.
- When summarizing, do not include raw quotes unless user asks; output distilled bullets.

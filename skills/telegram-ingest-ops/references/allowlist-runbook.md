# Allowlist + restart runbook (hawkfi-telegram-service)

## Where
- Repo: `/Users/massis/Documents/Code/hawkfi-telegram-service`
- Config: `.env` → `ALLOWLIST_CHAT_IDS=...`

## Update flow
1) Find chat_id via MCP search:
   - `mcporter call hawkfi-telegram.dialogs_search --json query="<name>"`
2) Add chat_id to `.env` allowlist (comma-separated ints).
3) Reinstall/reload launchd (ensures allowlist is passed as CLI arg):
   - `poetry run python -m hawkfi_telegram_service.cli --daemon install --config .env --allowlist "<ids>"`
4) Confirm running:
   - `poetry run python -m hawkfi_telegram_service.cli --daemon status --config .env --allowlist "<ids>"`

## Notes
- New chats won’t appear in summaries until they produce new messages and get ingested.

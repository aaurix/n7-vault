# MEMORY.md (Long-term)

## Projects
- **market-ops**: Hourly TG+Twitter market/meme summary + on-demand symbol/CA analysis.
  - Keep hourly output WhatsApp-friendly, concise, and trader-usable.
  - Prefer stability-first pipelines with time-budget gating.

## Current engineering decisions
- **二级山寨 OI movers output**: keep low information load; show current price + 24h price change + 24h OI change + OI notional (USD) + optional MC/FDV (USD abbreviated). If MC/FDV cannot be resolved reliably, hide it.
- **Twitter context filtering**: filter bot/marketing; only enforce explicit symbol for ambiguous bases (e.g., PUMP) to avoid over-filtering.
- **CCXT**: introduced via `requirements.txt` and a wrapper (`scripts/hourly/exchange_ccxt.py`). Prefer ccxt when supported; fallback to native Binance HTTP.
- **Git pushes**: push to GitHub only when the user explicitly requests it.

## Ops / reminders
- Pill reminder acknowledgements are tracked locally in `memory/pill_ack.json`.

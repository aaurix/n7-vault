# Hourly pipeline (market-ops)

## Goal
Generate an hourly WhatsApp summary combining:
- Perp/alt OI+price signals (Top3)
- TG热点（事件/叙事）
- TG可交易标的（LLM提炼，偏“标的卡片”）
- Twitter topics (optional / secondary)
- Meme radar candidates (twitter + TG CA merge)

## Entry point
- Script: `/Users/massis/clawd/scripts/hourly_market_summary.py`
- Output: JSON (includes `summary_whatsapp`, `summary_markdown`, `errors`, and debug fields)

## Layers
1) **Data**
   - Telegram MCP (hawkfi-telegram): fetch/search local SQLite history
   - Binance futures: price/OI/volume + OI history
   - DexScreener: token metrics for CA candidates
   - Twitter via bird: search snippets (filtered before LLM)

2) **Deterministic preprocessing (must stay deterministic)**
   - Filtering spam/bots/ads
   - Deduplication
   - Token/CA extraction
   - Time budget gating

3) **LLM summarization**
   - Must be constrained to short structured outputs
   - Never quote raw chat lines unless explicitly requested

4) **Delivery**
   - WhatsApp only (PushDeer disabled for now)
   - Split to <=950 chars per message
   - Idempotency file to avoid duplicate sends

## Stability rules
- Prefer skipping optional steps over timing out.
- Errors go into `errors` field, not into user-visible messages.

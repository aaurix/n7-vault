# Hourly pipeline (market-ops)

## Goal
Generate an hourly WhatsApp summary combining:
- TG热点（事件/叙事）
- TG可交易标的（LLM提炼，偏“标的卡片”）
- Perp/alt OI+price signals (Top3)
- Meme radar candidates（TG CA threads + Dex）
- Twitter补充（CA锚定，optional/secondary）

## Entry point
- Script: `/Users/massis/clawd/scripts/hourly_market_summary.py`
- Output: JSON (includes `summary_whatsapp`, `errors`, and debug fields; do not show `errors` to users)

## Key debug fields (common)
- `tg_viewpoint_messages`: the human-sourced viewpoint messages used as input
- `tg_topics_messages`: the messages used for TG hot topics (if present)

## Layers
1) **Data**
   - Telegram MCP (hawkfi-telegram): fetch/search local SQLite history
   - Binance futures: price/OI/volume + OI history
   - DexScreener: token metrics for CA candidates
   - Twitter via bird: CA-anchored snippets (optional; filtered before LLM)

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

## Twitter CA topics (aux, TG-first)
- 候选来源：Telegram 线程 + meme radar 的 CA/Dex 匹配
- 证据抓取：bird 搜索以 CA 为主锚点（可带 $SYMBOL），强过滤推广/机器人
- 输出方式：规则化 one-liner/标签；预算允许时再用 LLM 重写

## Stability rules
- Prefer skipping optional steps over timing out.
- Errors go into `errors` field, not into user-visible messages.

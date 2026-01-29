---
name: market-ops
version: 0.1.0
description: Production ops for the hourly TG+Twitter market summary + on-demand symbol/CA analysis.
---

# market-ops

This skill documents and standardizes the production pipelines in this workspace.

## When to use

Use this skill when the user asks for any of:

1) **Hourly summary**
- “开启小时级别推送 / 关掉推送 / 改成Top3/Top5 / 改输出格式”
- “跑一下过去一小时数据”

2) **Alt/Perp (二级山寨) analysis**
- “分析 PUMP / XXXUSDT”
- “深入分析二级山寨 …（要现价、24h价、24h OI、MC/FDV等）”

3) **Contract address (CA) analysis**
- User sends an on-chain contract address.

## Production architecture (3-layer)

### Layer 1 — Core library (reusable modules)
Located at:
- `scripts/hourly/*.py`

Key modules:
- `topic_pipeline.py` — unified topics pipeline (TG + Twitter)
- `oi_plan_pipeline.py` — Top3 OI trader plans
- `binance_futures.py` — price/OI/volume (no key) + OI hist
- `kline_fetcher.py` + `binance_kline_context.py --json` — structured kline inputs
- `coingecko.py` — MC/FDV (USD) with conservative mapping (hide when unmatched)
- `llm_openai.py` — OpenAI chat/embeddings + embeddings cache

### Layer 2 — Cron runner (stable)
- Cron job: **Hourly TG+Twitter market/meme summary**
- Runs: `python3 /Users/massis/clawd/scripts/hourly_market_summary.py`
- Delivery: WhatsApp + PushDeer
- Requirements:
  - Stability-first (time budget gating)
  - Idempotent delivery via `memory/hourly_summary_delivery.json`
  - **Do not use heredocs** like `python3 - <<'PY'` in cron.

### Layer 3 — Chat runner (on-demand)
- In chat, run the same core modules via:
  - `python3 scripts/hourly_market_summary.py` (for last hour)
  - Single-symbol deep analysis (future improvement): `python3 scripts/binance_kline_context.py <SYMBOL> --json`

## Output specs (current)

### 二级山寨（趋势观点：1H+4H）
- **Top3** (deduped)
- Each line is **natural language**, reduced info:
  - current price
  - 24h price change
  - 24h OI change
  - OI notional value (USD)
  - MC/FDV (USD abbreviated) **only when resolvable**

Example:
- `CYSUSDT 现价0.2069；24h价-20.4%；24h OI+46.0%；OI价值$5.26M（24h+2.8%）；MC$32.05M/FDV$199.32M`

### 二级山寨Top3（交易员计划）
- LLM-generated plans, bias only when trend is very clear/extreme; otherwise bias=观望.
- Uses structured kline json + OI/price/vol + (optional) twitter snippets.

### Telegram热点Top5 / Twitter热点Top5
- Topic clustering via embeddings (K=10) -> LLM summarize -> post-filter.

## Contract address handling (CA)
If user sends a CA:
- Resolve chain + token basics (DEX/liq/mcap/fdv where available)
- Cross-source sentiment: Twitter + TG viewpoint chats (+ Reddit if feasible)
- Output: sources, main narrative, sentiment, trader risk profile.

## Operational rules

- **Stability-first**: if close to time budget, skip non-essential LLM steps.
- **errors** are written into JSON output for debugging but MUST NOT be included in user-visible messages.
- Prefer conservative matching (e.g., CoinGecko symbol->id): if ambiguous, do not display.

## Troubleshooting

- WhatsApp disconnect (428/499): transient; cron will continue; next run should deliver.
- Cron exec errors: avoid heredocs; use plain commands.
- If Twitter topics are noisy: adjust `twitter_context.py` and topic postfilters.

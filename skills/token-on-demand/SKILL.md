---
name: token-on-demand
description: "On-demand token analysis (not cron): (1) perp/alt symbol (e.g., XXXUSDT) and (2) on-chain meme via contract address/CA (0x… or Solana base58). Use for spot checks, risk/tradability bullets, and trade-plan style summaries."
---

# token-on-demand

This skill covers **interactive** analysis requests (not cron).

## Two different flows
1) **Perp / 二级山寨（symbol-based）**
   - Input forms accepted (normalized deterministically):
     - `PUMPUSDT` → `PUMPUSDT`
     - `PUMP` / `pump` / `$pump` → `PUMPUSDT` (**default quote: USDT**)
   - Social search normalization:
     - Uses cashtag anchor `$PUMP` (uppercase) + perp symbol anchor `PUMPUSDT`
     - For ambiguous tickers, bare words are de-emphasized and stronger anchors are required.
   - Prepare→Agent pattern:
     - prepare（无LLM）: `PYTHONPATH=src python3 -m market_ops symbol <SYMBOL_OR_TICKER> --no-llm`
     - agent（默认输出）: `PYTHONPATH=src python3 -m market_ops symbol <SYMBOL_OR_TICKER>`
   - Default output: **方案2 决策仪表盘**（趋势/OI/社交评分 + 要点）
   - Optional: **方案1 交易计划**（`--template plan`）

2) **链上 meme（CA-based）**
   - Input: contract address (0x… / solana base58)
   - Output: DexScreener metrics + TG/Twitter context + risk/tradability bullets
   - Command: `PYTHONPATH=src python3 -m market_ops ca <CA>`

## Quick commands
- Symbol dashboard (default):
  - `PYTHONPATH=src python3 -m market_ops symbol <SYMBOL_OR_TICKER>`
- Symbol trade plan (方案1):
  - `PYTHONPATH=src python3 -m market_ops symbol <SYMBOL_OR_TICKER> --template plan`
- CA analysis:
  - `PYTHONPATH=src python3 -m market_ops ca <CA>`

## Output boundaries
- No raw quotes unless user asks
- Prefer risk/tradability + plan-style bullets; avoid generic chatter

## References
- CA analysis spec: `references/ca-analysis.md`
- Perp analysis spec: `references/perp-analysis.md`

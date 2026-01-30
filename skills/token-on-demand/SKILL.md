---
name: token-on-demand
description: On-demand token analysis (not cron): (1) perp/alt symbol (e.g., XXXUSDT) and (2) on-chain meme via contract address/CA (0x… or Solana base58). Use for spot checks, risk/tradability bullets, and trade-plan style summaries.
---

# token-on-demand

This skill covers **interactive** analysis requests (not cron).

## Two different flows
1) **Perp / 二级山寨（symbol-based）**
   - Input: `WLDUSDT` / `PUMPUSDT`
   - Output: price/OI/kline structure + trade plan

2) **链上 meme（CA-based）**
   - Input: contract address (0x… / solana base58)
   - Output: DexScreener metrics + TG/Twitter context + risk/tradability bullets

## Quick commands
- CA analysis:
  - `python3 /Users/massis/clawd/scripts/analyze_ca.py <CA>`

## References
- CA analysis spec: `references/ca-analysis.md`
- Perp analysis spec: `references/perp-analysis.md`

---
name: token-on-demand
description: On-demand token analysis for two flows: (1) perps/alt symbols (e.g., XXXUSDT) and (2) on-chain meme tokens via contract address (CA). Use when user asks to analyze a symbol or sends a CA.
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

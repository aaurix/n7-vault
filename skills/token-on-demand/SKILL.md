---
name: token-on-demand
description: "On-demand token analysis (not cron): (1) perp/alt symbol (e.g., XXXUSDT) and (2) on-chain meme via contract address/CA (0x… or Solana base58). Use for spot checks, risk/tradability bullets, and trade-plan style summaries."
---

# token-on-demand

This skill covers **interactive** analysis requests (not cron).

## Two different flows
1) **Perp / 二级山寨（symbol-based）**
   - Input: `WLDUSDT` / `PUMPUSDT`
   - Prepare→Agent pattern:
     - prepare（无LLM）: `python3 /Users/massis/clawd/scripts/analyze_symbol_prepare.py <SYMBOL> --pretty`
     - agent（默认输出）: `python3 /Users/massis/clawd/scripts/analyze_symbol.py <SYMBOL>`
   - Default output: **方案2 决策仪表盘**（趋势/OI/社交评分 + 要点）
   - Optional: **方案1 交易计划**（`--template plan`）

2) **链上 meme（CA-based）**
   - Input: contract address (0x… / solana base58)
   - Output: DexScreener metrics + TG/Twitter context + risk/tradability bullets

## Quick commands
- Symbol dashboard (default):
  - `python3 /Users/massis/clawd/scripts/analyze_symbol.py <SYMBOL>`
- Symbol trade plan (方案1):
  - `python3 /Users/massis/clawd/scripts/analyze_symbol.py <SYMBOL> --template plan`
- Symbol prepare JSON (deterministic, no LLM):
  - `python3 /Users/massis/clawd/scripts/analyze_symbol_prepare.py <SYMBOL> --pretty`
- CA analysis:
  - `python3 /Users/massis/clawd/scripts/analyze_ca.py <CA>`

## Output boundaries
- No raw quotes unless user asks
- Prefer risk/tradability + plan-style bullets; avoid generic chatter

## References
- CA analysis spec: `references/ca-analysis.md`
- Perp analysis spec: `references/perp-analysis.md`

# Market Data Architecture (Batcher) Design

**Date:** 2026-02-05

## Goal
Unify all market data access behind small, domain‑scoped batchers (Exchange / Onchain / Social) so that:
- data access has a single entry per domain
- caching, timeouts, and rate limits are centralized
- ccxt is primary, Binance REST is fallback
- real‑time vs cached behavior is controllable via CLI
- old/duplicated direct calls are removed

## Current Data Sources (Inventory)
**Exchange**
- Binance USDT‑M futures public REST: klines, open interest, premium index (mark price)
- CCXT (binanceusdm): OHLCV, ticker, OI history

**Onchain**
- DexScreener API: token / pair search + metrics (cached on disk)
- CoinGecko API: symbol→id resolve, market cap / FDV (cached on disk)

**Social**
- Telegram local service (HawkFi TG Service): health / channels / replay / search
- Bird CLI (X/Twitter scraping): `bird search`, `bird home --following`
- mcporter CLI (local Telegram search): `hawkfi-telegram.search`

**LLM**
- OpenRouter Chat API (LLM)
- OpenAI Embeddings API

## Target Architecture (Lightweight, Explicit)
**Structure**
```
scripts/market_data/
  exchange/
    batcher.py
    provider_ccxt.py
    provider_binance.py
  onchain/
    batcher.py
    provider_dexscreener.py
    provider_coingecko.py
  social/
    batcher.py
    provider_tg.py
    provider_bird.py
  utils/
    paths.py
    cache.py
```

**Rule**: `market_ops` can import **only** `market_data.<domain>.batcher` (or `market_data` shared helpers). Provider modules are internal. This keeps data access single‑entry and prevents new ad‑hoc calls.

## Batcher Responsibilities
Each batcher handles:
- provider priority / fallback (ccxt → binance)
- caching policy (TTL, fresh mode)
- rate limit & concurrency budgets
- consistent error handling (return empty/None; append context errors upstream)

Providers handle:
- external I/O
- minimal normalization of raw fields
- no caching, no concurrency, no business logic

## Interfaces (Conceptual)
**ExchangeBatcher**
- `ohlcv(symbol, timeframe, limit)`
- `ticker_last(symbol)`
- `oi_history(symbol, timeframe, limit)`
- `oi_changes(symbol)`
- `price_changes(symbol)`

**DexBatcher**
- `search(query)`
- `best_pair(pairs, symbol_hint=None)`
- `pair_metrics(pair)`
- `enrich_symbol(sym)`
- `enrich_addr(addr)`
- `resolve_addr_symbol(addr)`
- `market_cap_fdv(symbol)`

**SocialBatcher**
- `tg_client()`
- `tg_search(chat_id, q, limit)`
- `bird_search(query, limit, timeout)`
- `bird_following(n, timeout)`

Batchers should expose a minimal shared config object (cache policy, timeouts, budgets). That config is injected by CLI via `context_builder`.

## Caching & Real‑Time Controls
**CLI flags** (all commands):
- `--fresh` disables disk cache and forces TTL=0
- `--cache-ttl exchange=300,onchain=900,social=60` overrides TTL per domain

**Defaults** (tuned for stability):
- Exchange: 120–300s
- Onchain: 900–1800s
- Social: 30–60s

Rules:
- `--fresh` overrides everything
- disk cache is only for onchain providers; exchange uses in‑memory TTL only
- social caches only for short windows to avoid stale sentiment

## Concurrency & Rate Limits
- Batcher controls concurrency via thread pool (no global async overhaul)
- Exchange: bulk OHLCV / OI requests fan out but respect a max parallel budget
- Social: Bird calls are gated (Top1 / explicit request only); failures return empty without blocking pipeline
- Binance is never hit in unbounded parallelism; ccxt has `enableRateLimit` and Binance fallback uses its own throttle

## Error Handling & Observability
- Providers return `[]/None/{}` on failure
- Batchers add structured error codes to `ctx.errors` where relevant
- Bird auth errors are detected explicitly (`bird_auth_missing`)
- All data access failures remain soft failures (hourly summary still renders)

## Migration & Cleanup
1. Add batchers and provider modules.
2. Update `PipelineContext` to include `exchange`, `dex`, `social` batchers.
3. Update `context_builder` to wire CLI config into batchers.
4. Replace all direct imports of binance/dexscreener/coingecko/tg/bird with batcher calls.
5. Remove old direct access patterns and unused helpers.
6. Update docs/skills to reference batcher usage only.

## Testing Strategy
- Unit tests for batcher fallback ordering and caching
- Unit tests for CLI cache TTL parsing
- Regression tests for symbol/CA/hourly pipelines still passing
- Keep `PYTHONPATH=.` in test runs until a project‑level fix is agreed


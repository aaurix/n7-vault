# N7-ops Market-Data Refactor Design

**Date:** 2026-02-05

## Goal
Move kline and market data helpers out of `market_ops` into `market_data`, and relocate PushDeer sender to a proper ops/notify location. Keep `market_ops` focused on orchestration and domain logic.

## Scope
- `scripts/market_ops/kline_fetcher.py` -> `scripts/market_data/utils/kline_fetcher.py`
- `scripts/market_ops/market_data_helpers.py` -> `scripts/market_data/utils/market_data_helpers.py`
- `scripts/pushdeer_send.py` -> `scripts/ops/notify/pushdeer.py`
- Update imports + tests to new module paths
- No new job scripts for PushDeer (per user)

## Design Principles
- **Single data boundary:** raw market data access belongs in `market_data`.
- **Market-ops stays orchestration + logic:** no direct data access helpers.
- **Minimal API churn:** keep function names, update import paths.

## Target Layout
```
scripts/
  market_data/
    utils/
      kline_fetcher.py
      market_data_helpers.py
  market_ops/
    features/...
  ops/
    notify/
      pushdeer.py
```

## Import Updates
- `scripts.market_ops.kline_fetcher` -> `scripts.market_data.utils.kline_fetcher`
- `scripts.market_ops.market_data_helpers` -> `scripts.market_data.utils.market_data_helpers`
- Update test imports accordingly

## Verification
- Add guard tests for new module locations
- Ensure old paths are removed
- Run full `pytest`


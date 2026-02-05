# Market Data Batcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace direct data-source calls with Exchange/Dex/Social batchers, unify caching/timeout controls via CLI, and remove redundant paths.

**Architecture:** Add lightweight domain batchers in `scripts/market_data` and wire them into `market_ops` context/services. ccxt remains primary with Binance fallback. All caching/limits live in batchers.

**Tech Stack:** Python 3.14, pytest, argparse, ccxt (optional), Binance REST, DexScreener, CoinGecko, Bird CLI.

---

### Task 1: Add cache policy + TTL parsing utilities

**Files:**
- Create: `scripts/market_data/utils/cache.py`
- Test: `tests/market_data/test_cache_policy.py`

**Step 1: Write the failing test**

```python
from scripts.market_data.utils.cache import CachePolicy, parse_cache_ttl


def test_parse_cache_ttl_basic():
    cfg = parse_cache_ttl("exchange=300,onchain=900,social=60")
    assert cfg.exchange == 300
    assert cfg.onchain == 900
    assert cfg.social == 60


def test_cache_policy_fresh_overrides():
    p = CachePolicy(fresh=True, ttl_s=120)
    assert p.ttl() == 0
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_data/test_cache_policy.py -v`
Expected: FAIL (module missing)

**Step 3: Write minimal implementation**

```python
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class CachePolicy:
    fresh: bool = False
    ttl_s: int = 0

    def ttl(self) -> int:
        return 0 if self.fresh else int(self.ttl_s)


@dataclass(frozen=True)
class CacheTTLConfig:
    exchange: int = 0
    onchain: int = 0
    social: int = 0


def parse_cache_ttl(raw: str) -> CacheTTLConfig:
    if not raw:
        return CacheTTLConfig()
    out = {"exchange": 0, "onchain": 0, "social": 0}
    for part in raw.split(","):
        if not part.strip():
            continue
        k, v = part.split("=", 1)
        if k.strip() in out:
            out[k.strip()] = int(v.strip())
    return CacheTTLConfig(**out)
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_data/test_cache_policy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_data/utils/cache.py tests/market_data/test_cache_policy.py
git commit -m "feat: add cache policy parsing"
```

---

### Task 2: Introduce batchers and provider modules

**Files:**
- Create: `scripts/market_data/exchange/batcher.py`
- Create: `scripts/market_data/onchain/batcher.py`
- Create: `scripts/market_data/social/batcher.py`
- Move: `scripts/market_data/exchange/exchange_ccxt.py` → `scripts/market_data/exchange/provider_ccxt.py`
- Move: `scripts/market_data/exchange/binance_futures.py` → `scripts/market_data/exchange/provider_binance.py`
- Move: `scripts/market_data/onchain/dexscreener.py` → `scripts/market_data/onchain/provider_dexscreener.py`
- Move: `scripts/market_data/onchain/coingecko.py` → `scripts/market_data/onchain/provider_coingecko.py`
- Move: `scripts/market_data/social/tg_client.py` → `scripts/market_data/social/provider_tg.py`
- Create: `scripts/market_data/social/provider_bird.py`
- Modify: `scripts/market_data/__init__.py`
- Test: `tests/market_data/test_exchange_batcher.py`

**Step 1: Write the failing test**

```python
from scripts.market_data.exchange.batcher import ExchangeBatcher


def test_exchange_batcher_prefers_ccxt(monkeypatch):
    calls = []
    monkeypatch.setattr("scripts.market_data.exchange.provider_ccxt.fetch_ohlcv", lambda *a, **k: [[1,1,1,1,1,1]])
    monkeypatch.setattr("scripts.market_data.exchange.provider_binance.get_klines", lambda *a, **k: (_ for _ in ()).throw(AssertionError("binance used")))
    b = ExchangeBatcher()
    rows = b.ohlcv("BTCUSDT", "1h", 2)
    assert rows
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_data/test_exchange_batcher.py -v`
Expected: FAIL (module missing)

**Step 3: Write minimal implementation**

```python
class ExchangeBatcher:
    def __init__(self, *, cache_policy=None):
        self.cache_policy = cache_policy

    def ohlcv(self, symbol, timeframe, limit):
        rows = provider_ccxt.fetch_ohlcv(symbol, timeframe, limit)
        if rows:
            return rows
        return provider_binance.get_klines(symbol, timeframe, limit)
```

Add equivalent thin wrappers in `DexBatcher` and `SocialBatcher`, then wire shared getters in `scripts/market_data/__init__.py`:

```python
def get_shared_exchange_batcher(...):
    global _EX
    if _EX is None:
        _EX = ExchangeBatcher(...)
    return _EX
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_data/test_exchange_batcher.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_data/exchange/batcher.py scripts/market_data/onchain/batcher.py scripts/market_data/social/batcher.py \
  scripts/market_data/exchange/provider_ccxt.py scripts/market_data/exchange/provider_binance.py \
  scripts/market_data/onchain/provider_dexscreener.py scripts/market_data/onchain/provider_coingecko.py \
  scripts/market_data/social/provider_tg.py scripts/market_data/social/provider_bird.py \
  scripts/market_data/__init__.py tests/market_data/test_exchange_batcher.py
git commit -m "feat: add market data batchers"
```

---

### Task 3: Wire CLI + context to batchers

**Files:**
- Modify: `scripts/market_ops/cli.py`
- Modify: `scripts/market_ops/facade.py`
- Modify: `scripts/market_ops/models.py`
- Modify: `scripts/market_ops/services/context_builder.py`
- Test: `tests/market_ops/test_cli.py`

**Step 1: Write the failing test**

```python
def test_cli_help_shows_cache_flags():
    r = subprocess.run(["python3", "-m", "scripts.market_ops", "--help"], capture_output=True, text=True)
    assert "--fresh" in r.stdout
    assert "--cache-ttl" in r.stdout
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_cli.py -v`
Expected: FAIL (flags not present)

**Step 3: Write minimal implementation**

Add shared flags in CLI:

```python
common.add_argument("--fresh", action="store_true")
common.add_argument("--cache-ttl", default="")
```

Add `cache_policy` fields to `PipelineContext`, and pass config from CLI to `build_context`:

```python
ctx = build_context(total_budget_s=args.budget, fresh=args.fresh, cache_ttl=args.cache_ttl)
```

Context builder uses `parse_cache_ttl` and creates shared batchers:

```python
exchange = get_shared_exchange_batcher(cache_policy=CachePolicy(fresh=fresh, ttl_s=ttl.exchange))
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_ops/cli.py scripts/market_ops/facade.py scripts/market_ops/models.py \
  scripts/market_ops/services/context_builder.py tests/market_ops/test_cli.py
git commit -m "feat: wire cache config into context"
```

---

### Task 4: Replace direct data-source calls with batchers

**Files:**
- Modify: `scripts/market_ops/oi_plan_pipeline.py`
- Modify: `scripts/market_ops/services/symbol_analysis.py`
- Modify: `scripts/market_ops/market_data_helpers.py`
- Modify: `scripts/market_ops/kline_fetcher.py`
- Modify: `scripts/market_ops/services/ca_analysis.py`
- Modify: `scripts/market_ops/services/entity_resolver.py`
- Modify: `scripts/market_ops/services/meme_radar_engine.py`
- Modify: `scripts/market_ops/services/twitter_evidence.py`
- Modify: `scripts/market_ops/services/twitter_following.py`
- Modify: `scripts/market_ops/services/telegram_service.py`

**Step 1: Write a failing test**

Add a small regression in `tests/market_ops/test_market_data.py` to assert calls go through batcher:

```python
from scripts.market_ops.services.context_builder import build_context


def test_context_has_batchers():
    ctx = build_context()
    assert ctx.exchange is not None
    assert ctx.dex is not None
    assert ctx.social is not None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_market_data.py -v`
Expected: FAIL (fields missing)

**Step 3: Write minimal implementation**

- Replace imports of `provider_*` in services with `ctx.exchange/ctx.dex/ctx.social` access.
- Add shared batchers to `PipelineContext`.
- For symbol/CA (no ctx), use shared batchers from `scripts.market_data`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_market_data.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_ops/oi_plan_pipeline.py scripts/market_ops/services/symbol_analysis.py \
  scripts/market_ops/market_data_helpers.py scripts/market_ops/kline_fetcher.py \
  scripts/market_ops/services/ca_analysis.py scripts/market_ops/services/entity_resolver.py \
  scripts/market_ops/services/meme_radar_engine.py scripts/market_ops/services/twitter_evidence.py \
  scripts/market_ops/services/twitter_following.py scripts/market_ops/services/telegram_service.py \
  tests/market_ops/test_market_data.py
git commit -m "refactor: route data access through batchers"
```

---

### Task 5: Remove legacy/unused paths and update docs

**Files:**
- Modify: `docs/*` and `skills/*` references to old modules
- Remove: any unused direct import helpers after refactor

**Step 1: Write the failing test**

Extend `tests/market_ops/test_adapters_import.py` to ensure old providers are not imported directly.

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_adapters_import.py -v`
Expected: FAIL (direct imports still present)

**Step 3: Write minimal implementation**

- Remove dead helpers
- Update docs/skills with new CLI flags and batcher usage

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_adapters_import.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docs skills tests/market_ops/test_adapters_import.py
git commit -m "docs: update market data architecture"
```

---

### Task 6: Full verification

**Step 1: Run full test suite**

Run: `PYTHONPATH=. /Users/massis/.openclaw/workspace/.venv/bin/pytest`
Expected: PASS (warnings acceptable)

**Step 2: Summarize behavior changes**

- Single entry for data access via batchers
- CLI supports `--fresh` and `--cache-ttl`
- ccxt primary, Binance fallback

**Step 3: Commit final cleanup if needed**

```bash
git add -A
git commit -m "chore: finalize batcher migration" || true
```


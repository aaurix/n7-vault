# Market Ops Scripts Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move codebase to `scripts/` as the single package root, split reusable IO into `scripts/market_data`, and clean up duplication/boundary issues while fixing broken kline/meme radar paths.

**Architecture:** `scripts/market_ops` holds business pipeline, rendering, and use-cases; `scripts/market_data` holds external IO (DexScreener/Binance/ccxt/CoinGecko/TG/Bird). Imports flow one way: `market_ops` → `market_data`.

**Tech Stack:** Python 3, pytest.

---

### Task 1: Make `scripts` the package entrypoint (CLI test)

**Files:**
- Modify: `tests/market_ops/test_cli.py`
- Create: `scripts/__init__.py`
- Move: `src/market_ops` -> `scripts/market_ops`

**Step 1: Write the failing test**

Update `tests/market_ops/test_cli.py`:
```python
import os
import subprocess


def test_cli_help():
    env = dict(os.environ)
    r = subprocess.run(["python3", "-m", "scripts.market_ops", "--help"], capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert "symbol" in r.stdout
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_cli.py -v`
Expected: FAIL (module not found)

**Step 3: Minimal implementation**
- Create `scripts/__init__.py` (empty)
- `git mv src/market_ops scripts/market_ops`
- Ensure `scripts/market_ops/__main__.py` still calls `cli.main()`

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_cli.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/__init__.py scripts/market_ops tests/market_ops/test_cli.py
git commit -m "feat: move market_ops under scripts package"
```

---

### Task 2: Update tests to import from `scripts.market_ops`

**Files:**
- Modify: `tests/market_ops/*.py`
- Modify: `tests/test_*.py`
- Modify: `tests/market_ops/test_legacy_removed.py`

**Step 1: Write the failing test**

Update `tests/market_ops/test_legacy_removed.py`:
```python
import importlib


def test_scripts_package_present():
    assert importlib.util.find_spec("scripts.market_ops") is not None
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_legacy_removed.py -v`
Expected: FAIL until imports are fixed

**Step 3: Update imports in tests**
- Replace `from market_ops...` with `from scripts.market_ops...` in all tests.

**Step 4: Run subset tests**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_legacy_removed.py tests/market_ops/test_paths.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add tests
git commit -m "test: switch imports to scripts.market_ops"
```

---

### Task 3: Fix internal imports after move

**Files:**
- Modify: `scripts/market_ops/**/*.py`

**Step 1: Write a failing test**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_paths.py -v`
Expected: FAIL due to import errors

**Step 2: Update internal imports**
- Replace absolute `from market_ops...` with relative imports or `from scripts.market_ops...`.
- Keep internal imports consistent (prefer relative within `scripts/market_ops`).

**Step 3: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_paths.py -v`
Expected: PASS

**Step 4: Commit**
```bash
git add scripts/market_ops
git commit -m "refactor: fix market_ops imports under scripts"
```

---

### Task 4: Split reusable IO into `scripts/market_data`

**Files:**
- Create: `scripts/market_data/__init__.py`
- Create: `scripts/market_data/exchange/{binance_futures.py,exchange_ccxt.py}`
- Create: `scripts/market_data/onchain/{dexscreener.py,coingecko.py}`
- Create: `scripts/market_data/social/{bird_utils.py,tg_client.py}`
- Remove: `scripts/market_ops/adapters/*`
- Modify: imports in `scripts/market_ops`
- Test: `tests/market_ops/test_adapters_import.py` → replace with market_data import test

**Step 1: Write failing test**

Replace `tests/market_ops/test_adapters_import.py` with:
```python
def test_market_data_imports():
    import scripts.market_data.onchain.dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_adapters_import.py -v`
Expected: FAIL

**Step 3: Move files + update imports**
- Move adapters into `scripts/market_data/*` and update imports in market_ops.
- Remove `scripts/market_ops/adapters` directory.

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_adapters_import.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_data scripts/market_ops tests/market_ops/test_adapters_import.py
git commit -m "feat: split market_data adapters"
```

---

### Task 5: Remove `ports/` and unify market data helpers

**Files:**
- Remove: `scripts/market_ops/ports/*`
- Modify: `scripts/market_ops/market_data_helpers.py`
- Modify: any call sites in services

**Step 1: Write failing test**

Update `tests/market_ops/test_market_data.py` to use `market_data_helpers.fetch_dex_market` only:
```python
from scripts.market_ops.market_data_helpers import fetch_dex_market

class DummyDex:
    def enrich_addr(self, addr):
        return {"price": 1}


def test_fetch_dex_market():
    out = fetch_dex_market("0x1", "SYM", dex_client=DummyDex())
    assert out["price"] == 1
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_market_data.py -v`
Expected: FAIL until ports removed and helper updated

**Step 3: Update code**
- Remove `ports/` usage.
- Ensure `market_data_helpers.fetch_dex_market` signature matches tests.

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_market_data.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops tests/market_ops/test_market_data.py
git commit -m "refactor: remove ports and unify market data helpers"
```

---

### Task 6: Fix `kline_fetcher` without external scripts

**Files:**
- Modify: `scripts/market_ops/kline_fetcher.py`
- (Optional) Create: `scripts/market_data/exchange/kline_context.py`
- Test: `tests/market_ops/test_kline_context.py`

**Step 1: Write failing test**

Create `tests/market_ops/test_kline_context.py`:
```python
from scripts.market_ops.kline_fetcher import summarize_klines


def test_summarize_klines_basic():
    kl = [
        [0, "1", "2", "1", "1", "10"],
        [1, "1", "3", "1", "2", "20"],
        [2, "2", "4", "2", "3", "30"],
        [3, "3", "5", "3", "4", "40"],
    ]
    out = summarize_klines(kl, interval="1h")
    assert out["interval"] == "1h"
    assert out["last"] == 4.0
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_kline_context.py -v`
Expected: FAIL (function missing)

**Step 3: Implement minimal internal summarizer**
- Add `summarize_klines()` in `kline_fetcher.py` (ported from old script logic).
- Update `run_kline_json()` to call `market_data/exchange/binance_futures.get_klines()` directly and then summarize.

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_kline_context.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/kline_fetcher.py tests/market_ops/test_kline_context.py
git commit -m "feat: internalize kline context"
```

---

### Task 7: Replace meme radar subprocess with internal module

**Files:**
- Modify: `scripts/market_ops/services/meme_radar.py`
- Create: `scripts/market_ops/services/meme_radar_engine.py`
- Test: `tests/market_ops/test_meme_radar_engine.py`

**Step 1: Write failing test**

Create `tests/market_ops/test_meme_radar_engine.py`:
```python
from scripts.market_ops.services.meme_radar_engine import _normalize_candidates


def test_normalize_candidates_dedup():
    raw = [{"addr": "0x1"}, {"addr": "0x1"}, {"addr": "0x2"}]
    out = _normalize_candidates(raw)
    assert len(out) == 2
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_meme_radar_engine.py -v`
Expected: FAIL

**Step 3: Implement minimal engine + wire service**
- Port core logic from old meme_radar script into `meme_radar_engine.run_meme_radar()`.
- Update `services/meme_radar.py` to call engine directly (no subprocess).

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_meme_radar_engine.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/services/meme_radar.py scripts/market_ops/services/meme_radar_engine.py tests/market_ops/test_meme_radar_engine.py
git commit -m "feat: internalize meme radar engine"
```

---

### Task 8: De-duplicate formatting/indicators

**Files:**
- Modify: `scripts/market_ops/core/formatting.py`
- Modify: `scripts/market_ops/core/indicators.py`
- Modify: `scripts/market_ops/services/symbol_analysis.py`
- Modify: `scripts/market_ops/perp_dashboard.py`

**Step 1: Write failing test**

Update `tests/market_ops/test_indicators.py` to import from `scripts.market_ops.core.indicators` (already updated in Task 2) and add a second check for reuse:
```python
from scripts.market_ops.core.indicators import flow_label

def test_flow_label_up_up():
    assert flow_label(px_chg=2, oi_chg=6).startswith("多头加仓")
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_indicators.py -v`
Expected: FAIL until usages are unified

**Step 3: Update code to reuse core utilities**
- Replace duplicate `flow_label` and `_fmt_*` implementations with `core/formatting` + `core/indicators`.

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_indicators.py tests/market_ops/test_formatting.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/core scripts/market_ops/services/symbol_analysis.py scripts/market_ops/perp_dashboard.py
git commit -m "refactor: unify formatting and indicators"
```

---

### Task 9: Update docs/skills/cron instructions and remove `src/`

**Files:**
- Modify: `skills/market-ops/SKILL.md`
- Modify: `skills/token-on-demand/SKILL.md`
- Modify: `references/*.md`
- Remove: `src/`

**Step 1: Write failing test**

Update `tests/market_ops/test_legacy_removed.py` to ensure `src` is gone:
```python
from pathlib import Path

def test_src_removed():
    assert not Path("src").exists()
```

**Step 2: Run test to verify it fails**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_legacy_removed.py -v`
Expected: FAIL

**Step 3: Update docs + remove src**
- Replace commands with `python3 -m scripts.market_ops ...`
- `git rm -r src`

**Step 4: Run test to verify it passes**

Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest tests/market_ops/test_legacy_removed.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add skills references tests/market_ops/test_legacy_removed.py
git rm -r src
git commit -m "chore: move to scripts package root"
```

---

### Task 10: Full test run

**Step 1: Run full test suite**
Run: `/Users/massis/.openclaw/workspace/.venv/bin/python -m pytest -v`
Expected: PASS (allow deprecation warning)

**Step 2: Commit (if any fixes)**
```bash
git add -u
git commit -m "test: verify scripts package split"
```


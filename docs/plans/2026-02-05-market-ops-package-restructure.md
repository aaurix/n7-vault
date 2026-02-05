# Market Ops Package Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the scripts-based layout with a single package (`src/market_ops`) and a unified CLI (`python -m market_ops`), while keeping deterministic-first behavior and a shared output schema.

**Architecture:** Introduce a facade + pipeline runner, isolate adapters/ports, and centralize indicators/formatting. All entrypoints route through `market_ops.cli`, which calls `market_ops.facade`, which orchestrates deterministic collection and optional LLM rendering.

**Tech Stack:** Python 3, pytest, current dependencies in `requirements.txt`.

---

### Task 1: Add the unified schema envelope

**Files:**
- Create: `src/market_ops/schema.py`
- Test: `tests/market_ops/test_schema.py`

**Step 1: Write the failing test**

```python
from market_ops.schema import wrap_result


def test_wrap_result_basic():
    out = wrap_result(mode="symbol", data={"x": 1}, summary=None, errors=["e"])
    assert out["meta"]["mode"] == "symbol"
    assert out["data"] == {"x": 1}
    assert out["summary"] is None
    assert out["errors"] == ["e"]
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_schema.py::test_wrap_result_basic -v`
Expected: FAIL (module or function missing)

**Step 3: Write minimal implementation**

```python
from __future__ import annotations
import datetime as dt


def wrap_result(*, mode: str, data: dict, summary, errors: list, use_llm: bool = False, version: str = "v1") -> dict:
    return {
        "meta": {
            "mode": mode,
            "version": version,
            "use_llm": bool(use_llm),
            "timestamp": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        },
        "data": data or {},
        "summary": summary,
        "errors": errors or [],
    }
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_schema.py::test_wrap_result_basic -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/schema.py tests/market_ops/test_schema.py
git commit -m "feat: add unified schema envelope"
```

---

### Task 2: Centralize formatting utilities

**Files:**
- Create: `src/market_ops/core/formatting.py`
- Test: `tests/market_ops/test_formatting.py`

**Step 1: Write the failing test**

```python
from market_ops.core.formatting import fmt_pct, fmt_usd


def test_fmt_pct():
    assert fmt_pct(1.234) == "+1.2%"


def test_fmt_usd():
    assert fmt_usd(1500) == "$1.5K"
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_formatting.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
def fmt_pct(x):
    if x is None:
        return "?"
    return f"{float(x):+.1f}%"


def fmt_usd(x):
    if x is None:
        return "?"
    v = float(x)
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_formatting.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/core/formatting.py tests/market_ops/test_formatting.py
git commit -m "feat: centralize formatting helpers"
```

---

### Task 3: Centralize indicators

**Files:**
- Create: `src/market_ops/core/indicators.py`
- Test: `tests/market_ops/test_indicators.py`

**Step 1: Write the failing test**

```python
from market_ops.core.indicators import flow_label


def test_flow_label_up_up():
    assert flow_label(px_chg=2, oi_chg=6).startswith("多头加仓")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_indicators.py::test_flow_label_up_up -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
def flow_label(*, px_chg, oi_chg):
    if not isinstance(px_chg, (int, float)) or not isinstance(oi_chg, (int, float)):
        return "资金方向不明"
    if oi_chg >= 5 and px_chg >= 1:
        return "多头加仓（价↑OI↑）"
    if oi_chg >= 5 and px_chg <= -1:
        return "空头加仓（价↓OI↑）"
    if oi_chg <= -5 and px_chg >= 1:
        return "空头回补（价↑OI↓）"
    if oi_chg <= -5 and px_chg <= -1:
        return "多头止损/出清（价↓OI↓）"
    return "轻微/震荡（价/OI变化不大）"
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_indicators.py::test_flow_label_up_up -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/core/indicators.py tests/market_ops/test_indicators.py
git commit -m "feat: centralize indicator logic"
```

---

### Task 4: Package skeleton + repo paths

**Files:**
- Create: `src/market_ops/__init__.py`
- Create: `src/market_ops/__main__.py`
- Create: `src/market_ops/utils/paths.py`
- Test: `tests/market_ops/test_paths.py`

**Step 1: Write the failing test**

```python
from market_ops.utils.paths import repo_root


def test_repo_root_contains_readme():
    root = repo_root()
    assert (root / "README.md").exists()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_paths.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
from pathlib import Path
from functools import lru_cache


@lru_cache(maxsize=1)
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_paths.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/__init__.py src/market_ops/__main__.py src/market_ops/utils/paths.py tests/market_ops/test_paths.py
git commit -m "feat: add market_ops package skeleton"
```

---

### Task 5: Migrate adapters (Dex/TG/Bird/Binance/ccxt/CoinGecko)

**Files:**
- Create: `src/market_ops/adapters/dexscreener.py`
- Create: `src/market_ops/adapters/tg_client.py`
- Create: `src/market_ops/adapters/bird_utils.py`
- Create: `src/market_ops/adapters/exchange_ccxt.py`
- Create: `src/market_ops/adapters/binance_futures.py`
- Create: `src/market_ops/adapters/coingecko.py`
- Create: `src/market_ops/adapters/__init__.py`
- Modify imports to use `market_ops.utils.paths`
- Test: `tests/market_ops/test_adapters_import.py`

**Step 1: Write failing test (smoke import)**

```python
def test_adapters_import():
    import market_ops.adapters.dexscreener as ds
    assert hasattr(ds, "DexScreenerClient")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_adapters_import.py -v`
Expected: FAIL

**Step 3: Implement migration (copy + fix imports)**

Copy logic from `scripts/market_hourly/*` into the new adapter files. Update path helpers to import from `market_ops.utils.paths`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_adapters_import.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/adapters tests/market_ops/test_adapters_import.py
git commit -m "feat: migrate external adapters"
```

---

### Task 6: Add market_data port

**Files:**
- Create: `src/market_ops/ports/market_data.py`
- Create: `src/market_ops/ports/__init__.py`
- Test: `tests/market_ops/test_market_data.py`

**Step 1: Write failing test (adapter injection)**

```python
from market_ops.ports.market_data import fetch_dex_market


class DummyDex:
    def enrich_addr(self, addr):
        return {"price": 1}


def test_fetch_dex_market():
    out = fetch_dex_market("0x1", "SYM", dex=DummyDex())
    assert out["price"] == 1
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_market_data.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

```python
from market_ops.adapters.dexscreener import get_shared_dexscreener_client


def fetch_dex_market(addr: str, sym: str, dex=None) -> dict:
    dex = dex or get_shared_dexscreener_client()
    if addr:
        return dex.enrich_addr(addr) or {}
    if sym:
        return dex.enrich_symbol(sym) or {}
    return {}
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_market_data.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/ports tests/market_ops/test_market_data.py
git commit -m "feat: add market_data port"
```

---

### Task 7: Migrate models/config/filters and services

**Files:**
- Move: `scripts/market_hourly/models.py` -> `src/market_ops/models.py`
- Move: `scripts/market_hourly/config.py` -> `src/market_ops/config.py`
- Move: `scripts/market_hourly/filters.py` -> `src/market_ops/filters.py`
- Move: `scripts/market_hourly/services/*` -> `src/market_ops/services/*`
- Update imports across services/tests

**Step 1: Update one test import to fail**

Example change in `tests/test_tg_preprocess.py`:
```python
from market_ops.services.tg_preprocess import prefilter_tg_topic_text
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/test_tg_preprocess.py -v`
Expected: FAIL

**Step 3: Move files + fix imports**

- Update all `from market_hourly...` to `from market_ops...`
- Ensure `market_ops.models.PipelineContext` includes a `runtime: dict = field(default_factory=dict)` for cross-step state.

**Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=src pytest tests/test_tg_preprocess.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/models.py src/market_ops/config.py src/market_ops/filters.py src/market_ops/services tests
git commit -m "feat: migrate core modules and services"
```

---

### Task 8: Migrate on-demand analyzers (symbol + CA)

**Files:**
- Create: `src/market_ops/services/symbol_analysis.py`
- Create: `src/market_ops/services/ca_analysis.py`
- Test: `tests/market_ops/test_symbol_ca_smoke.py`

**Step 1: Write failing test (smoke)**

```python
def test_symbol_ca_modules_import():
    import market_ops.services.symbol_analysis as sym
    import market_ops.services.ca_analysis as ca
    assert hasattr(sym, "analyze_symbol")
    assert hasattr(ca, "analyze_ca")
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_symbol_ca_smoke.py -v`
Expected: FAIL

**Step 3: Implement migration (copy + refactor)**

- Move logic from `scripts/analyze_symbol.py` into `services/symbol_analysis.py`
- Move logic from `scripts/analyze_ca.py` into `services/ca_analysis.py`
- Remove CLI parsing from these modules; expose `analyze_symbol()` / `analyze_ca()` functions that return `{data, summary, errors, use_llm}`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_symbol_ca_smoke.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/services/symbol_analysis.py src/market_ops/services/ca_analysis.py tests/market_ops/test_symbol_ca_smoke.py
git commit -m "feat: migrate symbol/ca analyzers into services"
```

---

### Task 9: Pipeline runner + hourly steps

**Files:**
- Create: `src/market_ops/pipeline/runner.py`
- Create: `src/market_ops/pipeline/hourly.py`
- Create: `src/market_ops/pipeline/steps/*.py`
- Test: `tests/market_ops/test_pipeline_runner.py`

**Step 1: Write failing test**

```python
from market_ops.pipeline.runner import PipelineRunner


def test_runner_executes_steps_in_order():
    order = []
    def s1(ctx): order.append("a")
    def s2(ctx): order.append("b")
    runner = PipelineRunner(ctx={}, steps=[("s1", s1), ("s2", s2)])
    runner.run()
    assert order == ["a", "b"]
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_pipeline_runner.py -v`
Expected: FAIL

**Step 3: Implement runner + hourly steps**

`runner.py`
```python
import time


class PipelineRunner:
    def __init__(self, *, ctx, steps, continue_on_error=True, skip=None, only=None):
        self.ctx = ctx
        self.steps = steps
        self.continue_on_error = continue_on_error
        self.skip = set(skip or [])
        self.only = set(only or [])

    def _should_run(self, name: str) -> bool:
        if self.only and name not in self.only:
            return False
        if name in self.skip:
            return False
        return True

    def run(self):
        for name, fn in self.steps:
            if not self._should_run(name):
                continue
            t0 = time.perf_counter()
            try:
                fn(self.ctx)
            except Exception as e:
                self.ctx.errors.append(f"step_failed:{name}:{type(e).__name__}:{e}")
                if not self.continue_on_error:
                    raise
            finally:
                self.ctx.perf[f"step_{name}"] = round(time.perf_counter() - t0, 3)
```

`steps/health_check.py`
```python
from market_ops.services.telegram_service import require_tg_health


def step(ctx):
    require_tg_health(ctx)
```

Repeat with thin wrappers for each existing service function:
- meme_spawn: `spawn_meme_radar`
- tg_fetch: `fetch_tg_messages`
- human_texts: `build_human_texts`
- oi_items: `build_oi`
- oi_plans: `build_oi_plans_step`
- viewpoint_threads: `build_viewpoint_threads`
- tg_topics: `build_tg_topics`
- twitter_following: `build_twitter_following_summary`
- meme_wait: `wait_meme_radar`
- tg_addr_merge: `merge_tg_addr_candidates_into_radar`
- twitter_ca_topics: `build_twitter_ca_topics`
- token_threads: `build_token_thread_summaries`
- narrative_assets: `infer_narrative_assets_from_tg`
- social_cards: `build_social_cards`
- sentiment_watch: `compute_sentiment_and_watch`

`hourly.py`
```python
from market_ops.pipeline.runner import PipelineRunner
from market_ops.pipeline.steps import (
    health_check, meme_spawn, tg_fetch, human_texts, oi_items, oi_plans,
    viewpoint_threads, tg_topics, twitter_following, meme_wait, tg_addr_merge,
    twitter_ca_topics, token_threads, narrative_assets, social_cards, sentiment_watch,
)


def run_hourly(ctx):
    steps = [
        ("health_check", health_check.step),
        ("meme_spawn", meme_spawn.step),
        ("tg_fetch", tg_fetch.step),
        ("human_texts", human_texts.step),
        ("oi_items", oi_items.step),
        ("oi_plans", oi_plans.step),
        ("viewpoint_threads", viewpoint_threads.step),
        ("tg_topics", tg_topics.step),
        ("twitter_following", twitter_following.step),
        ("meme_wait", meme_wait.step),
        ("tg_addr_merge", tg_addr_merge.step),
        ("twitter_ca_topics", twitter_ca_topics.step),
        ("token_threads", token_threads.step),
        ("narrative_assets", narrative_assets.step),
        ("social_cards", social_cards.step),
        ("sentiment_watch", sentiment_watch.step),
    ]
    PipelineRunner(ctx=ctx, steps=steps, continue_on_error=True).run()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_pipeline_runner.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/pipeline tests/market_ops/test_pipeline_runner.py
git commit -m "feat: add pipeline runner and hourly steps"
```

---

### Task 10: Facade + CLI

**Files:**
- Create: `src/market_ops/facade.py`
- Create: `src/market_ops/cli.py`
- Modify: `src/market_ops/__main__.py`
- Test: `tests/market_ops/test_cli.py`

**Step 1: Write failing CLI test (help output)**

```python
import subprocess
import os


def test_cli_help():
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    r = subprocess.run(["python3", "-m", "market_ops", "--help"], capture_output=True, text=True, env=env)
    assert r.returncode == 0
    assert "symbol" in r.stdout
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_cli.py -v`
Expected: FAIL

**Step 3: Implement facade + CLI**

`facade.py`
```python
from market_ops.schema import wrap_result
from market_ops.services.context_builder import build_context
from market_ops.pipeline.hourly import run_hourly
from market_ops.services.summary_render import render
from market_ops.services.symbol_analysis import analyze_symbol
from market_ops.services.ca_analysis import analyze_ca


def analyze_hourly(total_budget_s: float = 240.0) -> dict:
    ctx = build_context(total_budget_s=total_budget_s)
    run_hourly(ctx)
    summary = render(ctx)
    return wrap_result(mode="hourly", data={"prepared": summary}, summary=summary, errors=ctx.errors, use_llm=ctx.use_llm)


def analyze_symbol_facade(symbol: str, template: str = "dashboard", allow_llm: bool = True) -> dict:
    out = analyze_symbol(symbol, template=template, allow_llm=allow_llm)
    return wrap_result(mode="symbol", data=out.get("data", {}), summary=out.get("summary"), errors=out.get("errors", []), use_llm=out.get("use_llm", False))


def analyze_ca_facade(addr: str, allow_llm: bool = True) -> dict:
    out = analyze_ca(addr, allow_llm=allow_llm)
    return wrap_result(mode="ca", data=out.get("data", {}), summary=out.get("summary"), errors=out.get("errors", []), use_llm=out.get("use_llm", False))
```

`cli.py`
```python
import argparse
import json
from market_ops.facade import analyze_hourly, analyze_symbol_facade, analyze_ca_facade


def main():
    ap = argparse.ArgumentParser(prog="market_ops")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("symbol")
    s.add_argument("symbol")
    s.add_argument("--template", default="dashboard", choices=["dashboard", "plan"])
    s.add_argument("--no-llm", action="store_true")

    c = sub.add_parser("ca")
    c.add_argument("address")
    c.add_argument("--no-llm", action="store_true")

    h = sub.add_parser("hourly")
    h.add_argument("--budget", type=float, default=240.0)

    args = ap.parse_args()

    if args.cmd == "symbol":
        out = analyze_symbol_facade(args.symbol, template=args.template, allow_llm=not args.no_llm)
    elif args.cmd == "ca":
        out = analyze_ca_facade(args.address, allow_llm=not args.no_llm)
    else:
        out = analyze_hourly(total_budget_s=args.budget)

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

`__main__.py`
```python
from market_ops.cli import main

if __name__ == "__main__":
    main()
```

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_cli.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/market_ops/facade.py src/market_ops/cli.py src/market_ops/__main__.py tests/market_ops/test_cli.py
git commit -m "feat: add facade and unified CLI"
```

---

### Task 11: Remove legacy scripts + update docs/skills + tests

**Files:**
- Remove: `scripts/` and `scripts/market_hourly/`
- Modify: `README.md`
- Modify: `skills/*` to use `PYTHONPATH=src python -m market_ops ...`
- Modify: `references/*` to new CLI
- Modify: `tests/test_*.py` to import from `market_ops.*`

**Step 1: Write failing test (import path no longer exists)**

```python
import importlib


def test_legacy_scripts_removed():
    assert importlib.util.find_spec("scripts.hourly_market_summary") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src pytest tests/market_ops/test_legacy_removed.py -v`
Expected: FAIL

**Step 3: Remove old scripts + update docs**

- Delete `scripts/` tree
- Update docs/skills to show new CLI commands
- Update tests to import from `market_ops.*`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=src pytest tests/market_ops/test_legacy_removed.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add README.md skills references tests/market_ops/test_legacy_removed.py tests
+git rm -r scripts
+git commit -m "chore: remove legacy scripts and update docs"
```

---

## Execution Notes
- All tests should be run with `PYTHONPATH=src`.
- If dependencies are missing, create a venv: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

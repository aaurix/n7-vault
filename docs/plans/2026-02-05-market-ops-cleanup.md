# Market Ops Cleanup (Option 2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove unused shims, delete genuinely dead code, and reduce over‑splitting by merging render/metrics helpers into primary modules while keeping behavior intact.

**Architecture:** Delete `narratives.py`, remove `twitter_context.py` shim, fold `metrics_report.py` into `summary_render.py`, fold `twitter_following_render.py` into `twitter_following.py`. Update imports/tests accordingly. No behavioral changes beyond file moves.

**Tech Stack:** Python 3.14, pytest.

---

### Task 1: Remove unused `narratives.py`

**Files:**
- Delete: `scripts/market_ops/narratives.py`
- Test: `tests/market_ops/test_symbol_ca_smoke.py`

**Step 1: Write the failing test**

Add a guard test to ensure `narratives` module is absent.

```python
import importlib.util


def test_narratives_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.narratives") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_ca_smoke.py::test_narratives_module_removed -v`
Expected: FAIL (module still exists)

**Step 3: Delete file**

Remove `scripts/market_ops/narratives.py`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_symbol_ca_smoke.py::test_narratives_module_removed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/market_ops/test_symbol_ca_smoke.py
git rm scripts/market_ops/narratives.py
git commit -m "chore: remove unused narratives module"
```

---

### Task 2: Remove twitter_context shim

**Files:**
- Delete: `scripts/market_ops/twitter_context.py`
- Modify: `scripts/market_ops/oi_plan_pipeline.py`
- Modify: `scripts/market_ops/services/symbol_analysis.py`
- Modify: `scripts/market_ops/services/ca_analysis.py`
- Test: `tests/test_twitter_evidence.py`

**Step 1: Write the failing test**

Add a guard test to ensure `twitter_context` module is absent.

```python
import importlib.util


def test_twitter_context_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.twitter_context") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/test_twitter_evidence.py::test_twitter_context_module_removed -v`
Expected: FAIL (module still exists)

**Step 3: Update imports + delete shim**

- Replace imports to `from .services.twitter_evidence import ...`
- Delete `scripts/market_ops/twitter_context.py`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_twitter_evidence.py::test_twitter_context_module_removed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_ops/oi_plan_pipeline.py scripts/market_ops/services/symbol_analysis.py scripts/market_ops/services/ca_analysis.py tests/test_twitter_evidence.py
git rm scripts/market_ops/twitter_context.py
git commit -m "chore: remove twitter_context shim"
```

---

### Task 3: Merge metrics_report into summary_render

**Files:**
- Modify: `scripts/market_ops/services/summary_render.py`
- Delete: `scripts/market_ops/services/metrics_report.py`
- Test: `tests/market_ops/test_pipeline_runner.py`

**Step 1: Write the failing test**

Add a guard test to ensure `metrics_report` module is absent.

```python
import importlib.util


def test_metrics_report_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.metrics_report") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_pipeline_runner.py::test_metrics_report_module_removed -v`
Expected: FAIL (module still exists)

**Step 3: Move implementation**

- Move `build_metrics_report` into `summary_render.py`
- Update internal call to use the local function
- Delete `metrics_report.py`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_pipeline_runner.py::test_metrics_report_module_removed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_ops/services/summary_render.py tests/market_ops/test_pipeline_runner.py
git rm scripts/market_ops/services/metrics_report.py
git commit -m "refactor: inline metrics report into summary_render"
```

---

### Task 4: Merge twitter_following_render into twitter_following

**Files:**
- Modify: `scripts/market_ops/services/twitter_following.py`
- Delete: `scripts/market_ops/services/twitter_following_render.py`
- Test: `tests/market_ops/test_meme_radar_engine.py`

**Step 1: Write the failing test**

Add a guard test to ensure `twitter_following_render` module is absent.

```python
import importlib.util


def test_twitter_following_render_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.twitter_following_render") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_meme_radar_engine.py::test_twitter_following_render_removed -v`
Expected: FAIL (module still exists)

**Step 3: Move implementation**

- Move helper functions from `twitter_following_render.py` into `twitter_following.py`
- Update imports to local functions
- Delete `twitter_following_render.py`

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_meme_radar_engine.py::test_twitter_following_render_removed -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scripts/market_ops/services/twitter_following.py tests/market_ops/test_meme_radar_engine.py
git rm scripts/market_ops/services/twitter_following_render.py
git commit -m "refactor: inline twitter_following_render helpers"
```

---

### Task 5: Full verification

**Step 1: Run full test suite**

Run: `PYTHONPATH=. /Users/massis/.openclaw/workspace/.venv/bin/pytest`
Expected: PASS

**Step 2: Commit final cleanup if needed**

```bash
git add -A
git commit -m "chore: finalize market_ops cleanup" || true
```


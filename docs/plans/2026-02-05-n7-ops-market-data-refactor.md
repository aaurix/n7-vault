# N7-ops Market-Data Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move kline and market-data helpers into `scripts/market_data/utils`, relocate PushDeer sender into `scripts/ops/notify`, and update all imports/tests to new module paths.

**Architecture:** Keep data access in `market_data` utilities, keep market-ops orchestration clean, and move notification code under `ops/notify`. No new job script for PushDeer.

**Tech Stack:** Python 3.14, pytest, git submodules (N7-ops).

---

### Task 1: Add guard tests for new module locations

**Files:**
- Modify: `tests/market_ops/test_structure.py`
- Create: `tests/test_ops_notify.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_kline_fetcher_moved_to_market_data():
    assert importlib.util.find_spec("scripts.market_data.utils.kline_fetcher") is not None
    assert importlib.util.find_spec("scripts.market_ops.kline_fetcher") is None


def test_market_data_helpers_moved():
    assert importlib.util.find_spec("scripts.market_data.utils.market_data_helpers") is not None
    assert importlib.util.find_spec("scripts.market_ops.market_data_helpers") is None
```

Create `tests/test_ops_notify.py`:
```python
import importlib.util


def test_pushdeer_location():
    assert importlib.util.find_spec("scripts.ops.notify.pushdeer") is not None
    assert importlib.util.find_spec("scripts.pushdeer_send") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_kline_fetcher_moved_to_market_data -v`
Expected: FAIL (new module missing)

Run: `PYTHONPATH=. pytest tests/test_ops_notify.py::test_pushdeer_location -v`
Expected: FAIL

**Step 3: Commit**
```bash
git add tests/market_ops/test_structure.py tests/test_ops_notify.py

git commit -m "test: guard new market-data and ops module locations"
```

---

### Task 2: Move kline_fetcher into market_data utils

**Files (N7-ops submodule):**
- Move: `scripts/market_ops/kline_fetcher.py` -> `scripts/market_data/utils/kline_fetcher.py`
- Modify: `scripts/market_ops/features/oi/service.py`
- Modify: `scripts/market_ops/features/symbol/service.py`
- Test update: `tests/market_ops/test_kline_context.py`

**Step 1: Write minimal implementation**

- Move file to `scripts/market_data/utils/kline_fetcher.py`.
- Update imports in N7-ops:
  - `features/oi/service.py` -> `from scripts.market_data.utils.kline_fetcher import run_kline_json`
  - `features/symbol/service.py` -> same update.
- Update `tests/market_ops/test_kline_context.py` to import from new path.
- Remove old module path.

**Step 2: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_kline_context.py -v`
Expected: PASS

**Step 3: Commit (inside submodule)**
```bash
git -C scripts add scripts/market_data/utils/kline_fetcher.py scripts/market_ops/features/oi/service.py scripts/market_ops/features/symbol/service.py

git -C scripts commit -m "refactor: move kline fetcher to market_data utils"
```

---

### Task 3: Move market_data_helpers into market_data utils

**Files (N7-ops submodule):**
- Move: `scripts/market_ops/market_data_helpers.py` -> `scripts/market_data/utils/market_data_helpers.py`
- Modify: `scripts/market_ops/services/social_cards.py`
- Modify: `scripts/market_ops/features/topics/twitter.py`
- Test update: `tests/market_ops/test_market_data.py`

**Step 1: Write minimal implementation**

- Move helper file to `scripts/market_data/utils/market_data_helpers.py`.
- Update imports:
  - `services/social_cards.py`
  - `features/topics/twitter.py`
- Update `tests/market_ops/test_market_data.py` to use new path.
- Remove old module path.

**Step 2: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_market_data.py -v`
Expected: PASS

**Step 3: Commit (inside submodule)**
```bash
git -C scripts add scripts/market_data/utils/market_data_helpers.py scripts/market_ops/services/social_cards.py scripts/market_ops/features/topics/twitter.py

git -C scripts commit -m "refactor: move market_data_helpers to market_data utils"
```

---

### Task 4: Move PushDeer sender into ops/notify

**Files (N7-ops submodule):**
- Create: `scripts/ops/__init__.py`
- Create: `scripts/ops/notify/__init__.py`
- Move: `scripts/pushdeer_send.py` -> `scripts/ops/notify/pushdeer.py`

**Step 1: Write minimal implementation**

- Create package dirs + `__init__.py` files.
- Move file to `scripts/ops/notify/pushdeer.py`.
- Update any references if found (rg `pushdeer_send`).

**Step 2: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/test_ops_notify.py -v`
Expected: PASS

**Step 3: Commit (inside submodule)**
```bash
git -C scripts add scripts/ops/__init__.py scripts/ops/notify/__init__.py scripts/ops/notify/pushdeer.py

git -C scripts commit -m "refactor: move pushdeer sender under ops notify"
```

---

### Task 5: Update submodule pointer + full verification

**Files (root repo):**
- Modify: `scripts` gitlink
- Modify: `tests/market_ops/test_structure.py`
- Modify: `tests/test_ops_notify.py`

**Step 1: Update submodule pointer**

Run: `git add scripts` (after submodule commits)

**Step 2: Run full test suite**

Run: `PYTHONPATH=. /Users/massis/.openclaw/workspace/.venv/bin/pytest`
Expected: PASS

**Step 3: Commit**
```bash
git add scripts tests/market_ops/test_structure.py tests/test_ops_notify.py tests/market_ops/test_kline_context.py tests/market_ops/test_market_data.py

git commit -m "refactor: align market_data helpers and ops notify"
```


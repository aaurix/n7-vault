# Market Ops Feature-Slice Refactor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure `scripts/market_ops` into a feature-sliced layout with `features/`, `shared/`, `output/`, and `jobs/`, removing old module paths and updating imports and entrypoints.

**Architecture:** Move domain logic into `features/<domain>/`, cross-domain helpers into `shared/`, output formatting into `output/`, and shell entrypoints into `scripts/jobs/`. Pipeline steps only orchestrate features and context, and no compatibility shims remain.

**Tech Stack:** Python 3.14, pytest.

---

### Task 1: Add output package + migrate WhatsApp rendering

**Files:**
- Create: `scripts/market_ops/output/__init__.py`
- Create: `scripts/market_ops/output/whatsapp.py`
- Delete: `scripts/market_ops/render.py`
- Modify: `scripts/market_ops/pipeline/steps/*` (imports referencing render)
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Add to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_output_whatsapp_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.whatsapp") is not None


def test_render_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.render") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_output_whatsapp_module_exists -v`
Expected: FAIL (module missing)

**Step 3: Write minimal implementation**

- Create `scripts/market_ops/output/__init__.py`.
- Move contents of `scripts/market_ops/render.py` into `scripts/market_ops/output/whatsapp.py`.
- Update imports from `scripts.market_ops.render` to `scripts.market_ops.output.whatsapp`.
- Delete `scripts/market_ops/render.py`.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_output_whatsapp_module_exists -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/output/__init__.py scripts/market_ops/output/whatsapp.py tests/market_ops/test_structure.py

git rm scripts/market_ops/render.py

git commit -m "refactor: move whatsapp rendering into output"
```

---

### Task 2: Migrate summary rendering to output/summary.py

**Files:**
- Create: `scripts/market_ops/output/summary.py`
- Delete: `scripts/market_ops/services/summary_render.py`
- Modify: `scripts/market_ops/services/*`, `scripts/market_ops/pipeline/*` (imports)
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_output_summary_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.output.summary") is not None


def test_summary_render_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.summary_render") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_output_summary_module_exists -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move `scripts/market_ops/services/summary_render.py` to `scripts/market_ops/output/summary.py`.
- Update imports to `scripts.market_ops.output.summary`.
- Delete the old file.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_output_summary_module_exists -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/output/summary.py tests/market_ops/test_structure.py

git rm scripts/market_ops/services/summary_render.py

git commit -m "refactor: move summary render into output"
```

---

### Task 3: Create shared package and move filters

**Files:**
- Create: `scripts/market_ops/shared/__init__.py`
- Create: `scripts/market_ops/shared/filters.py`
- Delete: `scripts/market_ops/filters.py`
- Modify: all imports referencing `scripts.market_ops.filters`
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_shared_filters_module_exists():
    assert importlib.util.find_spec("scripts.market_ops.shared.filters") is not None


def test_filters_module_removed():
    assert importlib.util.find_spec("scripts.market_ops.filters") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_shared_filters_module_exists -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move `scripts/market_ops/filters.py` to `scripts/market_ops/shared/filters.py`.
- Create `scripts/market_ops/shared/__init__.py`.
- Update all imports to `scripts.market_ops.shared.filters`.
- Delete old file.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_shared_filters_module_exists -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/shared/__init__.py scripts/market_ops/shared/filters.py tests/market_ops/test_structure.py

git rm scripts/market_ops/filters.py

git commit -m "refactor: move filters into shared"
```

---

### Task 4: Migrate OI feature modules

**Files:**
- Create: `scripts/market_ops/features/oi/__init__.py`
- Create: `scripts/market_ops/features/oi/service.py`
- Create: `scripts/market_ops/features/oi/plan.py`
- Delete: `scripts/market_ops/oi.py`
- Delete: `scripts/market_ops/services/oi_service.py`
- Delete: `scripts/market_ops/oi_plan_pipeline.py`
- Modify: imports referencing these modules
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_oi_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.oi.service") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.oi.plan") is not None


def test_oi_legacy_modules_removed():
    assert importlib.util.find_spec("scripts.market_ops.oi") is None
    assert importlib.util.find_spec("scripts.market_ops.services.oi_service") is None
    assert importlib.util.find_spec("scripts.market_ops.oi_plan_pipeline") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_oi_feature_modules_exist -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Create `scripts/market_ops/features/oi/__init__.py`.
- Move/merge `scripts/market_ops/oi.py` and `scripts/market_ops/services/oi_service.py` into `features/oi/service.py`.
- Move `scripts/market_ops/oi_plan_pipeline.py` into `features/oi/plan.py`.
- Update imports across pipeline/steps and services to new paths.
- Delete old modules.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_oi_feature_modules_exist -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/features/oi/__init__.py scripts/market_ops/features/oi/service.py scripts/market_ops/features/oi/plan.py tests/market_ops/test_structure.py

git rm scripts/market_ops/oi.py scripts/market_ops/services/oi_service.py scripts/market_ops/oi_plan_pipeline.py

git commit -m "refactor: move oi into feature slice"
```

---

### Task 5: Migrate topics feature modules

**Files:**
- Create: `scripts/market_ops/features/topics/__init__.py`
- Create: `scripts/market_ops/features/topics/pipeline.py`
- Create: `scripts/market_ops/features/topics/tg.py`
- Create: `scripts/market_ops/features/topics/twitter.py`
- Create: `scripts/market_ops/features/topics/fallback.py`
- Delete: `scripts/market_ops/topic_pipeline.py`
- Delete: `scripts/market_ops/tg_topics_fallback.py`
- Delete: `scripts/market_ops/services/tg_topics.py`
- Delete: `scripts/market_ops/services/twitter_topics.py`
- Modify: imports referencing these modules
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_topics_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.topics.pipeline") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.tg") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.twitter") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.topics.fallback") is not None


def test_topics_legacy_modules_removed():
    assert importlib.util.find_spec("scripts.market_ops.topic_pipeline") is None
    assert importlib.util.find_spec("scripts.market_ops.tg_topics_fallback") is None
    assert importlib.util.find_spec("scripts.market_ops.services.tg_topics") is None
    assert importlib.util.find_spec("scripts.market_ops.services.twitter_topics") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_topics_feature_modules_exist -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Create `scripts/market_ops/features/topics/__init__.py`.
- Move topic pipeline/fallback/services into the new files.
- Update imports in pipeline steps and services.
- Delete old files.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_topics_feature_modules_exist -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/features/topics/__init__.py scripts/market_ops/features/topics/pipeline.py scripts/market_ops/features/topics/tg.py scripts/market_ops/features/topics/twitter.py scripts/market_ops/features/topics/fallback.py tests/market_ops/test_structure.py

git rm scripts/market_ops/topic_pipeline.py scripts/market_ops/tg_topics_fallback.py scripts/market_ops/services/tg_topics.py scripts/market_ops/services/twitter_topics.py

git commit -m "refactor: move topics into feature slice"
```

---

### Task 6: Migrate symbol + CA feature modules

**Files:**
- Create: `scripts/market_ops/features/symbol/__init__.py`
- Create: `scripts/market_ops/features/symbol/service.py`
- Create: `scripts/market_ops/features/ca/__init__.py`
- Create: `scripts/market_ops/features/ca/service.py`
- Delete: `scripts/market_ops/services/symbol_analysis.py`
- Delete: `scripts/market_ops/services/ca_analysis.py`
- Modify: imports referencing these modules
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_symbol_ca_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.symbol.service") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.ca.service") is not None


def test_symbol_ca_legacy_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.symbol_analysis") is None
    assert importlib.util.find_spec("scripts.market_ops.services.ca_analysis") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_symbol_ca_feature_modules_exist -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move `services/symbol_analysis.py` -> `features/symbol/service.py`.
- Move `services/ca_analysis.py` -> `features/ca/service.py`.
- Create feature `__init__.py` files.
- Update all imports to the new paths.
- Delete old files.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_symbol_ca_feature_modules_exist -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/features/symbol/__init__.py scripts/market_ops/features/symbol/service.py scripts/market_ops/features/ca/__init__.py scripts/market_ops/features/ca/service.py tests/market_ops/test_structure.py

git rm scripts/market_ops/services/symbol_analysis.py scripts/market_ops/services/ca_analysis.py

git commit -m "refactor: move symbol and ca into feature slices"
```

---

### Task 7: Migrate meme radar + twitter following features

**Files:**
- Create: `scripts/market_ops/features/meme_radar/__init__.py`
- Create: `scripts/market_ops/features/meme_radar/service.py`
- Create: `scripts/market_ops/features/meme_radar/engine.py`
- Create: `scripts/market_ops/features/twitter_following/__init__.py`
- Create: `scripts/market_ops/features/twitter_following/service.py`
- Delete: `scripts/market_ops/services/meme_radar.py`
- Delete: `scripts/market_ops/services/meme_radar_engine.py`
- Delete: `scripts/market_ops/services/twitter_following.py`
- Modify: imports referencing these modules
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_meme_radar_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.meme_radar.service") is not None
    assert importlib.util.find_spec("scripts.market_ops.features.meme_radar.engine") is not None


def test_twitter_following_feature_modules_exist():
    assert importlib.util.find_spec("scripts.market_ops.features.twitter_following.service") is not None


def test_meme_radar_legacy_removed():
    assert importlib.util.find_spec("scripts.market_ops.services.meme_radar") is None
    assert importlib.util.find_spec("scripts.market_ops.services.meme_radar_engine") is None
    assert importlib.util.find_spec("scripts.market_ops.services.twitter_following") is None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_meme_radar_feature_modules_exist -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move meme radar service/engine to new feature paths.
- Move twitter following service to new feature path.
- Create feature `__init__.py` files.
- Update imports in pipeline steps and services.
- Delete old files.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_meme_radar_feature_modules_exist -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/features/meme_radar/__init__.py scripts/market_ops/features/meme_radar/service.py scripts/market_ops/features/meme_radar/engine.py scripts/market_ops/features/twitter_following/__init__.py scripts/market_ops/features/twitter_following/service.py tests/market_ops/test_structure.py

git rm scripts/market_ops/services/meme_radar.py scripts/market_ops/services/meme_radar_engine.py scripts/market_ops/services/twitter_following.py

git commit -m "refactor: move meme radar and twitter following into features"
```

---

### Task 8: Migrate remaining shared utilities

**Files:**
- Create: `scripts/market_ops/shared/<file>.py`
- Delete: `scripts/market_ops/services/<file>.py` (selected utils)
- Modify: imports referencing these modules
- Test: `tests/market_ops/test_structure.py`

**Step 1: Write the failing test**

Append to `tests/market_ops/test_structure.py`:
```python
import importlib.util


def test_shared_utils_exist():
    assert importlib.util.find_spec("scripts.market_ops.shared.entity_resolver") is not None
    assert importlib.util.find_spec("scripts.market_ops.shared.evidence_cleaner") is not None
    assert importlib.util.find_spec("scripts.market_ops.shared.diagnostics") is not None
    assert importlib.util.find_spec("scripts.market_ops.shared.state_manager") is not None
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_shared_utils_exist -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Move `services/entity_resolver.py` -> `shared/entity_resolver.py`.
- Move `services/evidence_cleaner.py` -> `shared/evidence_cleaner.py`.
- Move `services/diagnostics.py` -> `shared/diagnostics.py`.
- Move `services/state_manager.py` -> `shared/state_manager.py`.
- Update imports to new paths and delete old files.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_structure.py::test_shared_utils_exist -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/market_ops/shared/entity_resolver.py scripts/market_ops/shared/evidence_cleaner.py scripts/market_ops/shared/diagnostics.py scripts/market_ops/shared/state_manager.py tests/market_ops/test_structure.py

git rm scripts/market_ops/services/entity_resolver.py scripts/market_ops/services/evidence_cleaner.py scripts/market_ops/services/diagnostics.py scripts/market_ops/services/state_manager.py

git commit -m "refactor: move shared utilities out of services"
```

---

### Task 9: Move shell jobs into scripts/jobs

**Files:**
- Create: `scripts/jobs/`
- Move + rename:
  - `scripts/auto_watchdog.sh` -> `scripts/jobs/job_auto_watchdog.sh`
  - `scripts/monitor_health.sh` -> `scripts/jobs/job_monitor_health.sh`
  - `scripts/scan_skills.sh` -> `scripts/jobs/job_scan_skills.sh`
  - `scripts/update_skills_inventory.sh` -> `scripts/jobs/job_update_skills_inventory.sh`
- Modify: any cron/docs references
- Test: `tests/market_ops/test_jobs_layout.py`

**Step 1: Write the failing test**

Create `tests/market_ops/test_jobs_layout.py`:
```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_jobs_layout():
    jobs = ROOT / "scripts" / "jobs"
    assert (jobs / "job_auto_watchdog.sh").exists()
    assert (jobs / "job_monitor_health.sh").exists()
    assert (jobs / "job_scan_skills.sh").exists()
    assert (jobs / "job_update_skills_inventory.sh").exists()

    assert not (ROOT / "scripts" / "auto_watchdog.sh").exists()
    assert not (ROOT / "scripts" / "monitor_health.sh").exists()
    assert not (ROOT / "scripts" / "scan_skills.sh").exists()
    assert not (ROOT / "scripts" / "update_skills_inventory.sh").exists()
```

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=. pytest tests/market_ops/test_jobs_layout.py -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Create `scripts/jobs/`.
- Move and rename the scripts.
- Update any references in docs/cron configs to the new paths.

**Step 4: Run test to verify it passes**

Run: `PYTHONPATH=. pytest tests/market_ops/test_jobs_layout.py -v`
Expected: PASS

**Step 5: Commit**
```bash
git add scripts/jobs/job_auto_watchdog.sh scripts/jobs/job_monitor_health.sh scripts/jobs/job_scan_skills.sh scripts/jobs/job_update_skills_inventory.sh tests/market_ops/test_jobs_layout.py

git rm scripts/auto_watchdog.sh scripts/monitor_health.sh scripts/scan_skills.sh scripts/update_skills_inventory.sh

git commit -m "chore: move job scripts into jobs directory"
```

---

### Task 10: Full verification

**Step 1: Run full test suite**

Run: `PYTHONPATH=. /Users/massis/.openclaw/workspace/.venv/bin/pytest`
Expected: PASS

**Step 2: Commit final cleanup if needed**
```bash
git add -A

git commit -m "chore: finalize market ops structure refactor" || true
```


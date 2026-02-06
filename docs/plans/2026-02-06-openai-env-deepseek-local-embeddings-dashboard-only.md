# OpenAI Env + DeepSeek Base URL + Local Embeddings + Dashboard-Only Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove OpenRouter usage from `scripts/`, unify all runtime configuration under `OPENAI_*`, switch embeddings to local `SentenceTransformers`, and delete the non-pro `plan` template (keep `dashboard` professional report only).

**Architecture:** Chat requests use an OpenAI-compatible endpoint configured by `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_CHAT_MODEL`. Embeddings run locally via `sentence-transformers` (`BAAI/bge-small-zh-v1.5`) behind the existing `embeddings()` function and are only enabled when the local backend is available.

**Tech Stack:** Python, urllib (OpenAI-compatible HTTP), `sentence-transformers` (optional local embeddings), pytest.

---

### Task 1: Create/Update Tests for Dashboard-Only Symbol Report

**Files:**
- Modify: `tests/market_ops/test_symbol_report_sections.py`

**Step 1: Write the failing test (remove template arg)**

Update calls to `build_symbol_sections()` and `render_symbol_report()` so they no longer pass/accept `template=...`.

**Step 2: Run tests to verify RED**

Run:
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/market_ops/test_symbol_report_sections.py
```
Expected: FAIL with `TypeError: ... missing 1 required keyword-only argument: 'template'`.

---

### Task 2: Remove `plan` Template Codepaths (Dashboard Only)

**Files:**
- Modify: `scripts/market_ops/cli.py`
- Modify: `scripts/market_ops/facade.py`
- Modify: `scripts/market_ops/features/symbol/service.py`
- Modify: `scripts/market_ops/output/symbol_report.py`

**Step 1: Implement minimal code to pass Task 1 tests**
- Remove `--template` from CLI.
- Remove `template` argument from `analyze_symbol_facade()` and `analyze_symbol()`.
- Delete `_llm_plan()` / `_rule_plan()` and all `template == "plan"` branches.
- In renderer, drop template branching and update title to a single professional title (dashboard).

**Step 2: Run focused tests**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/market_ops/test_symbol_report_sections.py
```
Expected: PASS.

**Step 3: Run full test suite**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```
Expected: PASS (same count as baseline).

---

### Task 3: Add Tests for `OPENAI_*` Chat Config Resolution (No Network)

**Files:**
- Create: `tests/market_ops/test_llm_openai_config.py`

**Step 1: Write the failing test**

Add tests that:
- `OPENAI_API_KEY` is required for chat.
- `OPENAI_BASE_URL` default is `https://api.openai.com/v1` and is normalized (no trailing slash).
- `OPENAI_CHAT_MODEL` is used when `model=""` is passed to resolver.

**Step 2: Run tests to verify RED**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q tests/market_ops/test_llm_openai_config.py
```
Expected: FAIL until implementation exists.

---

### Task 4: Remove OpenRouter Routing and Switch Chat to `OPENAI_*`

**Files:**
- Modify: `scripts/market_ops/llm_openai/keys.py`
- Modify: `scripts/market_ops/llm_openai/chat.py`
- Modify: `scripts/market_ops/llm_openai/__init__.py`

**Step 1: Implement minimal code to pass Task 3 tests**
- Delete `load_openrouter_api_key()` and any `OPENROUTER_*` usage.
- `load_chat_api_key()` returns `OPENAI_API_KEY` (same as `load_openai_api_key()`).
- `_resolve_chat_endpoint()` reads `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_CHAT_MODEL`.
- Keep `chat_json()` API stable and OpenAI-compatible (POST `${OPENAI_BASE_URL}/chat/completions`).

**Step 2: Run full test suite**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

---

### Task 5: Switch Embeddings to Local `SentenceTransformers` (Optional Dependency)

**Files:**
- Modify: `scripts/market_ops/llm_openai/embeddings.py`
- Modify: `scripts/market_ops/services/context_builder.py`

**Step 1: Implement local embeddings**
- Implement `embeddings()` using `sentence_transformers.SentenceTransformer(...).encode(...)`.
- Default model: `BAAI/bge-small-zh-v1.5` (overridable via `OPENAI_EMBEDDINGS_MODEL`).
- Cache key must include backend+model to avoid mixing old OpenAI vectors.
- Add a lightweight availability helper (import-only) so `ctx.use_embeddings` is correct without loading the full model.

**Step 2: Run full test suite**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```

---

### Task 6: Update Skill Scan Script Patterns (Remove OpenRouter)

**Files:**
- Modify: `scripts/jobs/job_scan_skills.sh`

**Step 1: Update patterns**
- Remove `OPENROUTER_API_KEY`
- Add `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL`, `OPENAI_EMBEDDINGS_MODEL`

**Step 2: Sanity run (no need to commit output)**
```bash
bash scripts/jobs/job_scan_skills.sh skills /tmp/skills_scan_test.txt
```
Expected: Writes report without error.

---

### Task 7: Docs and Long-Term Memory Updates

**Files:**
- Modify: `MEMORY.md`
- Modify: `docs/plans/2026-02-05-market-data-architecture-design.md`

**Step 1: Update text**
- Replace “OpenRouter Chat API” with “OpenAI-compatible Chat API (OPENAI_BASE_URL)”.
- Update `MEMORY.md` routing note accordingly.

**Step 2: Run full test suite**
```bash
PYTHONPATH=. .venv/bin/python -m pytest -q
```


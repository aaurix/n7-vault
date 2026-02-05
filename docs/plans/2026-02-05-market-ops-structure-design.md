# Market Ops Feature-Slice Structure Design

**Date:** 2026-02-05

## Goal
Restructure `scripts/market_ops` into feature-sliced modules with clear boundaries, unified naming, and a dedicated `jobs/` directory for shell entrypoints. Remove ambiguity between analysis/render/fallback layers and make pipeline orchestration clean and stable.

## Scope
- Convert market ops to feature-slice layout (`features/<domain>/...`).
- Centralize cross-domain utilities in `shared/`.
- Centralize output formatting in `output/`.
- Move all `.sh` scripts into `scripts/jobs/` using a consistent naming scheme.
- Remove old file paths (no compatibility shims).

## Design Principles
- **Feature-first:** Each domain owns its own logic and rendering.
- **Pipeline-only orchestration:** `pipeline/steps/*` only wires services and context.
- **Single output boundary:** `output/` owns WhatsApp/markdown formatting.
- **Single data boundary:** data access comes from `scripts/market_data` only.
- **Explicit fallbacks:** fallback logic lives inside its feature.

## Target Directory Layout
```
scripts/market_ops/
  __main__.py  cli.py  facade.py  config.py  models.py  schema.py
  pipeline/
    runner.py
    hourly.py
    steps/
      ... (step modules)
  features/
    oi/
      service.py
      plan.py
      render.py
      fallback.py
    topics/
      pipeline.py
      tg.py
      twitter.py
      fallback.py
    symbol/
      service.py
      render.py
    ca/
      service.py
      render.py
    meme_radar/
      service.py
      render.py
      engine.py
    twitter_following/
      service.py
      render.py
    sentiment/
      service.py
  shared/
    filters.py
    entity_resolver.py
    evidence_cleaner.py
    diagnostics.py
    state_manager.py
    actionable_normalization.py
    tg_preprocess.py
    twitter_evidence.py
    ...
  output/
    summary.py
    whatsapp.py
```

## Naming Conventions
- Domain modules: `features/<domain>/{service,render,fallback}.py`
- Pipeline steps: `pipeline/steps/<action>.py` (verb-noun, e.g. `oi_items.py`)
- Shared utilities: `shared/<utility>.py`
- Output: `output/summary.py`, `output/whatsapp.py`

## Jobs Directory Standard
- New location: `scripts/jobs/`
- Naming: `job_<task>.sh` (verb-noun, short)
  - Examples: `job_hourly_summary.sh`, `job_health_check.sh`, `job_skills_scan.sh`
- Scripts only call Python entrypoints.

## Migration Rules (Highlights)
- `render.py` -> `output/whatsapp.py`
- `services/summary_render.py` -> `output/summary.py`
- `oi.py` + `services/oi_service.py` -> `features/oi/service.py`
- `oi_plan_pipeline.py` -> `features/oi/plan.py`
- `topic_pipeline.py` -> `features/topics/pipeline.py`
- `tg_topics_fallback.py` -> `features/topics/fallback.py`
- `services/tg_topics.py` -> `features/topics/tg.py`
- `services/twitter_topics.py` -> `features/topics/twitter.py`
- `filters.py` -> `shared/filters.py`
- `services/*analysis.py` -> `features/<domain>/service.py`
- `services/*render*` -> `features/<domain>/render.py` or `output/`
- Cross-domain utilities -> `shared/`

## Verification
- Add guard tests to ensure old modules are removed.
- Run full suite: `PYTHONPATH=. pytest`.
- Smoke command: `python -m scripts.market_ops hourly`.


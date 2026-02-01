# Hourly pipeline package

This folder hosts the hourly market summary pipeline and its supporting services.

## Entry points
- `scripts/hourly_market_summary.py` → production summary JSON (WhatsApp + Markdown)
- `scripts/hourly_prepare.py` → deterministic data prep JSON (LLM/embeddings used if keys present)

## Structure
- `config.py` → static config (TZ + Telegram channel ids)
- `models.py` → `PipelineContext`, `TimeBudget`
- `llm_openai/` → chat + embeddings + parsing helpers for LLM calls
- `services/` → pipeline steps (TG ingest, OI, actionables, Twitter supplement, Twitter following analysis, social cards, render, etc.)

## Design goals
- Deterministic preprocessing + budget-aware LLM calls
- Lightweight observability via `metrics_report` in render output
- Clear module boundaries (no generic utils)
- Repo-root-relative state access via `HourlyStateManager`

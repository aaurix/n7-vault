# Models

## `PipelineContext`
Central, mutable pipeline state shared across steps.

Key fields:
- **time window**: `since`, `until`, `hour_key`, `now_sh`, `now_utc`
- **services**: `client` (Telegram), `state` (`HourlyStateManager`)
- **budget**: `TimeBudget` (deadline-based)
- **inputs**: `messages_by_chat`, `human_texts`, `oi_items`, `radar_items`
- **outputs**: `narratives`, `threads`, `twitter_topics`, `sentiment`, `watch`
- **diagnostics**: `perf`, `errors`, `llm_failures`

## `TimeBudget`
Monotonic, deadline-based helper with:
- `elapsed_s()`
- `remaining_s()`
- `over(reserve_s=...)`

## `HourlyStateManager`
State accessor for repo-root state:
- `load_meme_radar_output()` → `state/meme/last_candidates.json`

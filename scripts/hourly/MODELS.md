# Models

## `PipelineContext`
Central, mutable pipeline state shared across steps.

Key fields:
- **time window**: `since`, `until`, `hour_key`, `now_sh`, `now_utc`
- **services**: `client` (Telegram), `state` (`HourlyStateManager`)
- **budget**: `TimeBudget` (deadline-based)
- **inputs**: `messages_by_chat`, `human_texts`, `oi_items`, `radar_items`
- **outputs**: `narratives`, `threads`, `twitter_topics`, `social_cards`, `sentiment`, `watch`
- **diagnostics**: `perf`, `errors`, `llm_failures`, `tg_topics_fallback_reason`

## `TimeBudget`
Monotonic, deadline-based helper with:
- `elapsed_s()`
- `remaining_s()`
- `over(reserve_s=...)`

## `HourlyStateManager`
State accessor for repo-root state:
- `load_meme_radar_output()` → `state/meme/last_candidates.json`

## `SocialCard`
Unified TG/X card schema:
- `source` (tg/twitter)
- `symbol`, `symbol_type`, `addr`, `chain`
- `price`, `market_cap`, `fdv`
- `sentiment`, `one_liner`, `signals`, `evidence_snippets`
- `drivers` (2-3 catalysts when available), `risk`

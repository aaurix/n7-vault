# Hourly pipeline dataflow

## High-level flow
1. **Context**
   - Build time window (`since`, `until`) and init `PipelineContext`.
2. **Telegram ingest**
   - Fetch formula feed + viewpoint chats.
   - Filter bot/ads and build `human_texts`.
3. **OI pipeline**
   - Parse OI signals → enrich with kline data → Top N.
   - Optional LLM: trading plans (budget-gated).
4. **TG actionables**
   - Snippet prep → optional LLM → normalize.
   - Fallback: rule-based actionables from TG text.
5. **Meme radar**
   - Spawn async meme radar → load output → merge TG address candidates.
6. **Twitter supplement**
   - Build signal cards from radar evidence (LLM optional).
7. **Threads + narratives**
   - Token thread summaries (LLM optional).
   - Infer related assets for narratives.
8. **Sentiment + watchlist**
   - Combine TG + Twitter cues → watchlist.
9. **Render**
   - Build WhatsApp + Markdown summary + hash.

## State inputs
- Meme radar output: `state/meme/last_candidates.json`
- Cache files: `state/embeddings_cache.json`, `state/dexscreener_cache.json`

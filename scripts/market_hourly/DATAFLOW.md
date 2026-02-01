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
4. **TG topics (narratives)**
   - Deterministic prefilter → dedup → embeddings cluster (scored) → LLM → postfilter.
   - No-LLM path: cluster centers + keyword/entity extraction (embeddings optional).
   - Fallback: symbol-based extraction when clustering yields nothing.
5. **Meme radar**
   - Spawn async meme radar → load output → merge TG address candidates.
6. **Twitter supplement**
   - Build signal cards from radar evidence (LLM optional).
7. **Twitter following timeline**
   - Pull following timeline via bird (last 60 min) → summarize narratives/sentiment/major events.
8. **Social cards**
   - Unify TG actionables + Twitter cards into a shared schema.
   - Enrich price/MC where available via shared resolver/Dex client.
9. **Threads + assets**
   - Token thread summaries (LLM optional).
   - Infer related assets for narratives.
10. **Sentiment + watchlist**
   - Combine TG + Twitter cues → watchlist.
11. **Render**
   - Build WhatsApp + Markdown summary + hash.

## State inputs
- Meme radar output: `state/meme/last_candidates.json`
- Cache files: `state/embeddings_cache.json`, `state/dexscreener_cache.json`

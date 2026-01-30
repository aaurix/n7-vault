# MEMORY.md (Long-term)

## Projects
- **market-ops**: Hourly TG+Twitter market/meme summary + on-demand symbol/CA analysis.
  - Keep hourly output WhatsApp-friendly, concise, and trader-usable.
  - Prefer stability-first pipelines with time-budget gating.

## Current engineering decisions
- **Code changes must use Codex tooling**: for all design/code/script modifications, run work via Codex sub-tasks by default (Codex already configured as default; no need to manually specify the model each time unless overriding). Do not apply non-Codex changes as the source-of-truth.
- **Hourly pipeline architecture**: prefer **prepare→agent**. Prepare stage should be deterministic (no OpenAI HTTP calls); agent stage does summarization. WhatsApp outputs must be chunked <=950 chars.
- **On-demand token analysis architecture**: unified **prepare→agent** for symbol-based analysis; default output is **方案2 决策仪表盘** (scored, explainable, WhatsApp-friendly). Add an optional switch for 方案1 交易计划.
- **Token input normalization**: accept `$symbol`/`symbol`/`SYMBOL` and normalize to `SYMBOLUSDT` for market data; social anchor uses `$SYMBOL`. Default quote is USDT.
- **No raw quotes by default**: user-visible outputs should avoid quoting tweets/messages unless explicitly requested; provide “社交明细（无引用）” instead.
- **二级山寨 OI movers output**: for hourly summaries, prefer **mini 决策仪表盘** per top 2–3 perps (1H/4H structure + key levels + flow + action + risk). Fallback to simple `oi_lines` only when dashboards are unavailable.
- **Solana base58 detection**: constrain Solana address regex to length {32,44} to reduce false positives.
- **JSON contract discipline**:
  - `analyze_symbol --json` now returns plural keys when emitting items/plans (and symbol analysis is now prepare→agent with a richer JSON wrapper).
  - Hourly pipeline returns `summary_whatsapp_chunks` alongside `summary_whatsapp`.
- **Script LLM routing**: scripts’ chat/completions use **OpenRouter** (DeepSeek v3.2) via `OPENROUTER_API_KEY` / `OPENROUTER_CHAT_MODEL`; embeddings remain on OpenAI (`OPENAI_API_KEY`).
- **Cron WhatsApp delivery**: always send with explicit E.164 `target` (never `current`) and split messages into <=950-char chunks.
- **Git pushes**: default allow commit+push unless the user explicitly says “don’t push”. Don’t repeatedly ask/mention.
- **Dependency errors**: when cron/scripts fail due to missing tools (e.g., `rg`), prefer installing the dependency / fixing the environment over monkey-patching the script to avoid it.

## Ops / reminders
- Pill reminder acknowledgements are tracked locally in `memory/pill_ack.json`.

# MEMORY.md (Long-term)

## Projects
- **market-ops**: Hourly TG+Twitter market/meme summary + on-demand symbol/CA analysis.
  - Keep hourly output WhatsApp-friendly, concise, and trader-usable.
  - Prefer stability-first pipelines with time-budget gating.

## Long-term preferences & constraints (durable)
- **Code changes must use Codex sub-tasks**: all design/code/script modifications should be produced via Codex sub-tasks by default (Codex is already configured as default; no need to manually specify the model each time unless overriding).
- **No secrets in memory**: never store API keys, OAuth callback URLs, passwords, or other credentials in `MEMORY.md` or `memory/*.md`.
- **Input normalization**: accept `$symbol` forms; default quote is USDT; social anchor uses `$SYMBOL`.
- **Script LLM routing**: scripts’ chat/completions use an OpenAI-compatible endpoint via `OPENAI_BASE_URL` + `OPENAI_API_KEY` + `OPENAI_CHAT_MODEL`; embeddings default to local SentenceTransformers via `OPENAI_EMBEDDINGS_MODEL`.
- **Ops behavior**: default allow commit+push unless explicitly told not to; fix missing deps properly (no monkey patches).
- **Logging best practice**: follow official guidance—do not auto-log chats to daily. Only record key events/important execution rules as summaries when I judge they're important.

## Ops / reminders
- Pill reminder acknowledgements are tracked locally in `memory/pill_ack.json`.

# Hourly Pipeline

Primary entrypoint:
- `python3 -m scripts.market_ops hourly`
Optional flags:
- `--fresh` disables disk cache for this run
- `--cache-ttl exchange=300,onchain=900,social=60` overrides per-domain TTLs

Flow:
1. Telegram health check
2. Meme radar spawn
3. TG fetch + preprocess
4. OI items + plans
5. Viewpoint threads + TG topics
6. Twitter following summary
7. Meme radar merge + CA topics
8. Token threads + narrative assets
9. Social cards + sentiment/watch
10. Render summary

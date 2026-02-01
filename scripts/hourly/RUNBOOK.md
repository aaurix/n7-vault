# Runbook

## Run locally
```bash
python3 /Users/massis/clawd/scripts/hourly_market_summary.py
```

## Deterministic prep-only
```bash
python3 /Users/massis/clawd/scripts/hourly_prepare.py
```

## Common env flags
- `HOURLY_MARKET_SUMMARY_BUDGET_S=240` (default)

## Debugging tips
- Inspect `errors` and `llm_failures` in JSON output.
- `summary_whatsapp_chunks` must stay <= ~950 chars per chunk.
- TG service must be healthy (see `require_tg_health`).

# Debugging

Quick debugging steps for the hourly pipeline.

## Common commands
- Deterministic prep (no LLM): `HOURLY_PREP_USE_LLM=0 PYTHONPATH=src python3 -m market_ops hourly --budget 30 > /tmp/hourly_prepare.json`
- Full hourly JSON: `PYTHONPATH=src python3 -m market_ops hourly > /tmp/hourly_summary.json`

## Output rules
- WhatsApp chunk size must stay <= ~950 chars
- No raw quotes unless explicitly requested

# Testing

## Self-check (no LLM)
```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
from hourly.market_summary_pipeline import self_check_actionables
from hourly.services.social_cards import self_check_social_cards
from hourly.services.tg_preprocess import self_check_tg_preprocess
print(self_check_actionables())
print(self_check_social_cards())
print(self_check_tg_preprocess())
PY
```

## Compile check
```bash
python3 -m compileall scripts/hourly
```

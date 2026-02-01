# Testing

## Self-check (no LLM)
```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
from hourly.market_summary_pipeline import self_check_actionables
from hourly.services.social_cards import self_check_social_cards
from hourly.services.tg_preprocess import self_check_tg_preprocess
from hourly.tg_topics_fallback import self_check_tg_topics_fallback
from hourly.services.twitter_following import self_check_twitter_following
from hourly.render import WHATSAPP_CHUNK_MAX, split_whatsapp_text
print(self_check_actionables())
print(self_check_social_cards())
print(self_check_tg_preprocess())
print(self_check_tg_topics_fallback())
print(self_check_twitter_following())
assert all(len(x) <= WHATSAPP_CHUNK_MAX for x in split_whatsapp_text("x" * (WHATSAPP_CHUNK_MAX + 5)))
PY
```

## Pytest
```bash
pytest -q
```

## Compile check
```bash
python3 -m compileall scripts/hourly
```

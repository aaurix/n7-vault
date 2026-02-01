# Testing

## Self-check (no LLM)
```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "scripts")
from hourly.market_summary_pipeline import self_check_actionables
print(self_check_actionables())
PY
```

## Compile check
```bash
python3 -m compileall scripts/hourly
```

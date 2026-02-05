from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List


def wrap_result(
    *,
    mode: str,
    data: Dict[str, Any],
    summary: Any,
    errors: List[str],
    use_llm: bool = False,
    version: str = "v1",
) -> Dict[str, Any]:
    return {
        "meta": {
            "mode": mode,
            "version": version,
            "use_llm": bool(use_llm),
            "timestamp": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        },
        "data": data or {},
        "summary": summary,
        "errors": errors or [],
    }

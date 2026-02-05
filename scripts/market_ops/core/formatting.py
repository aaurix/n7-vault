from __future__ import annotations

from typing import Any, Optional


def _as_num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def fmt_pct(x: Any, *, digits: int = 1) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    return f"{v:+.{digits}f}%"


def fmt_num(x: Any, *, digits: int = 6) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    try:
        return f"{v:.{digits}g}"
    except Exception:
        return str(x)


def fmt_price(x: Any, *, digits: int = 4) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    try:
        if abs(v) >= 1000:
            return f"{v:.0f}"
        if abs(v) >= 100:
            return f"{v:.1f}"
        if abs(v) >= 10:
            return f"{v:.2f}"
        if abs(v) >= 1:
            return f"{v:.2f}"
        return f"{v:.{digits}g}" if v != 0 else "0"
    except Exception:
        return str(x)


def fmt_usd(x: Any) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    if abs(v) >= 1e12:
        return f"${v/1e12:.2f}T"
    if abs(v) >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


__all__ = ["fmt_pct", "fmt_num", "fmt_price", "fmt_usd"]

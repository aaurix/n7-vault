#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic perp mini-dashboard builder/renderer.

Designed for hourly summaries:
- Input is market_hourly.oi_plan_pipeline.build_oi_items() output (oi_items).
- Output is compact, WhatsApp-friendly lines (no raw quotes).

This module is intentionally dependency-free and stable.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def _as_num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_get(d: Any, *keys: str) -> Any:
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _fmt_pct(x: Any, *, digits: int = 1) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    return f"{v:+.{digits}f}%"


def _fmt_num(x: Any, *, digits: int = 4) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    # Keep deterministic; avoid scientific notation for typical crypto prices.
    try:
        if abs(v) >= 1000:
            return f"{v:.0f}"
        if abs(v) >= 100:
            return f"{v:.1f}"
        if abs(v) >= 10:
            return f"{v:.2f}"
        if abs(v) >= 1:
            return f"{v:.2f}"
        # sub-$1
        return f"{v:.{digits}g}" if v != 0 else "0"
    except Exception:
        return str(x)


def _fmt_usd(x: Any) -> str:
    v = _as_num(x)
    if v is None:
        return "?"
    try:
        if abs(v) >= 1e12:
            return f"${v/1e12:.2f}T"
        if abs(v) >= 1e9:
            return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"${v/1e3:.1f}K"
        return f"${v:.0f}"
    except Exception:
        return str(x)


def _pick_market_cap_fdv(it: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    def _pick_top(*keys: str) -> Optional[float]:
        for k in keys:
            v = _as_num(it.get(k))
            if v is not None:
                return v
        return None

    mc = _pick_top("market_cap", "marketCap", "mcap")
    fdv = _pick_top("fdv", "fully_diluted_valuation")

    market = it.get("market") if isinstance(it.get("market"), dict) else {}
    if mc is None:
        mc = _as_num(market.get("market_cap") or market.get("marketCap") or market.get("mcap"))
    if fdv is None:
        fdv = _as_num(market.get("fdv") or market.get("fully_diluted_valuation"))

    dex = it.get("dex") if isinstance(it.get("dex"), dict) else {}
    if mc is None:
        mc = _as_num(dex.get("marketCap") or dex.get("fdv"))
    if fdv is None:
        fdv = _as_num(dex.get("fdv"))

    return mc, fdv


def flow_label(*, px_chg: Optional[float], oi_chg: Optional[float]) -> str:
    """Price/OI quadrant label (deterministic heuristic).

    Inputs are % changes over the same horizon (prefer 4h).
    """

    if not isinstance(px_chg, (int, float)) or not isinstance(oi_chg, (int, float)):
        return "资金方向不明"

    if oi_chg >= 5 and px_chg >= 1:
        return "多头加仓（价↑OI↑）"
    if oi_chg >= 5 and px_chg <= -1:
        return "空头加仓（价↓OI↑）"
    if oi_chg <= -5 and px_chg >= 1:
        return "空头回补（价↑OI↓）"
    if oi_chg <= -5 and px_chg <= -1:
        return "多头止损/出清（价↓OI↓）"

    return "轻微/震荡（价/OI变化不大）"


def _key_levels(k1: Dict[str, Any], k4: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Return key support/resistance levels.

    Prefer 1h swing -> 1h range -> 4h swing -> 4h range.
    """

    def _pick(d: Dict[str, Any], path: Tuple[str, str]) -> Optional[float]:
        return _as_num(_safe_get(d, path[0], path[1]))

    r1 = _pick(k1, ("swing", "hi")) or _pick(k1, ("range", "hi")) or _pick(k4, ("swing", "hi")) or _pick(k4, ("range", "hi"))
    s1 = _pick(k1, ("swing", "lo")) or _pick(k1, ("range", "lo")) or _pick(k4, ("swing", "lo")) or _pick(k4, ("range", "lo"))
    return {"resistance": r1, "support": s1}


def _atr_pct(k: Dict[str, Any]) -> Optional[float]:
    atr14 = _as_num(k.get("atr14"))
    last = _as_num(k.get("last"))
    if atr14 is None or last is None or last == 0:
        return None
    return round((atr14 / last) * 100.0, 2)


def _bias_hint(*, slope4: Optional[float], rsi1: Optional[float]) -> str:
    # slope4: EMA20 slope pct
    if slope4 is None or rsi1 is None:
        return "观望"

    if slope4 >= 0.06 and rsi1 >= 55:
        return "偏多"
    if slope4 <= -0.06 and rsi1 <= 45:
        return "偏空"
    return "观望"


def _action_notes(
    *,
    flow: str,
    bias: str,
    sup: Optional[float],
    res: Optional[float],
    atr1_pct: Optional[float],
    rsi1: Optional[float],
    pos1: Optional[float],
    oi4: Optional[float],
) -> List[str]:
    notes: List[str] = []

    # 1) Level-based trigger (always the most actionable)
    if bias == "偏多" and res is not None:
        notes.append(f"上破并站稳{_fmt_num(res)}才追")
    elif bias == "偏空" and sup is not None:
        notes.append(f"跌破{_fmt_num(sup)}延续偏空")
    elif sup is not None and res is not None:
        notes.append(f"区间：上{_fmt_num(res)}/下{_fmt_num(sup)}")

    # 2) Overextension / squeeze risk
    if rsi1 is not None and pos1 is not None:
        if rsi1 >= 70 or pos1 >= 0.88:
            notes.append("高位易回撤：等回踩确认")
        elif rsi1 <= 30 or pos1 <= 0.12:
            notes.append("低位易反抽：别追空")

    # 3) Volatility-based sizing
    if atr1_pct is not None:
        if atr1_pct >= 4.0:
            notes.append("ATR高：减仓/放宽止损")
        elif atr1_pct <= 1.2:
            notes.append("波动低：耐心等突破")

    # 4) OI expansion warning
    if oi4 is not None and abs(oi4) >= 15:
        if "空头加仓" in flow:
            notes.append("OI扩张：防逼空")
        elif "多头加仓" in flow:
            notes.append("OI扩张：防踩踏")

    # Keep 1-2 only (WhatsApp constraints)
    out: List[str] = []
    for n in notes:
        if n and n not in out:
            out.append(n)
        if len(out) >= 2:
            break
    return out


def build_perp_dash_inputs(*, oi_items: List[Dict[str, Any]], max_n: int = 3) -> List[Dict[str, Any]]:
    """Create compact deterministic inputs for LLM/renderer.

    Uses oi_items (already enriched with kline_1h/4h).
    """

    out: List[Dict[str, Any]] = []

    for it in (oi_items or [])[: max(0, int(max_n) or 0)]:
        if not isinstance(it, dict):
            continue
        sym = str(it.get("symbol") or "").upper().strip()
        if not sym:
            continue

        k1 = it.get("kline_1h") if isinstance(it.get("kline_1h"), dict) else {}
        k4 = it.get("kline_4h") if isinstance(it.get("kline_4h"), dict) else {}

        px_now = _as_num(it.get("price_now"))
        px1 = _as_num(it.get("price_1h"))
        px4 = _as_num(it.get("price_4h"))
        px24 = _as_num(it.get("price_24h"))
        oi1 = _as_num(it.get("oi_1h"))
        oi4 = _as_num(it.get("oi_4h"))
        oi24 = _as_num(it.get("oi_24h"))

        mc, fdv = _pick_market_cap_fdv(it)

        # Prefer 4h quadrant; fallback to 1h.
        flow = flow_label(px_chg=px4 if px4 is not None else px1, oi_chg=oi4 if oi4 is not None else oi1)

        levels = _key_levels(k1, k4)
        sup = levels.get("support")
        res = levels.get("resistance")

        slope4 = _as_num(k4.get("ema20_slope_pct"))
        rsi1 = _as_num(k1.get("rsi14"))
        pos1 = _as_num(_safe_get(k1, "range", "pos"))
        atr1_pct = _atr_pct(k1)
        atr4_pct = _atr_pct(k4)

        bias = _bias_hint(slope4=slope4, rsi1=rsi1)

        notes = _action_notes(
            flow=flow,
            bias=bias,
            sup=sup,
            res=res,
            atr1_pct=atr1_pct,
            rsi1=rsi1,
            pos1=pos1,
            oi4=oi4,
        )

        out.append(
            {
                "symbol": sym,
                "price_now": px_now,
                "market_cap": mc,
                "fdv": fdv,
                "price_chg": {"1h_pct": px1, "4h_pct": px4, "24h_pct": px24},
                "oi_chg": {"1h_pct": oi1, "4h_pct": oi4, "24h_pct": oi24},
                "structure": {
                    "1h": {
                        "swing_hi": _as_num(_safe_get(k1, "swing", "hi")),
                        "swing_lo": _as_num(_safe_get(k1, "swing", "lo")),
                        "ema20_slope_pct": _as_num(k1.get("ema20_slope_pct")),
                        "rsi14": rsi1,
                        "atr_pct": atr1_pct,
                        "range_loc": _safe_get(k1, "range", "loc"),
                        "range_pos": pos1,
                        "vol_ratio": _as_num(_safe_get(k1, "volume", "ratio")),
                    },
                    "4h": {
                        "swing_hi": _as_num(_safe_get(k4, "swing", "hi")),
                        "swing_lo": _as_num(_safe_get(k4, "swing", "lo")),
                        "ema20_slope_pct": slope4,
                        "rsi14": _as_num(k4.get("rsi14")),
                        "atr_pct": atr4_pct,
                        "range_loc": _safe_get(k4, "range", "loc"),
                        "range_pos": _as_num(_safe_get(k4, "range", "pos")),
                    },
                },
                "key_levels": {"resistance": res, "support": sup},
                "flow_label": flow,
                "bias_hint": bias,
                "action_notes": notes,
            }
        )

    return out


def render_perp_dashboards_mini(perp_dash_inputs: List[Dict[str, Any]], *, top_n: int = 3) -> List[str]:
    """Deterministic renderer: concise trader view (price/OI + 1H/4H trend + action)."""

    def _trend_label(slope: Optional[float]) -> str:
        if slope is None:
            return "震荡"
        if slope >= 0.06:
            return "上行"
        if slope <= -0.06:
            return "下行"
        return "震荡"

    def _extreme_tag(rsi: Optional[float]) -> str:
        if rsi is None:
            return ""
        if rsi >= 75:
            return "极端过热"
        if rsi >= 70:
            return "过热"
        if rsi <= 25:
            return "极端超卖"
        if rsi <= 30:
            return "超卖"
        return ""

    out: List[str] = []

    for i, d in enumerate((perp_dash_inputs or [])[: max(0, int(top_n) or 0)], 1):
        if not isinstance(d, dict):
            continue

        sym = str(d.get("symbol") or "").upper().strip()
        if not sym:
            continue

        px = d.get("price_chg") if isinstance(d.get("price_chg"), dict) else {}
        oi = d.get("oi_chg") if isinstance(d.get("oi_chg"), dict) else {}
        st = d.get("structure") if isinstance(d.get("structure"), dict) else {}
        s1 = st.get("1h") if isinstance(st.get("1h"), dict) else {}
        s4 = st.get("4h") if isinstance(st.get("4h"), dict) else {}

        flow = str(d.get("flow_label") or "资金方向不明").strip()
        bias = str(d.get("bias_hint") or "观望").strip() or "观望"

        # Line 1: price/OI relationship (trader view)
        price_now = _as_num(d.get("price_now"))
        mc = _as_num(d.get("market_cap"))
        line1 = f"{i}) {sym}（{bias}）"
        if price_now is not None:
            line1 += f"现价{_fmt_num(price_now)} "
        if mc is not None:
            line1 += f"MC{_fmt_usd(mc)} "
        line1 += f"价4h{_fmt_pct(px.get('4h_pct'))} OI4h{_fmt_pct(oi.get('4h_pct'))} → {flow}"
        out.append(line1)

        # Line 2: 1H/4H trend + extreme emotion
        slope1 = _as_num(s1.get("ema20_slope_pct"))
        slope4 = _as_num(s4.get("ema20_slope_pct"))
        rsi1 = _as_num(s1.get("rsi14"))
        rsi4 = _as_num(s4.get("rsi14"))
        tag1 = _extreme_tag(rsi1)
        tag4 = _extreme_tag(rsi4)
        t1 = _trend_label(slope1)
        t4 = _trend_label(slope4)
        trend_line = f"   - 趋势：1H{t1}{('(' + tag1 + ')') if tag1 else ''} / 4H{t4}{('(' + tag4 + ')') if tag4 else ''}"
        out.append(trend_line)

        # Line 3: actions (already includes key levels / risk notes)
        notes = d.get("action_notes") if isinstance(d.get("action_notes"), list) else []
        notes2 = [str(x).strip() for x in notes if isinstance(x, str) and x.strip()][:2]
        if notes2:
            out.append("   - 动作：" + "；".join(notes2))

    return out

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

from scripts.market_data import get_shared_dex_batcher, get_shared_exchange_batcher
from ..core.formatting import fmt_num, fmt_pct, fmt_usd
from ..core.indicators import flow_label
from ..kline_fetcher import run_kline_json
from ..llm_openai import chat_json, load_chat_api_key, summarize_oi_trading_plans
from ..output.whatsapp import WHATSAPP_CHUNK_MAX, split_whatsapp_text
from .twitter_evidence import TwitterQuerySpec, twitter_evidence


DEFAULT_QUOTE = "USDT"
_KNOWN_QUOTES = ("USDT", "USDC", "USD", "BUSD", "BTC", "ETH")


def _dedup_keep_order(xs: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in xs or []:
        t = (x or "").strip()
        if not t:
            continue
        k = t.upper()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out


def normalize_symbol_input(raw: str, *, default_quote: str = DEFAULT_QUOTE) -> Dict[str, str]:
    """Normalize user input into a perp symbol + social cashtag."""

    s = (raw or "").strip()
    if not s:
        raise ValueError("empty symbol")

    # Common copy/paste formats: BINANCE:PUMPUSDT, $pump, pump/usdt
    s = s.strip()
    if ":" in s:
        s = s.split(":")[-1].strip()

    s = re.sub(r"\s+", "", s)
    s = s.upper()

    if s.startswith("$"):
        s = s[1:]

    # Allow BASE/QUOTE explicit form.
    base = ""
    quote = (default_quote or DEFAULT_QUOTE).upper().strip() or DEFAULT_QUOTE
    if "/" in s:
        left, right = s.split("/", 1)
        base = left.strip().lstrip("$")
        q = right.strip().lstrip("$")
        if q:
            quote = q
    else:
        # "XXXPERP" -> "XXX"
        if s.endswith("PERP") and len(s) > 4:
            s = s[: -len("PERP")]

        # If user already provided quote (e.g., XXXUSDT), keep it.
        for q in _KNOWN_QUOTES:
            if s.endswith(q) and len(s) > len(q):
                base = s[: -len(q)]
                quote = q
                break
        else:
            base = s

    base = re.sub(r"[^A-Z0-9]", "", base)
    quote = re.sub(r"[^A-Z0-9]", "", quote)

    if not base:
        raise ValueError(f"invalid base from input: {raw!r}")
    if not quote:
        quote = DEFAULT_QUOTE

    perp_symbol = f"{base}{quote}"
    cashtag = f"${base}"

    return {
        "input": (raw or "").strip(),
        "base": base,
        "quote": quote,
        "perp_symbol": perp_symbol,
        "cashtag": cashtag,
    }


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


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


def _key_levels(k1: Dict[str, Any], k4: Dict[str, Any]) -> Dict[str, Optional[float]]:
    def _pick(d: Dict[str, Any], path: Tuple[str, str]) -> Optional[float]:
        v = _safe_get(d, path[0], path[1])
        return _as_num(v)

    r1 = _pick(k1, ("swing", "hi")) or _pick(k1, ("range", "hi")) or _pick(k4, ("swing", "hi")) or _pick(k4, ("range", "hi"))
    s1 = _pick(k1, ("swing", "lo")) or _pick(k1, ("range", "lo")) or _pick(k4, ("swing", "lo")) or _pick(k4, ("range", "lo"))
    return {"resistance": r1, "support": s1}


def _twitter_stats(snippets: List[str]) -> Dict[str, Any]:
    bull_terms = [
        "long",
        "buy",
        "bull",
        "breakout",
        "break out",
        "support",
        "bounce",
        "higher",
        "看多",
        "做多",
        "多单",
        "突破",
        "支撑",
        "反弹",
    ]
    bear_terms = [
        "short",
        "sell",
        "bear",
        "rejection",
        "resistance",
        "dump",
        "down",
        "rug",
        "scam",
        "hack",
        "看空",
        "做空",
        "空单",
        "压制",
        "跌破",
        "砸盘",
        "跑路",
        "诈骗",
        "被黑",
    ]
    trader_terms = ["tp", "sl", "stop", "entry", "exit", "support", "resistance", "long", "short", "突破", "止损", "入场", "止盈"]

    bull_hits = 0
    bear_hits = 0
    trader_talk_hits = 0
    lens: List[int] = []

    for s in snippets or []:
        t = (s or "").strip()
        if not t:
            continue
        low = t.lower()
        lens.append(len(t))
        if any(k in low for k in bull_terms):
            bull_hits += 1
        if any(k in low for k in bear_terms):
            bear_hits += 1
        if any(k in low for k in trader_terms):
            trader_talk_hits += 1

    avg_len = round(sum(lens) / len(lens), 1) if lens else 0.0

    stance_score = 0.0
    if bull_hits or bear_hits:
        stance_score = (bull_hits - bear_hits) / max(1.0, float(bull_hits + bear_hits))
        stance_score = float(_clamp(stance_score, -1.0, 1.0))

    return {
        "snippets": len(snippets or []),
        "avg_len": avg_len,
        "bull_hits": bull_hits,
        "bear_hits": bear_hits,
        "trader_talk_hits": trader_talk_hits,
        "stance_score": round(stance_score, 3),
    }


def _scores(*, k1: Dict[str, Any], k4: Dict[str, Any], px: Dict[str, Any], oi: Dict[str, Any], tw: Dict[str, Any]) -> Dict[str, int]:
    slope4 = _as_num(k4.get("ema20_slope_pct"))
    rsi1 = _as_num(k1.get("rsi14"))
    pos1 = _as_num(_safe_get(k1, "range", "pos"))

    px4 = _as_num(px.get("price_4h"))
    oi4 = _as_num(oi.get("oi_4h"))

    tr = 0.0
    if slope4 is not None:
        tr += _clamp(slope4 / 0.2, -2.0, 2.0)
    if rsi1 is not None:
        tr += _clamp((rsi1 - 50.0) / 10.0, -2.0, 2.0)
    if pos1 is not None:
        tr += _clamp((pos1 - 0.5) * 1.2, -0.6, 0.6)
    trend = int(round(_clamp(50.0 + 12.0 * tr, 0.0, 100.0)))

    fr = 0.0
    if px4 is not None and oi4 is not None:
        if px4 >= 1 and oi4 >= 5:
            fr += 2.0
        elif px4 <= -1 and oi4 >= 5:
            fr -= 2.0
        elif px4 >= 1 and oi4 <= -5:
            fr += 0.8
        elif px4 <= -1 and oi4 <= -5:
            fr -= 0.8
        fr += _clamp(oi4 / 8.0, -1.5, 1.5)
    else:
        oi1 = _as_num(oi.get("oi_1h"))
        px1 = _as_num(px.get("price_1h"))
        if px1 is not None and oi1 is not None:
            fr += _clamp(oi1 / 6.0, -1.5, 1.5)
    oi_score = int(round(_clamp(50.0 + 14.0 * fr, 0.0, 100.0)))

    kept = int(tw.get("kept") or 0)
    total = int(tw.get("total") or 0)
    ratio = float(tw.get("kept_ratio") or (kept / total if total else 0.0))
    st = tw.get("stats") if isinstance(tw.get("stats"), dict) else {}
    stance = _as_num(st.get("stance_score")) or 0.0
    intensity = _clamp(kept / 6.0, 0.0, 1.0)

    sr = 0.0
    sr += 1.2 * ratio
    sr += 0.8 * intensity
    sr += 0.3 * abs(stance)
    social = int(round(_clamp(25.0 + 55.0 * sr, 0.0, 100.0)))

    overall = int(round(_clamp(0.45 * trend + 0.35 * oi_score + 0.20 * social, 0.0, 100.0)))

    return {"trend": trend, "oi": oi_score, "social": social, "overall": overall}


def run_prepare(symbol: str) -> Dict[str, Any]:
    raw = (symbol or "").strip()
    errors: List[str] = []

    try:
        norm = normalize_symbol_input(raw)
    except Exception as e:
        sym = raw.upper().strip()
        return {
            "symbol": sym,
            "use_llm": False,
            "errors": [f"normalize:{type(e).__name__}:{e}"],
            "prepared": {"symbol": sym, "normalization": {"input": raw}},
        }

    sym = norm["perp_symbol"]
    base = norm["base"]
    cashtag = norm["cashtag"]

    px: Dict[str, Any] = {}
    oi: Dict[str, Any] = {}
    k1: Dict[str, Any] = {}
    k4: Dict[str, Any] = {}
    mcfdv: Dict[str, Any] = {}
    tw: Dict[str, Any] = {}

    try:
        px = get_shared_exchange_batcher().price_changes(sym)
    except Exception as e:
        errors.append(f"price_changes:{type(e).__name__}:{e}")

    try:
        oi = get_shared_exchange_batcher().oi_changes(sym)
    except Exception as e:
        errors.append(f"oi_changes:{type(e).__name__}:{e}")

    try:
        k1 = run_kline_json(sym, interval="1h", lookback=120)
    except Exception as e:
        errors.append(f"kline_1h:{type(e).__name__}:{e}")

    try:
        k4 = run_kline_json(sym, interval="4h", lookback=80)
    except Exception as e:
        errors.append(f"kline_4h:{type(e).__name__}:{e}")

    try:
        mcfdv = get_shared_dex_batcher().market_cap_fdv(base)
    except Exception as e:
        errors.append(f"coingecko:{type(e).__name__}:{e}")

    try:
        aliases = _dedup_keep_order([sym, cashtag, base])
        spec = TwitterQuerySpec(topic=sym, aliases=aliases, intent="plan", window_hours=24, snippet_limit=12)
        out = twitter_evidence(spec)
        tw = {"total": out.get("total", 0), "kept": out.get("kept", 0), "snippets": out.get("snippets", [])}
    except Exception as e:
        errors.append(f"twitter:{type(e).__name__}:{e}")
        tw = {"total": 0, "kept": 0, "snippets": []}

    snippets = (tw.get("snippets") or []) if isinstance(tw.get("snippets"), list) else []
    snippets = [str(x) for x in snippets if isinstance(x, str) and x.strip()][:8]

    tw_out = {
        "total": int(tw.get("total") or 0),
        "kept": int(tw.get("kept") or 0),
        "kept_ratio": round((int(tw.get("kept") or 0) / int(tw.get("total") or 1)), 3) if int(tw.get("total") or 0) else 0.0,
        "snippets": snippets,
        "stats": _twitter_stats(snippets),
    }

    flow = flow_label(px_chg=_as_num(px.get("px_4h")) or _as_num(px.get("px_1h")), oi_chg=_as_num(oi.get("oi_4h")) or _as_num(oi.get("oi_1h")))

    levels = _key_levels(k1 if isinstance(k1, dict) else {}, k4 if isinstance(k4, dict) else {})

    scores = _scores(
        k1=k1 if isinstance(k1, dict) else {},
        k4=k4 if isinstance(k4, dict) else {},
        px={
            "price_1h": px.get("px_1h"),
            "price_4h": px.get("px_4h"),
        },
        oi={"oi_1h": oi.get("oi_1h"), "oi_4h": oi.get("oi_4h")},
        tw=tw_out,
    )

    bias_hint = "观望"
    if scores["trend"] >= 62 and scores["oi"] >= 58:
        bias_hint = "偏多"
    elif scores["trend"] <= 38 and scores["oi"] <= 42:
        bias_hint = "偏空"

    atr14 = _as_num(k1.get("atr14"))
    last = _as_num(k1.get("last"))
    atr_pct = round((atr14 / last) * 100.0, 2) if (atr14 and last) else None

    derived = {
        "flow_label": flow,
        "bias_hint": bias_hint,
        "scores": scores,
        "key_levels": levels,
        "labels": {
            "range_loc_1h": _safe_get(k1, "range", "loc"),
            "range_pos_1h": _safe_get(k1, "range", "pos"),
            "ema20_slope_4h_pct": k4.get("ema20_slope_pct") if isinstance(k4, dict) else None,
            "rsi14_1h": k1.get("rsi14") if isinstance(k1, dict) else None,
            "atr14_pct_1h": atr_pct,
        },
    }

    prepared = {
        "symbol": sym,
        "normalization": norm,
        "price": {
            "now": px.get("px_now"),
            "chg_1h_pct": px.get("px_1h"),
            "chg_4h_pct": px.get("px_4h"),
            "chg_24h_pct": px.get("px_24h"),
            "vol_1h": px.get("vol_1h"),
        },
        "oi": {
            "now": oi.get("oi_now"),
            "chg_1h_pct": oi.get("oi_1h"),
            "chg_4h_pct": oi.get("oi_4h"),
            "chg_24h_pct": oi.get("oi_24h"),
            "oi_value_now": oi.get("oi_value_now"),
            "oi_value_chg_24h_pct": oi.get("oi_value_24h"),
        },
        "market": {
            "market_cap": mcfdv.get("market_cap"),
            "fdv": mcfdv.get("fdv"),
        },
        "kline_1h": k1,
        "kline_4h": k4,
        "twitter": tw_out,
        "derived": derived,
    }

    return {
        "symbol": sym,
        "use_llm": False,
        "errors": errors,
        "prepared": prepared,
    }


def _extract_kline_brief(k: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(k, dict):
        return {}
    return {
        "interval": k.get("interval"),
        "last": k.get("last"),
        "chg_pct": k.get("chg_pct"),
        "range": k.get("range"),
        "swing": k.get("swing"),
        "ema20": k.get("ema20"),
        "ema20_slope_pct": k.get("ema20_slope_pct"),
        "rsi14": k.get("rsi14"),
        "atr14": k.get("atr14"),
        "volume": k.get("volume"),
    }


def _llm_dashboard(prepared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not load_chat_api_key():
        return None

    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}

    payload = {
        "symbol": p.get("symbol"),
        "price": p.get("price"),
        "oi": p.get("oi"),
        "market": p.get("market"),
        "kline_1h": _extract_kline_brief(p.get("kline_1h") or {}),
        "kline_4h": _extract_kline_brief(p.get("kline_4h") or {}),
        "twitter": p.get("twitter"),
        "derived": p.get("derived"),
        "requirements": {
            "language": "zh",
            "no_quotes": True,
            "max_bullets": 6,
            "max_risks": 3,
            "max_actions": 2,
            "bullet_len": 26,
        },
    }

    system = (
        "你是加密交易员助手。输入是一份单币结构化数据（价格/OI/K线结构/Twitter证据统计/启发式分数）。\n"
        "请生成：『方案2 决策仪表盘』的可发WhatsApp内容要点（不要输出链接，不要引用原话，不要编造新闻）。\n"
        "输出必须是JSON，字段：{verdict, oi_narrative, twitter_view, twitter_signals, bullets, actions, risks}。\n"
        "约束：\n"
        "- verdict 只能是: 偏多/偏空/观望/高波动\n"
        "- oi_narrative：1~2句，基于价格/OI变化与区间位置解读资金意图（不确定可写“可能/需确认”）\n"
        "- twitter_view：四段式对象，字段为 {consensus, divergence, catalyst, risk}，每项1句，概括共识/分歧/催化/风险（不引用原话）\n"
        "- twitter_signals：3~5条短语，来自社交证据的“信号词”\n"
        "- bullets: 4~6条，每条<=26字，直接可执行/可验证\n"
        "- actions: 1~2条，每条<=20字\n"
        "- risks: 2~3条，每条<=20字\n"
        "- 如果社交证据弱（kept少/ratio低），必须明确写在twitter_view的risk里\n"
    )

    try:
        return chat_json(system=system, user=json.dumps(payload, ensure_ascii=False), temperature=0.2, max_tokens=620, timeout=35)
    except Exception:
        return None


def _llm_plan(prepared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not load_chat_api_key():
        return None

    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    oi = p.get("oi") if isinstance(p.get("oi"), dict) else {}
    derived = p.get("derived") if isinstance(p.get("derived"), dict) else {}
    tw = p.get("twitter") if isinstance(p.get("twitter"), dict) else {}

    k1 = p.get("kline_1h") if isinstance(p.get("kline_1h"), dict) else {}

    item = {
        "symbol": p.get("symbol"),
        "price_now": price.get("now"),
        "price_1h": price.get("chg_1h_pct"),
        "price_4h": price.get("chg_4h_pct"),
        "price_24h": price.get("chg_24h_pct"),
        "vol_1h": price.get("vol_1h"),
        "vol_ratio": ((k1.get("volume") or {}).get("ratio") if isinstance(k1.get("volume"), dict) else None),
        "oi_now": oi.get("now"),
        "oi_1h": oi.get("chg_1h_pct"),
        "oi_4h": oi.get("chg_4h_pct"),
        "oi_24h": oi.get("chg_24h_pct"),
        "flow": derived.get("flow_label"),
        "kline_1h": p.get("kline_1h"),
        "kline_4h": p.get("kline_4h"),
        "twitter": tw,
    }

    try:
        out = summarize_oi_trading_plans(items=[item])
        items = out.get("items") if isinstance(out, dict) else None
        if isinstance(items, list) and items and isinstance(items[0], dict):
            return items[0]
        return None
    except Exception:
        return None


def _rule_dashboard(prepared: Dict[str, Any]) -> Dict[str, Any]:
    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}

    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    oi = p.get("oi") if isinstance(p.get("oi"), dict) else {}
    tw = p.get("twitter") if isinstance(p.get("twitter"), dict) else {}
    derived = p.get("derived") if isinstance(p.get("derived"), dict) else {}

    scores = derived.get("scores") if isinstance(derived.get("scores"), dict) else {}
    kept = int(tw.get("kept") or 0)
    total = int(tw.get("total") or 0)
    flow = (derived.get("flow_label") or "").strip() or "资金方向不明"

    verdict = "观望"
    overall = int(scores.get("overall") or 0)
    if overall >= 70:
        verdict = "偏多"
    elif overall <= 30:
        verdict = "偏空"

    px1 = price.get("chg_1h_pct")
    oi1 = oi.get("chg_1h_pct")

    def _oi_narrative() -> str:
        if isinstance(px1, (int, float)) and isinstance(oi1, (int, float)):
            if px1 > 0 and oi1 > 0:
                return "1H 价↑OI↑：增仓跟涨，但需量能确认"
            if px1 < 0 and oi1 > 0:
                return "1H 价↓OI↑：空头加仓或对冲增多"
            if px1 > 0 and oi1 < 0:
                return "1H 价↑OI↓：空头回补/减仓推动"
            if px1 < 0 and oi1 < 0:
                return "1H 价↓OI↓：出清型回撤，谨慎追单"
        return flow or "OI/价格关系不明，等待确认"

    def _twitter_view() -> Dict[str, str]:
        if not total:
            return {
                "consensus": "证据缺失/抓取失败",
                "divergence": "无足够样本判断分歧",
                "catalyst": "暂无明确催化",
                "risk": "样本为空，结论可靠性低",
            }
        if kept <= 1:
            return {
                "consensus": "有效观点偏少，难形成共识",
                "divergence": "缺少可比样本",
                "catalyst": "未见明确事件驱动",
                "risk": "社交证据弱，结论不稳",
            }
        return {
            "consensus": "有一定观点密度，但未形成强一致",
            "divergence": "多空观点并存，方向需再确认",
            "catalyst": "催化多为预期/情绪，需验证",
            "risk": "叙事与价格背离风险",
        }

    bullets: List[str] = []
    bullets.append(f"价格24h {fmt_pct(price.get('chg_24h_pct'))} | 4h {fmt_pct(price.get('chg_4h_pct'))}")
    bullets.append(f"OI 24h {fmt_pct(oi.get('chg_24h_pct'))} | 4h {fmt_pct(oi.get('chg_4h_pct'))}")
    bullets.append(_oi_narrative())

    lv = derived.get("key_levels") if isinstance(derived.get("key_levels"), dict) else {}
    sup = lv.get("support")
    res = lv.get("resistance")
    if sup is not None or res is not None:
        bullets.append(f"关键位：上{fmt_num(res)} / 下{fmt_num(sup)}")

    if total:
        bullets.append(f"社交证据：有效{kept}/{total}")
    else:
        bullets.append("社交证据：暂无/抓取失败")

    actions = ["等关键位确认再出手"]
    if verdict == "偏多" and sup is not None:
        actions = [f"回踩{fmt_num(sup)}不破再偏多"]
    elif verdict == "偏空" and res is not None:
        actions = [f"反抽{fmt_num(res)}受压再偏空"]

    risks: List[str] = ["勿追单；优先等收线"]
    if total and kept <= 1:
        risks.append("社交讨论偏少")

    return {
        "verdict": verdict,
        "oi_narrative": _oi_narrative(),
        "twitter_view": _twitter_view(),
        "twitter_signals": [],
        "bullets": bullets[:6],
        "actions": actions[:2],
        "risks": risks[:3],
    }


def _rule_plan(prepared: Dict[str, Any]) -> Dict[str, Any]:
    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
    sym = (p.get("symbol") or "").upper().strip()

    derived = p.get("derived") if isinstance(p.get("derived"), dict) else {}

    bias = derived.get("bias_hint") or "观望"
    flow = derived.get("flow_label") or "资金方向不明"

    lv = derived.get("key_levels") if isinstance(derived.get("key_levels"), dict) else {}
    sup = lv.get("support")
    res = lv.get("resistance")

    setup_bits: List[str] = []
    lbl = derived.get("labels") if isinstance(derived.get("labels"), dict) else {}
    loc = lbl.get("range_loc_1h")
    if isinstance(loc, str) and loc:
        setup_bits.append(f"1h {loc}")
    slope4 = lbl.get("ema20_slope_4h_pct")
    if isinstance(slope4, (int, float)):
        setup_bits.append(f"4h EMA20斜率{slope4:+.2f}%")
    setup_bits.append(flow)

    triggers: List[str] = []
    if res is not None:
        triggers.append(f"突破站稳{fmt_num(res)}")
    if sup is not None:
        triggers.append(f"跌破收在{fmt_num(sup)}下")

    targets: List[str] = []
    if res is not None:
        targets.append(f"目标看{fmt_num(res)}上方扩展")
    if sup is not None:
        targets.append(f"目标看{fmt_num(sup)}下方延伸")

    invalid = "确认失败则撤"
    if bias == "偏多" and sup is not None:
        invalid = f"有效跌破{fmt_num(sup)}"[:28]
    if bias == "偏空" and res is not None:
        invalid = f"有效站回{fmt_num(res)}"[:28]

    return {
        "symbol": sym,
        "bias": bias,
        "setup": "；".join(setup_bits[:3])[:60],
        "triggers": triggers[:2],
        "targets": targets[:2],
        "invalidation": invalid,
        "risk_notes": ["无LLM：以结构+OI为主"],
    }


def _render_dashboard_text(prepared: Dict[str, Any], dash: Dict[str, Any]) -> str:
    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
    sym = (p.get("symbol") or "").upper().strip()

    price = p.get("price") if isinstance(p.get("price"), dict) else {}
    oi = p.get("oi") if isinstance(p.get("oi"), dict) else {}
    market = p.get("market") if isinstance(p.get("market"), dict) else {}
    derived = p.get("derived") if isinstance(p.get("derived"), dict) else {}

    scores = derived.get("scores") if isinstance(derived.get("scores"), dict) else {}
    flow = (derived.get("flow_label") or "").strip()

    k1 = p.get("kline_1h") if isinstance(p.get("kline_1h"), dict) else {}
    k4 = p.get("kline_4h") if isinstance(p.get("kline_4h"), dict) else {}

    lines: List[str] = []
    lines.append(f"*{sym} 方案2 决策仪表盘*")
    lines.append(f"- 现价：{fmt_num(price.get('now'))} | 24h {fmt_pct(price.get('chg_24h_pct'))}")
    lines.append(f"- 涨跌：1h {fmt_pct(price.get('chg_1h_pct'))} | 4h {fmt_pct(price.get('chg_4h_pct'))}")
    lines.append(
        f"- OI：1h {fmt_pct(oi.get('chg_1h_pct'))} | 4h {fmt_pct(oi.get('chg_4h_pct'))} | 24h {fmt_pct(oi.get('chg_24h_pct'))}"
    )
    lines.append(f"- OI名义：{fmt_usd(oi.get('oi_value_now'))}")

    mc = market.get("market_cap")
    fdv = market.get("fdv")
    if mc is not None or fdv is not None:
        bits = []
        if mc is not None:
            bits.append(f"MC{fmt_usd(mc)}")
        if fdv is not None:
            bits.append(f"FDV{fmt_usd(fdv)}")
        if bits:
            lines.append(f"- {'/'.join(bits)}")

    trend_s = int(scores.get("trend") or 0)
    oi_s = int(scores.get("oi") or 0)
    soc_s = int(scores.get("social") or 0)
    all_s = int(scores.get("overall") or 0)

    lines.append(f"- 评分：趋势{trend_s}/100 | OI{oi_s}/100 | 社交{soc_s}/100 | 综合{all_s}/100")

    verdict = (dash.get("verdict") or derived.get("bias_hint") or "观望").strip()
    lines.append(f"- 结论：{verdict}")

    lv = derived.get("key_levels") if isinstance(derived.get("key_levels"), dict) else {}
    if lv.get("support") is not None or lv.get("resistance") is not None:
        lines.append(f"- 关键位：上{fmt_num(lv.get('resistance'))} / 下{fmt_num(lv.get('support'))}")

    k1_sw = k1.get("swing") if isinstance(k1.get("swing"), dict) else {}
    k4_sw = k4.get("swing") if isinstance(k4.get("swing"), dict) else {}
    k1_rg = k1.get("range") if isinstance(k1.get("range"), dict) else {}
    rsi1 = k1.get("rsi14")
    rsi4 = k4.get("rsi14")
    atr1 = k1.get("atr14")
    atr4 = k4.get("atr14")
    ema4 = k4.get("ema20")
    slope4 = k4.get("ema20_slope_pct")
    vol1 = k1.get("volume") if isinstance(k1.get("volume"), dict) else {}

    struct_lines: List[str] = []
    if k1_sw.get("hi") is not None or k1_sw.get("lo") is not None:
        struct_lines.append(f"1H swing：上{fmt_num(k1_sw.get('hi'))} / 下{fmt_num(k1_sw.get('lo'))}")
    if k4_sw.get("hi") is not None or k4_sw.get("lo") is not None:
        struct_lines.append(f"4H swing：上{fmt_num(k4_sw.get('hi'))} / 下{fmt_num(k4_sw.get('lo'))}")
    if k1_rg.get("hi") is not None or k1_rg.get("lo") is not None:
        pos = k1_rg.get("pos")
        pos_s = "?" if pos is None else f"{float(pos):.2f}"
        struct_lines.append(f"1H 区间：{fmt_num(k1_rg.get('lo'))}~{fmt_num(k1_rg.get('hi'))} | pos {pos_s}")

    ind_bits: List[str] = []
    if ema4 is not None or slope4 is not None:
        if isinstance(slope4, (int, float)):
            ind_bits.append(f"4H EMA20 {fmt_num(ema4)} | 斜率{slope4:+.2f}%")
        else:
            ind_bits.append(f"4H EMA20 {fmt_num(ema4)}")
    if rsi1 is not None or rsi4 is not None:
        ind_bits.append(f"RSI：1H {fmt_num(rsi1)} | 4H {fmt_num(rsi4)}")
    if atr1 is not None or atr4 is not None:
        ind_bits.append(f"ATR：1H {fmt_num(atr1)} | 4H {fmt_num(atr4)}")
    if vol1.get("ratio") is not None:
        ind_bits.append(f"量能比(1H)：{fmt_num(vol1.get('ratio'))}")

    if struct_lines or ind_bits:
        lines.append("*关键结构数据*")
        for s in (struct_lines + ind_bits)[:6]:
            lines.append(f"- {s}")

    tw = p.get("twitter") if isinstance(p.get("twitter"), dict) else {}
    kept = int(tw.get("kept") or 0)
    total = int(tw.get("total") or 0)
    ratio = tw.get("kept_ratio")
    st = tw.get("stats") if isinstance(tw.get("stats"), dict) else {}
    if total or kept or st:
        lines.append("*社交明细（无引用）*")
        if total:
            r = ratio
            if not isinstance(r, (int, float)):
                r = (kept / total) if total else 0.0
            lines.append(f"- 有效/总量：{kept}/{total} | 比例 {float(r):.2f}")
        else:
            lines.append(f"- 有效/总量：{kept}/?")
        if st:
            lines.append(
                "- 词命中：多头{bull} 空头{bear} 交易员话术{talk}".format(
                    bull=int(st.get("bull_hits") or 0),
                    bear=int(st.get("bear_hits") or 0),
                    talk=int(st.get("trader_talk_hits") or 0),
                )
            )
            lines.append(f"- 倾向分：{fmt_num(st.get('stance_score'))}（-1空/+1多）")

    exp: List[str] = []
    if trend_s >= 70:
        exp.append("趋势分高：4H趋势上行/位置偏上")
    elif trend_s <= 30:
        exp.append("趋势分低：4H趋势下行/位置偏下")
    else:
        exp.append("趋势分中：方向不够一致")

    if oi_s >= 65:
        exp.append("OI分高：增仓与价格同向")
    elif oi_s <= 35:
        exp.append("OI分低：增仓与价格逆向/出清")
    else:
        exp.append("OI分中：多空博弈/震荡")

    if total and kept <= 1:
        exp.append("社交分低：有效观点偏少")
    elif total and kept >= 4:
        exp.append("社交分偏高：有一定观点密度")
    else:
        exp.append("社交分中：证据一般")

    if flow:
        exp.append(f"资金结构：{flow}")

    if exp:
        lines.append("*评分解释*")
        for e in exp[:5]:
            lines.append(f"- {e}")

    oi_narr = (dash.get("oi_narrative") or "").strip()
    if oi_narr:
        lines.append("*OI解读*")
        lines.append(f"- {oi_narr}")

    tw_view = dash.get("twitter_view") if isinstance(dash.get("twitter_view"), dict) else {}
    tw_sig = dash.get("twitter_signals") if isinstance(dash.get("twitter_signals"), list) else []
    if tw_view or tw_sig:
        lines.append("*Twitter观点（无引用）*")
        if tw_view:
            consensus = (tw_view.get("consensus") or "").strip()
            divergence = (tw_view.get("divergence") or "").strip()
            catalyst = (tw_view.get("catalyst") or "").strip()
            risk = (tw_view.get("risk") or "").strip()
            if consensus:
                lines.append(f"- 共识：{consensus}")
            if divergence:
                lines.append(f"- 分歧：{divergence}")
            if catalyst:
                lines.append(f"- 催化：{catalyst}")
            if risk:
                lines.append(f"- 风险：{risk}")
        if tw_sig:
            lines.append("- 信号：" + "；".join(str(x) for x in tw_sig[:5] if str(x).strip()))

    bullets = dash.get("bullets") if isinstance(dash.get("bullets"), list) else []
    if bullets:
        lines.append("*要点*")
        for b in bullets[:6]:
            t = str(b).strip()
            if t:
                lines.append(f"- {t}")

    acts = dash.get("actions") if isinstance(dash.get("actions"), list) else []
    if acts:
        lines.append("*操作*")
        for a in acts[:2]:
            t = str(a).strip()
            if t:
                lines.append(f"- {t}")

    risks = dash.get("risks") if isinstance(dash.get("risks"), list) else []
    if risks:
        lines.append("*风险*")
        for r in risks[:3]:
            t = str(r).strip()
            if t:
                lines.append(f"- {t}")

    return "\n".join(lines).strip() + "\n"


def _render_plan_text(plan: Dict[str, Any]) -> str:
    sym = (plan.get("symbol") or "").upper().strip()
    lines: List[str] = []
    lines.append(f"*{sym} 方案1 交易计划*")
    lines.append(f"- 倾向：{plan.get('bias') or '观望'}")

    setup = (plan.get("setup") or "").strip()
    if setup:
        lines.append(f"- 结构：{setup}")

    trg = plan.get("triggers") if isinstance(plan.get("triggers"), list) else []
    if trg:
        lines.append("- 触发：" + "；".join(str(x) for x in trg[:3] if x))

    tgt = plan.get("targets") if isinstance(plan.get("targets"), list) else []
    if tgt:
        lines.append("- 目标：" + "；".join(str(x) for x in tgt[:3] if x))

    inv = (plan.get("invalidation") or "").strip()
    if inv:
        lines.append(f"- 无效：{inv}")

    rn = plan.get("risk_notes") if isinstance(plan.get("risk_notes"), list) else []
    if rn:
        lines.append("- 风险：" + "；".join(str(x) for x in rn[:3] if x))

    bull = (plan.get("twitter_bull") or "").strip()
    bear = (plan.get("twitter_bear") or "").strip()
    q = (plan.get("twitter_quality") or "").strip()
    if bull or bear or q:
        parts = []
        if bull:
            parts.append(f"看多:{bull}")
        if bear:
            parts.append(f"看空:{bear}")
        if q:
            parts.append(f"质量:{q}")
        lines.append("- Twitter：" + " | ".join(parts))

    return "\n".join(lines).strip() + "\n"


def analyze_symbol(symbol: str, template: str = "dashboard", allow_llm: bool = True) -> Dict[str, Any]:
    prepared = run_prepare(symbol)
    errors = list(prepared.get("errors") or [])

    llm_used = False
    text = ""
    agent_obj: Optional[Dict[str, Any]] = None

    template = (template or "dashboard").strip().lower()
    if template not in {"dashboard", "plan"}:
        template = "dashboard"

    if template == "plan":
        plan = None
        if allow_llm and load_chat_api_key():
            plan = _llm_plan(prepared)
            llm_used = bool(plan)
        if not plan:
            plan = _rule_plan(prepared)
        text = _render_plan_text(plan)
        agent_obj = {"plan": plan}
    else:
        dash = None
        if allow_llm and load_chat_api_key():
            dash = _llm_dashboard(prepared)
            llm_used = bool(dash and isinstance(dash, dict) and (dash.get("bullets") or dash.get("risks")))
        if not dash:
            dash = _rule_dashboard(prepared)
        text = _render_dashboard_text(prepared, dash)
        agent_obj = {"dashboard": dash}

    chunks = split_whatsapp_text(text, max_chars=WHATSAPP_CHUNK_MAX)

    data = {
        "symbol": prepared.get("symbol"),
        "template": template,
        "prepared": prepared,
        "agent": agent_obj,
        "whatsapp": text.strip(),
        "whatsapp_chunks": chunks,
    }

    return {
        "data": data,
        "summary": text.strip(),
        "errors": errors,
        "use_llm": llm_used,
    }


__all__ = ["analyze_symbol", "normalize_symbol_input", "run_prepare"]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""On-demand single-symbol analysis (agent stage).

This is the *agent stage* for token-on-demand (perp symbol) analysis.
It follows the prepare->agent pattern aligned with scripts/hourly_prepare.py:

- scripts/analyze_symbol_prepare.py: deterministic collection/enrichment (NO LLM)
- scripts/analyze_symbol.py (this file): optional 1 LLM call to render a WhatsApp-friendly output

Default output template: 方案2 决策仪表盘
Optional: 方案1 交易计划 (use --template plan)

Usage:
  python3 scripts/analyze_symbol.py PUMPUSDT
  python3 scripts/analyze_symbol.py PUMP
  python3 scripts/analyze_symbol.py $PUMP
  python3 scripts/analyze_symbol.py PUMPUSDT --template plan
  python3 scripts/analyze_symbol.py PUMPUSDT --json
  python3 scripts/analyze_symbol.py pump --dry-run-normalize

Notes:
- If OPENAI_API_KEY is missing or LLM call fails, falls back to deterministic output.
- WhatsApp chunking enforced via market_hourly.render.WHATSAPP_CHUNK_MAX (~950 chars per chunk).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional

# make ./scripts importable
sys.path.insert(0, os.path.dirname(__file__))

from analyze_symbol_prepare import normalize_symbol_input, run_prepare  # noqa: E402
from market_hourly.llm_openai import chat_json, load_chat_api_key, summarize_oi_trading_plans  # noqa: E402
from market_hourly.render import WHATSAPP_CHUNK_MAX, split_whatsapp_text  # noqa: E402


def _fmt_pct(x: Optional[float]) -> str:
    return "?" if x is None else f"{x:+.1f}%"


def _fmt_num(x: Any) -> str:
    if x is None:
        return "?"
    try:
        return f"{float(x):.6g}"
    except Exception:
        return str(x)


def _fmt_usd(x: Any) -> str:
    if x is None:
        return "?"
    try:
        v = float(x)
        if abs(v) >= 1e9:
            return f"${v/1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v/1e6:.2f}M"
        if abs(v) >= 1e3:
            return f"${v/1e3:.1f}K"
        return f"${v:.0f}"
    except Exception:
        return "?"


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
    """Ask LLM to generate concise bullets for 方案2 (dashboard)."""

    if not load_chat_api_key():
        return None

    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}

    # Keep payload small but sufficient.
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
        "输出必须是JSON，字段：{verdict, bullets, actions, risks}。\n"
        "约束：\n"
        "- verdict 只能是: 偏多/偏空/观望/高波动\n"
        "- bullets: 4~6条，每条<=26字，直接可执行/可验证\n"
        "- actions: 1~2条，每条<=20字\n"
        "- risks: 2~3条，每条<=20字\n"
        "- 如果社交证据弱（kept少/ratio低），必须明确写在bullets或risks里\n"
    )

    try:
        return chat_json(system=system, user=json.dumps(payload, ensure_ascii=False), temperature=0.2, max_tokens=520, timeout=30)
    except Exception:
        return None


def _llm_plan(prepared: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ask LLM to generate 方案1 (trade plan)."""

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

    sym = (p.get("symbol") or "").upper().strip()
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

    bullets: List[str] = []
    bullets.append(f"价格24h {_fmt_pct(price.get('chg_24h_pct'))} | 4h {_fmt_pct(price.get('chg_4h_pct'))}")
    bullets.append(f"OI 24h {_fmt_pct(oi.get('chg_24h_pct'))} | 4h {_fmt_pct(oi.get('chg_4h_pct'))}")
    bullets.append(flow)

    lv = derived.get("key_levels") if isinstance(derived.get("key_levels"), dict) else {}
    sup = lv.get("support")
    res = lv.get("resistance")
    if sup is not None or res is not None:
        bullets.append(f"关键位：上{_fmt_num(res)} / 下{_fmt_num(sup)}")

    if total:
        bullets.append(f"社交证据：有效{kept}/{total}")
    else:
        bullets.append("社交证据：暂无/抓取失败")

    actions = ["等关键位确认再出手"]
    if verdict == "偏多" and sup is not None:
        actions = [f"回踩{_fmt_num(sup)}不破再偏多"]
    elif verdict == "偏空" and res is not None:
        actions = [f"反抽{_fmt_num(res)}受压再偏空"]

    risks: List[str] = ["勿追单；优先等收线"]
    if total and kept <= 1:
        risks.append("社交讨论偏少")

    return {"verdict": verdict, "bullets": bullets[:6], "actions": actions[:2], "risks": risks[:3]}


def _rule_plan(prepared: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback plan (compact)."""

    p = prepared.get("prepared") if isinstance(prepared.get("prepared"), dict) else {}
    sym = (p.get("symbol") or "").upper().strip()

    price = p.get("price") if isinstance(p.get("price"), dict) else {}
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
        triggers.append(f"突破站稳{_fmt_num(res)}")
    if sup is not None:
        triggers.append(f"跌破收在{_fmt_num(sup)}下")

    targets: List[str] = []
    if res is not None:
        targets.append(f"目标看{_fmt_num(res)}上方扩展")
    if sup is not None:
        targets.append(f"目标看{_fmt_num(sup)}下方延伸")

    invalid = "确认失败则撤"
    if bias == "偏多" and sup is not None:
        invalid = f"有效跌破{_fmt_num(sup)}"[:28]
    if bias == "偏空" and res is not None:
        invalid = f"有效站回{_fmt_num(res)}"[:28]

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
    lines.append(f"- 现价：{_fmt_num(price.get('now'))} | 24h {_fmt_pct(price.get('chg_24h_pct'))}")
    lines.append(
        f"- 涨跌：1h {_fmt_pct(price.get('chg_1h_pct'))} | 4h {_fmt_pct(price.get('chg_4h_pct'))}"
    )
    lines.append(
        f"- OI：1h {_fmt_pct(oi.get('chg_1h_pct'))} | 4h {_fmt_pct(oi.get('chg_4h_pct'))} | 24h {_fmt_pct(oi.get('chg_24h_pct'))}"
    )
    lines.append(f"- OI名义：{_fmt_usd(oi.get('oi_value_now'))}")

    mc = market.get("market_cap")
    fdv = market.get("fdv")
    if mc is not None or fdv is not None:
        bits = []
        if mc is not None:
            bits.append(f"MC{_fmt_usd(mc)}")
        if fdv is not None:
            bits.append(f"FDV{_fmt_usd(fdv)}")
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
        lines.append(f"- 关键位：上{_fmt_num(lv.get('resistance'))} / 下{_fmt_num(lv.get('support'))}")

    # Key structure data (compact, WhatsApp-friendly)
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
        struct_lines.append(f"1H swing：上{_fmt_num(k1_sw.get('hi'))} / 下{_fmt_num(k1_sw.get('lo'))}")
    if k4_sw.get("hi") is not None or k4_sw.get("lo") is not None:
        struct_lines.append(f"4H swing：上{_fmt_num(k4_sw.get('hi'))} / 下{_fmt_num(k4_sw.get('lo'))}")
    if k1_rg.get("hi") is not None or k1_rg.get("lo") is not None:
        pos = k1_rg.get("pos")
        pos_s = "?" if pos is None else f"{float(pos):.2f}"
        struct_lines.append(f"1H 区间：{_fmt_num(k1_rg.get('lo'))}~{_fmt_num(k1_rg.get('hi'))} | pos {pos_s}")

    ind_bits: List[str] = []
    if ema4 is not None or slope4 is not None:
        if isinstance(slope4, (int, float)):
            ind_bits.append(f"4H EMA20 {_fmt_num(ema4)} | 斜率{slope4:+.2f}%")
        else:
            ind_bits.append(f"4H EMA20 {_fmt_num(ema4)}")
    if rsi1 is not None or rsi4 is not None:
        ind_bits.append(f"RSI：1H {_fmt_num(rsi1)} | 4H {_fmt_num(rsi4)}")
    if atr1 is not None or atr4 is not None:
        ind_bits.append(f"ATR：1H {_fmt_num(atr1)} | 4H {_fmt_num(atr4)}")
    if vol1.get("ratio") is not None:
        ind_bits.append(f"量能比(1H)：{_fmt_num(vol1.get('ratio'))}")

    if struct_lines or ind_bits:
        lines.append("*关键结构数据*")
        for s in (struct_lines + ind_bits)[:6]:
            lines.append(f"- {s}")

    # Social detail (no quotes)
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
            lines.append(f"- 倾向分：{_fmt_num(st.get('stance_score'))}（-1空/+1多）")

    # Score explanation (deterministic, avoid pretending precision)
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

    # Optional twitter fields from summarize_oi_trading_plans
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol", help="e.g. PUMPUSDT | PUMP | $pump")
    ap.add_argument("--template", choices=["dashboard", "plan"], default="dashboard")
    ap.add_argument("--json", action="store_true", help="emit json (includes whatsapp chunks)")
    ap.add_argument("--no-llm", action="store_true", help="force deterministic output")
    ap.add_argument("--dry-run-normalize", action="store_true", help="print normalization json and exit")
    args = ap.parse_args()

    if args.dry_run_normalize:
        print(json.dumps(normalize_symbol_input(args.symbol), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    prepared = run_prepare(args.symbol)

    llm_used = False
    text = ""
    agent_obj: Optional[Dict[str, Any]] = None

    if args.template == "plan":
        plan = None
        if not args.no_llm:
            plan = _llm_plan(prepared)
            llm_used = bool(plan)
        if not plan:
            plan = _rule_plan(prepared)
        text = _render_plan_text(plan)
        agent_obj = {"plan": plan}

    else:
        dash = None
        if not args.no_llm:
            dash = _llm_dashboard(prepared)
            llm_used = bool(dash and isinstance(dash, dict) and (dash.get("bullets") or dash.get("risks")))
        if not dash:
            dash = _rule_dashboard(prepared)
        text = _render_dashboard_text(prepared, dash)
        agent_obj = {"dashboard": dash}

    chunks = split_whatsapp_text(text, max_chars=WHATSAPP_CHUNK_MAX)

    if args.json:
        out = {
            "symbol": prepared.get("symbol"),
            "template": args.template,
            "use_llm": llm_used,
            "prepared": prepared,
            "agent": agent_obj,
            "whatsapp": text.strip(),
            "whatsapp_chunks": chunks,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # Text mode: print each chunk separated, so it can be sent chunk-by-chunk.
    if not chunks:
        print(text)
        return 0

    sep = "\n\n---\n\n"
    print(sep.join(chunks).strip() + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

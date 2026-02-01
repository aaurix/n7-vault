#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Rendering helpers for the hourly WhatsApp/Markdown output."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from hourly.perp_dashboard import render_perp_dashboards_mini


WHATSAPP_CHUNK_MAX = 950


def split_whatsapp_text(text: str, *, max_chars: int = WHATSAPP_CHUNK_MAX) -> List[str]:
    """Split WhatsApp message into chunks.

    WhatsApp messages can truncate/fail when too long; we keep each chunk <= max_chars.
    Splitting tries to respect newlines/section boundaries.
    """

    s = (text or "").strip()
    if not s:
        return []

    # Normalize newlines (keep explicit line boundaries).
    lines = s.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    chunks: List[str] = []
    cur: str = ""

    def flush() -> None:
        nonlocal cur
        t = cur.strip()
        if t:
            chunks.append(t)
        cur = ""

    def split_long_line(line: str) -> List[str]:
        """Split a single overlong line into <=max_chars pieces."""

        out: List[str] = []
        rest = (line or "").strip()
        while rest and len(rest) > max_chars:
            window = rest[:max_chars]
            # Try to split near the end at a natural boundary.
            cut = max_chars
            for sep in [" ", "；", ";", "，", ",", "。", ".", "|", "/"]:
                idx = window.rfind(sep)
                if idx >= int(max_chars * 0.6):
                    cut = idx + 1
                    break
            out.append(rest[:cut].strip())
            rest = rest[cut:].strip()
        if rest:
            out.append(rest)
        return out

    for line in lines:
        line = (line or "").rstrip()
        if not line:
            # Preserve paragraph breaks when possible.
            if cur and not cur.endswith("\n"):
                cur += "\n"
            continue

        candidate = (cur + "\n" + line).strip() if cur else line.strip()
        if len(candidate) <= max_chars:
            cur = candidate
            continue

        # Candidate would exceed the limit.
        if cur:
            flush()

        if len(line) <= max_chars:
            cur = line.strip()
            continue

        # Overlong single line: split it.
        for part in split_long_line(line):
            if len(part) <= max_chars:
                chunks.append(part)
            else:
                chunks.append(part[:max_chars].strip())
        cur = ""

    flush()

    # Defensive: enforce max_chars.
    out2: List[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            out2.append(c)
        else:
            out2.extend(split_long_line(c))
    return [x for x in out2 if x and len(x) <= max_chars]


_WA_MAX_CHARS = WHATSAPP_CHUNK_MAX


def _is_whatsapp_header(line: str) -> bool:
    t = (line or "").strip()
    return t.startswith("*") and t.endswith("*") and len(t) <= 60


def _section_priority(header: str) -> int:
    h = (header or "").strip("*")
    if "社媒补充" in h:
        return 5
    if "Twitter" in h or "跟随时间线" in h:
        return 4
    if "关注" in h or "情绪" in h or "弱信号" in h:
        return 4
    if "Telegram可交易标的" in h or "叙事/事件" in h or "叙事" in h:
        return 3
    if "二级山寨" in h:
        return 2
    return 0


def _is_x_section(header: str) -> bool:
    t = (header or "").strip()
    if t.startswith("*") and t.endswith("*"):
        t = t.strip("*").strip()
    elif t.startswith("## "):
        t = t[3:].strip()
    return "社媒补充" in t and "X" in t


def _apply_whatsapp_budget(
    lines: List[str], *, max_chars: int = _WA_MAX_CHARS, exclude_x: bool = False
) -> List[str]:
    if not lines:
        return []

    sections: List[Dict[str, Any]] = []
    cur: List[str] = []
    for line in lines:
        if _is_whatsapp_header(line):
            if cur:
                sections.append({"lines": cur})
            cur = [line]
        else:
            if not cur:
                cur = [line]
            else:
                cur.append(line)
    if cur:
        sections.append({"lines": cur})

    for idx, sec in enumerate(sections):
        header = sec["lines"][0] if sec["lines"] else ""
        sec["priority"] = _section_priority(header)
        sec["is_x"] = _is_x_section(header)
        if idx == 0:
            sec["min_keep"] = len(sec["lines"])
        else:
            sec["min_keep"] = 2 if len(sec["lines"]) > 1 else len(sec["lines"])

    def _total_len(include_x: bool = True) -> int:
        all_lines = [
            ln
            for sec in sections
            for ln in sec["lines"]
            if include_x or (not sec.get("is_x"))
        ]
        return sum(len(ln) for ln in all_lines) + max(0, len(all_lines) - 1)

    budget_len = _total_len(include_x=not exclude_x)
    if budget_len <= max_chars:
        return lines

    guard = 0
    while _total_len(include_x=not exclude_x) > max_chars and guard < 2000:
        guard += 1
        candidates = [
            sec
            for sec in sections
            if len(sec["lines"]) > int(sec["min_keep"])
            and (not exclude_x or not sec.get("is_x"))
        ]
        if not candidates:
            break
        sec = min(candidates, key=lambda s: int(s.get("priority", 0)))
        sec["lines"].pop()

    out: List[str] = []
    for sec in sections:
        out.extend(sec["lines"])
    return out


def _cn_num(x: Any) -> str:
    if x is None:
        return "?"
    try:
        if isinstance(x, str):
            x = float(x)
        if abs(x) >= 1e9:
            return f"{x/1e9:.1f}B"
        if abs(x) >= 1e6:
            return f"{x/1e6:.1f}M"
        if abs(x) >= 1e3:
            return f"{x/1e3:.1f}K"
        return f"{x:.0f}"
    except Exception:
        return str(x)


def _fmt_price(x: Any) -> str:
    if x is None:
        return "?"
    try:
        v = float(x)
    except Exception:
        return str(x)
    try:
        if abs(v) >= 1000:
            return f"{v:.0f}"
        if abs(v) >= 100:
            return f"{v:.2f}"
        if abs(v) >= 10:
            return f"{v:.3f}"
        if abs(v) >= 1:
            return f"{v:.4f}"
        if abs(v) >= 0.01:
            return f"{v:.5f}"
        return f"{v:.6g}" if v != 0 else "0"
    except Exception:
        return str(x)


def _fmt_usd(x: Any) -> str:
    if x is None:
        return "?"
    try:
        v = float(x)
    except Exception:
        return str(x)
    if v == 0:
        return "$0"
    return f"${_cn_num(v)}" if _cn_num(v) != "?" else "?"


def build_summary(
    *,
    title: str,
    oi_lines: List[str],
    plans: Optional[List[Dict[str, Any]]] = None,
    narratives: Optional[List[Dict[str, Any]]] = None,
    threads: Optional[List[Dict[str, Any]]] = None,
    weak_threads: Optional[List[Dict[str, Any]]] = None,
    social_cards: Optional[List[Dict[str, Any]]] = None,
    twitter_following_summary: Optional[Dict[str, Any]] = None,
    overlap_syms: Optional[List[str]] = None,
    sentiment: str = "",
    watch: Optional[List[str]] = None,
    perp_dash_inputs: Optional[List[Dict[str, Any]]] = None,
    whatsapp: bool = True,
    show_twitter_metrics: bool = False,
) -> str:
    def H(s: str) -> str:
        return f"*{s}*" if whatsapp else f"## {s}"

    out: List[str] = []
    out.append(f"*{title}*" if whatsapp else title)

    oi_lines = oi_lines or []

    dash_inputs = perp_dash_inputs if isinstance(perp_dash_inputs, list) else []
    dash_inputs = [d for d in dash_inputs if isinstance(d, dict) and str(d.get("symbol") or "").strip()]

    # Prefer the richer deterministic mini dashboards when available.
    if dash_inputs:
        out.append(H("二级山寨Top3（决策仪表盘mini+计划）" if plans else "二级山寨Top3（决策仪表盘mini）"))

        # Optional: use plan bias (LLM) to override rule bias in the mini dashboard.
        sym2plan: Dict[str, Dict[str, Any]] = {}
        sym2bias: Dict[str, str] = {}
        if plans:
            for p in (plans or [])[:5]:
                if not isinstance(p, dict):
                    continue
                sym = str(p.get("symbol") or "").upper().strip()
                if not sym or sym in sym2plan:
                    continue
                sym2plan[sym] = p
                b = str(p.get("bias") or "").strip()
                if b:
                    sym2bias[sym] = b

        for i, d in enumerate(dash_inputs[:3], 1):
            sym = str(d.get("symbol") or "").upper().strip()
            d2 = dict(d)
            if sym in sym2bias:
                d2["bias_hint"] = sym2bias[sym]

            block = render_perp_dashboards_mini([d2], top_n=1)
            if block:
                if str(block[0]).startswith("1)"):
                    block[0] = str(block[0]).replace("1)", f"{i})", 1)
            out.extend(block)

            # Attach compact plan line when available (keep bounded).
            p = sym2plan.get(sym) if plans else None
            if isinstance(p, dict):
                setup = (p.get("setup") or "").strip()
                trg = p.get("triggers") if isinstance(p.get("triggers"), list) else []
                tgt = p.get("targets") if isinstance(p.get("targets"), list) else []
                inv = (p.get("invalidation") or "").strip()

                chunks: List[str] = []
                if setup:
                    chunks.append(f"结构:{setup}")
                if trg:
                    chunks.append("触发:" + "；".join([str(x) for x in trg[:2] if x]))
                if tgt:
                    chunks.append("目标:" + "；".join([str(x) for x in tgt[:2] if x]))
                if inv:
                    chunks.append(f"无效:{inv}")

                if chunks:
                    out.append("   - 计划：" + " | ".join(chunks))

                # Top1 only: include Twitter view summary (no raw snippets)
                if i == 1:
                    q = (p.get("twitter_quality") or "").strip()
                    bull = (p.get("twitter_bull") or "").strip()
                    bear = (p.get("twitter_bear") or "").strip()

                    meta = p.get("twitter_meta") if isinstance(p.get("twitter_meta"), dict) else None
                    total = meta.get("total") if meta else None
                    kept = meta.get("kept") if meta else None

                    if (bull or bear or q) or (meta and (total is not None or kept is not None)):
                        parts = []
                        if bull:
                            parts.append(f"看多:{bull}")
                        if bear:
                            parts.append(f"看空:{bear}")
                        if q:
                            parts.append(f"质量:{q}")
                        if not parts:
                            parts.append("无明确多空观点")

                        tail = f"（{kept}/{total}）" if (kept is not None or total is not None) else ""
                        out.append(f"   - 社媒补充：{' | '.join(parts)}{tail}")

    # Fallback to the legacy oi_lines when dashboards are unavailable.
    elif plans:
        out.append(H("二级山寨Top3（趋势+计划）"))

        # build symbol -> trend line mapping
        sym2trend: Dict[str, str] = {}
        for ln in oi_lines:
            t = (ln or "").strip()
            if not t.startswith("-"):
                continue
            body = t.lstrip("-").strip()
            sym = body.split(" ", 1)[0].strip().upper() if body else ""
            if sym and sym not in sym2trend:
                # keep the rest as a compact descriptor
                rest = body[len(sym):].strip()
                sym2trend[sym] = rest

        for i, p in enumerate((plans or [])[:3], 1):
            sym = (p.get("symbol") or "").upper().strip()
            bias = p.get("bias") or "观望"
            setup = (p.get("setup") or "").strip()

            # Line 1: symbol + current state (compact)
            trend = sym2trend.get(sym) or ""
            if trend:
                out.append(f"{i}) {sym}（{bias}）现状：{trend}")
            else:
                out.append(f"{i}) {sym}（{bias}）")

            # Line 2: compact plan (structure + triggers + targets + invalidation)
            trg = p.get("triggers") if isinstance(p.get("triggers"), list) else []
            tgt = p.get("targets") if isinstance(p.get("targets"), list) else []
            inv = (p.get("invalidation") or "").strip()

            chunks: List[str] = []
            if setup:
                chunks.append(f"结构:{setup}")
            if trg:
                chunks.append("触发:" + "；".join([str(x) for x in trg[:2] if x]))
            if tgt:
                chunks.append("目标:" + "；".join([str(x) for x in tgt[:2] if x]))
            if inv:
                chunks.append(f"无效:{inv}")

            if chunks:
                out.append("   - 计划：" + " | ".join(chunks))

            rn = p.get("risk_notes")
            if isinstance(rn, list) and rn:
                out.append(f"   - 风险：{str(rn[0])}")

            # Top1: include Twitter views summary (no raw snippets)
            if i == 1:
                q = (p.get("twitter_quality") or "").strip()
                bull = (p.get("twitter_bull") or "").strip()
                bear = (p.get("twitter_bear") or "").strip()

                meta = p.get("twitter_meta") if isinstance(p.get("twitter_meta"), dict) else None
                total = meta.get("total") if meta else None
                kept = meta.get("kept") if meta else None

                # show line if we have any twitter meta, even if LLM couldn't summarize
                if (bull or bear or q) or (meta and (total is not None or kept is not None)):
                    parts = []
                    if bull:
                        parts.append(f"看多:{bull}")
                    if bear:
                        parts.append(f"看空:{bear}")
                    if q:
                        parts.append(f"质量:{q}")
                    if not parts:
                        parts.append("无明确多空观点")

                    tail = f"（{kept}/{total}）" if (kept is not None or total is not None) else ""
                    out.append(f"   - 社媒补充：{' | '.join(parts)}{tail}")

    else:
        out.append(H("二级山寨（趋势观点：1H+4H）"))
        if oi_lines:
            out.extend(oi_lines)
        else:
            out.append("- 无明确 OI/Price 异动信号")

    def _is_actionable(it: Any) -> bool:
        return isinstance(it, dict) and bool(it.get("asset_name") or it.get("why_buy") or it.get("why_not_buy"))

    actionable_mode = bool(narratives and any(_is_actionable(it) for it in narratives))

    if actionable_mode:
        out.append(H("Telegram交易线索Top5"))
        if narratives:
            for i, it in enumerate((narratives or [])[:5], 1):
                if not isinstance(it, dict):
                    continue
                asset = str(it.get("asset_name") or it.get("asset") or it.get("symbol") or "").strip()
                if not asset:
                    continue
                why_buy = str(it.get("why_buy") or "").strip()
                why_not = str(it.get("why_not_buy") or "").strip()
                trigger = str(it.get("trigger") or "").strip()
                risk = str(it.get("risk") or "").strip()
                ev = it.get("evidence_snippets") if isinstance(it.get("evidence_snippets"), list) else []
                line = f"{i}) {asset}"
                parts: List[str] = []
                if why_buy:
                    parts.append(f"买:{why_buy}")
                if why_not:
                    parts.append(f"不买:{why_not}")
                if parts:
                    line += "（" + " | ".join(parts) + "）"
                out.append(line)
                if trigger:
                    out.append(f"   - 触发：{trigger}")
                if risk:
                    out.append(f"   - 风险：{risk}")
                if ev:
                    out.append("   - 证据：" + " | ".join([str(x) for x in ev[:2] if x]))
        else:
            out.append("- 无明显交易线索")
    else:
        out.append(H("Telegram热点Top5（提炼）"))
        if narratives:
            for i, it in enumerate((narratives or [])[:5], 1):
                one = it.get("one_liner") or ""
                sen = it.get("sentiment") or "中性"
                tri = it.get("triggers") or ""
                rel = it.get("related_assets") or []
                inferred = bool(it.get("_inferred"))
                if isinstance(rel, list) and rel:
                    prefix = "（推断）" if inferred else ""
                    rel_s = " | 关联" + prefix + ": " + ", ".join(rel)
                else:
                    rel_s = ""
                out.append(f"{i}) {one}（{sen}）{rel_s}")
                if tri:
                    out.append(f"   - 触发：{tri}")
        else:
            out.append("- 无明显叙事（观点分散/多为零散聊天）")

        out.append(H("Telegram可交易标的Top5（观点提炼）"))
        if threads:
            for i, th in enumerate(threads[:5], 1):
                out.append(f"{i}) {th.get('title')}（{th.get('stance')}，热度{th.get('count')}）")
                # Prefer LLM fields if present
                if th.get("thesis"):
                    out.append(f"   - 叙事：{th.get('thesis')}")
                if th.get("drivers"):
                    out.append(f"   - 驱动：{th.get('drivers')}")
                if th.get("risks"):
                    out.append(f"   - 风险：{th.get('risks')}")
                if th.get("trade_implication"):
                    out.append(f"   - 交易含义：{th.get('trade_implication')}")
                else:
                    # If we have no LLM fields and no meaningful points, avoid repetitive filler.
                    pts = [p for p in (th.get("points") or []) if p and "缺少明确事件/结构点" not in str(p)]
                    for p in pts[:3]:
                        out.append(f"   - {p}")
        else:
            out.append("- 本小时未出现热度≥1的可交易标的讨论")

        if (not threads) and weak_threads:
            out.append(H("弱信号候选（热度=2，仅供观察）"))
            for i, th in enumerate(weak_threads[:3], 1):
                out.append(f"{i}) {th.get('title')}（{th.get('stance')}）")
                pts = th.get("points") or []
                if pts:
                    out.append(f"   - {pts[0]}")

    tw = twitter_following_summary if isinstance(twitter_following_summary, dict) else {}
    tw_narratives = tw.get("narratives") if isinstance(tw.get("narratives"), list) else []
    tw_events = tw.get("events") if isinstance(tw.get("events"), list) else []
    tw_sent = str(tw.get("sentiment") or "").strip()

    def _fmt_tw_list(items: List[Any]) -> str:
        out_items: List[str] = []
        for it in items:
            s = str(it).strip().lstrip("- ")
            if not s:
                continue
            if len(s) > 80:
                s = s[:80]
            if s in out_items:
                continue
            out_items.append(s)
            if len(out_items) >= 3:
                break
        return "；".join(out_items) if out_items else "无明显"

    def _fmt_pct(val: Any) -> str:
        if val is None:
            return ""
        try:
            v = float(val)
        except Exception:
            return ""
        if v < 0:
            return ""
        if v <= 1.2:
            return f"{v * 100:.0f}%"
        return f"{v:.0f}%"

    out.append(H("Twitter跟随时间线（近1小时）"))
    out.append(f"- 叙事：{_fmt_tw_list(tw_narratives)}")
    out.append(f"- 情绪：{tw_sent or '中性'}")
    out.append(f"- 重大事件：{_fmt_tw_list(tw_events)}")

    if show_twitter_metrics:
        tw_meta = tw.get("meta") if isinstance(tw.get("meta"), dict) else {}
        tw_metrics = tw_meta.get("metrics") if isinstance(tw_meta.get("metrics"), dict) else {}
        if not tw_metrics and isinstance(tw.get("metrics"), dict):
            tw_metrics = tw.get("metrics")
        if isinstance(tw_metrics, dict) and tw_metrics:
            noise_rate = _fmt_pct(tw_metrics.get("noise_drop_rate"))
            dedupe_rate = _fmt_pct(tw_metrics.get("dedupe_rate"))
            clusters = tw_metrics.get("clusters")
            if clusters is None:
                clusters = tw_meta.get("clusters")
            parts: List[str] = []
            if noise_rate:
                parts.append(f"噪声↓{noise_rate}")
            if dedupe_rate:
                parts.append(f"去重率{dedupe_rate}")
            if clusters is not None:
                parts.append(f"聚类{clusters}")
            if parts:
                out.append("- 质量：" + " | ".join(parts))


    out.append(H("社媒补充（TG/X信号卡Top2）"))
    cards = social_cards or []
    card_limit = 2
    if cards:
        for i, it in enumerate(cards[:card_limit], 1):
            if not isinstance(it, dict):
                continue
            sym = str(it.get("symbol") or it.get("asset_name") or "").strip()
            if not sym:
                continue

            source = str(it.get("source") or "").strip().lower()
            src_label = "X" if source == "twitter" else ("TG" if source == "tg" else "")

            symbol_type = str(it.get("symbol_type") or "").strip().lower()
            chain = str(it.get("chain") or "").strip()
            type_label = "链上" if symbol_type == "onchain" else ("CEX" if symbol_type == "cex" else "")
            if chain:
                type_label = f"{type_label}/{chain}" if type_label else chain

            label_bits = [x for x in [src_label, type_label] if x]

            price = it.get("price")
            mc = it.get("market_cap")
            fdv = it.get("fdv")

            line = f"{i}) {sym}"
            if label_bits:
                line += f"（{'/'.join(label_bits)}）"
            line += f"价{_fmt_price(price)}"

            mc_bits: List[str] = []
            if mc is not None:
                mc_bits.append(f"MC{_fmt_usd(mc)}")
            if fdv is not None:
                mc_bits.append(f"FDV{_fmt_usd(fdv)}")
            if mc_bits:
                line += " | " + "/".join(mc_bits)
            out.append(line)

            one = str(it.get("one_liner") or "").strip()
            sen = str(it.get("sentiment") or "").strip()
            sig = str(it.get("signals") or "").strip()
            ev = it.get("evidence_snippets") if isinstance(it.get("evidence_snippets"), list) else []

            if one:
                tail = f"（{sen}）" if sen else ""
                out.append(f"   - 观点：{one}{tail}")
            elif sen:
                out.append(f"   - 情绪：{sen}")

            drivers_raw = it.get("drivers")
            drivers_list: List[str] = []
            if isinstance(drivers_raw, list):
                drivers_list = [str(x).strip() for x in drivers_raw if str(x).strip()]
            elif isinstance(drivers_raw, str) and drivers_raw.strip():
                drivers_list = [x.strip() for x in drivers_raw.split(";") if x.strip()]
            drivers_list = drivers_list[:3]

            risk = str(it.get("risk") or "").strip()
            if drivers_list:
                out.append(f"   - 驱动：{'；'.join(drivers_list)}")
            if risk:
                out.append(f"   - 风险：{risk}")

            if sig:
                out.append(f"   - 信号：{sig}")
            if ev and not one:
                out.append("   - 证据：" + " | ".join([str(x) for x in ev[:2] if x]))
    else:
        out.append("- 无")

    out.append(H("情绪"))
    out.append(sentiment or "")

    out.append(H("关注"))
    watch = watch or []
    if watch:
        out.extend([f"- {x}" for x in watch[:3]])
    else:
        out.append("- 无")

    lines = out
    has_x_section = whatsapp and any(_is_x_section(ln) for ln in out if _is_whatsapp_header(ln))
    if whatsapp:
        lines = _apply_whatsapp_budget(out, max_chars=_WA_MAX_CHARS, exclude_x=has_x_section)

    txt = "\n".join(lines).strip()
    if whatsapp and len(txt) > _WA_MAX_CHARS and not has_x_section:
        txt = txt[: (_WA_MAX_CHARS - 10)].rstrip() + "…"
    return txt

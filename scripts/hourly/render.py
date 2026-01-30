#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Rendering helpers for the hourly WhatsApp/Markdown output."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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


def build_summary(
    *,
    title: str,
    oi_lines: List[str],
    plans: Optional[List[Dict[str, Any]]] = None,
    narratives: Optional[List[Dict[str, Any]]] = None,
    threads: Optional[List[Dict[str, Any]]] = None,
    weak_threads: Optional[List[Dict[str, Any]]] = None,
    twitter_lines: Optional[List[str]] = None,
    overlap_syms: Optional[List[str]] = None,
    sentiment: str = "",
    watch: Optional[List[str]] = None,
    whatsapp: bool = True,
) -> str:
    def H(s: str) -> str:
        return f"*{s}*" if whatsapp else f"## {s}"

    out: List[str] = []
    out.append(f"*{title}*" if whatsapp else title)

    oi_lines = oi_lines or []

    # Merge OI trend + trader plan into one section when plans exist (user request).
    if plans:
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
                    out.append(f"   - Twitter：{' | '.join(parts)}{tail}")

    else:
        out.append(H("二级山寨（趋势观点：1H+4H）"))
        if oi_lines:
            out.extend(oi_lines)
        else:
            out.append("- 无明确 OI/Price 异动信号")

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

    out.append(H("Telegram可交易标的Top5（LLM提炼）"))
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

    out.append(H("Twitter（CA+$SYMBOL观点Top5）"))
    twitter_topics = (twitter_lines or [])
    if twitter_topics:
        for i, it in enumerate(twitter_topics[:5], 1):
            one = it.get("one_liner") if isinstance(it, dict) else str(it)
            sen = it.get("sentiment") if isinstance(it, dict) else ""
            sig = it.get("signals") if isinstance(it, dict) else ""
            rel_s = ""  # do not show related_assets for Twitter topics
            if sen:
                out.append(f"{i}) {one}（{sen}）{rel_s}")
            else:
                out.append(f"{i}) {one}{rel_s}")
            if sig:
                out.append(f"   - 信号：{sig}")
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

    txt = "\n".join(out).strip()
    if len(txt) > 1400:
        txt = txt[:1390] + "…"
    return txt

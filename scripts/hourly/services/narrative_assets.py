#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Narrative asset inference from Telegram context."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..dexscreener import enrich_symbol, resolve_addr_symbol
from ..filters import extract_symbols_and_addrs
from ..models import PipelineContext
from .pipeline_timing import measure


def infer_narrative_assets_from_tg(ctx: PipelineContext) -> None:
    """Best-effort asset linking for TG narratives, using TG-only token contexts."""

    done = measure(ctx.perf, "narrative_asset_infer")

    # If we're in actionable mode, asset_name already anchors the item.
    if ctx.narratives and any(isinstance(it, dict) and it.get("asset_name") for it in ctx.narratives):
        for it in ctx.narratives:
            asset = str(it.get("asset_name") or "").strip()
            if asset:
                it["related_assets"] = [asset]
                it["_inferred"] = False
        done()
        return

    # Candidate universe: Telegram token threads only.
    tg_syms: List[str] = [str(t.get("sym") or "").upper().strip() for t in (ctx.threads or []) if t.get("sym")]
    candidates: List[str] = []
    seen: set[str] = set()
    for x in tg_syms:
        if x and x not in seen:
            seen.add(x)
            candidates.append(x)

    # Context text per symbol from Telegram thread messages.
    sym_ctx: Dict[str, str] = {}
    for th in (ctx.strong_threads or []) + (ctx.weak_threads or []):
        s = str(th.get("sym") or "").upper().strip()
        if not s:
            continue
        msgs = th.get("_msgs") or []
        sym_ctx[s] = " ".join([str(x) for x in msgs[:20]])

    import re

    def _kw(s: str) -> List[str]:
        s = (s or "").lower()
        latin = re.findall(r"[a-z0-9_]{3,}", s)
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", s)
        cjk2: List[str] = []
        for w in cjk:
            w = w.strip()
            for i in range(0, min(len(w) - 1, 6)):
                cjk2.append(w[i : i + 2])
        out = latin + cjk2
        stop = {"市场", "项目", "代币", "价格", "今天", "现在", "小时", "社区", "交易", "流动性"}
        out2: List[str] = []
        seen2: set[str] = set()
        for x in out:
            if x in stop or len(x) < 2:
                continue
            if x not in seen2:
                seen2.add(x)
                out2.append(x)
        return out2[:30]

    def _score(nar: Dict[str, Any], sym: str) -> int:
        k = _kw(f"{nar.get('one_liner','')} {nar.get('triggers','')}")
        if not k:
            return 0
        ctx_txt = (sym_ctx.get(sym) or "").lower()
        if not ctx_txt:
            return 0
        return sum(1 for w in k if w and w in ctx_txt)

    def _extract_token_hints(nar: Dict[str, Any]) -> List[str]:
        s = f"{nar.get('one_liner','')} {nar.get('triggers','')}".strip()
        if not s:
            return []
        hints = [x[1:] for x in re.findall(r"\$([A-Za-z0-9]{2,12})", s)]
        hints += re.findall(r"\b([A-Za-z]{3,12})\b", s)
        out: List[str] = []
        seenh: set[str] = set()
        bad = {"bsc", "sol", "base", "eth", "btc", "usdt", "usdc", "dex", "alpha"}
        for h in hints:
            hu = h.upper()
            if hu.lower() in bad:
                continue
            if hu not in seenh:
                seenh.add(hu)
                out.append(hu)
        return out[:3]

    def _find_addr_near_hint(hint: str) -> Optional[str]:
        for t in ctx.human_texts:
            if hint.lower() in (t or "").lower():
                _sy, _ad = extract_symbols_and_addrs(t)
                if _ad:
                    return _ad[0]
        return None

    def _pin_hint(hint: str) -> Optional[str]:
        d = enrich_symbol(hint)
        if d:
            return hint
        addr = _find_addr_near_hint(hint)
        if addr:
            rs = resolve_addr_symbol(addr)
            if rs:
                return rs
        return None

    for it in ctx.narratives:
        # Explicit hints first.
        pinned: List[str] = []
        for h in _extract_token_hints(it):
            p = _pin_hint(h)
            if p and p not in pinned:
                pinned.append(p)
        if pinned:
            it["related_assets"] = pinned[:6]
            it["_inferred"] = False
            one = str(it.get("one_liner") or "")
            if pinned and ("某个代币" in one or "某个项目" in one):
                it["one_liner"] = one.replace("某个代币", pinned[0]).replace("某个项目", pinned[0])
            continue

        # LLM-provided related_assets: keep but do not allow Twitter-only tickers.
        rel = it.get("related_assets")
        rel2: List[str] = []
        if isinstance(rel, list):
            for x in rel:
                xs = str(x).strip()
                if not xs:
                    continue
                up = xs.upper()
                if candidates and re.fullmatch(r"[A-Z0-9]{2,10}", up) and up not in candidates:
                    continue
                rel2.append(up)
        if rel2:
            it["related_assets"] = rel2[:6]
            it["_inferred"] = False
            continue

        # Infer from Telegram-only candidates.
        if not candidates:
            continue
        scored = [(c, _score(it, c)) for c in candidates]
        scored.sort(key=lambda x: (-x[1], x[0]))
        top = [f"{c}({sc})" for c, sc in scored if sc >= 1][:6]
        if top:
            it["related_assets"] = top
            it["_inferred"] = True

    done()

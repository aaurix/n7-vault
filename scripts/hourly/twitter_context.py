#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Twitter context gathering + filtering for a futures symbol.

Goal (production):
- Provide a small, de-noised set of trader-relevant snippets without extra LLM calls.
- Use bird search (cookie auth) and filter out obvious promo/bot spam.

This is used as auxiliary context for OI trader plans.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List


_PROMO_PAT = re.compile(
    r"(join our telegram|vip telegram|dm to join|link in bio|join alpha|calls|signal active|\bvip\b|airdrop\b|giveaway)",
    re.IGNORECASE,
)

_BOTISH_PAT = re.compile(r"(#\w+\s*){6,}")


def _run_bird_search(query: str, *, n: int = 30, timeout_s: int = 18) -> List[Dict[str, Any]]:
    cmd = ["bird", "search", query, "-n", str(n), "--json"]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s)
        raw = (p.stdout or "").strip()
        if not raw:
            return []
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _is_good_snippet(text: str, *, symbol: str, base: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if _PROMO_PAT.search(t):
        return False
    if _BOTISH_PAT.search(t):
        return False

    low = t.lower()

    sym_l = symbol.lower()
    base_l = base.lower()

    # Ambiguity guard: some bases are generic words (e.g. PUMP) and get lots of off-topic hits.
    # For those, require explicit futures symbol mention.
    ambiguous_bases = {"pump"}

    if base_l in ambiguous_bases:
        if sym_l not in low and (f"{base_l}/usdt" not in low) and (f"{base_l} usdt" not in low):
            return False
    else:
        # normal case: allow base mention or explicit symbol
        if sym_l not in low and base_l not in low and (f"${base_l}" not in low):
            return False

    # violent/off-topic
    if any(k in low for k in ["rpg", "rocket", "grenade", "shooting", "killed", "dead", "bomb"]):
        return False

    # reject obvious cross-token signal spam: too many $TICKER
    if len(re.findall(r"\$[A-Za-z0-9]{2,10}", t)) >= 6:
        return False

    # keep if looks like trading talk (levels / tp / sl / support / resistance)
    if re.search(r"\b(tp\d*|sl|stop|support|resistance|break|hold|bias|entry|exit)\b", low):
        return True

    # keep if includes numeric levels
    if re.search(r"\b0\.\d{3,}|\b\d+\.\d+", t):
        return True

    # keep short symbol-only chatter only if it mentions symbol and is short
    if len(t) <= 60:
        return True

    return False
    return False


def twitter_context_for_symbol(symbol: str, *, limit: int = 6) -> Dict[str, Any]:
    """Return {total, kept, snippets:[...]} for the given futures symbol."""

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"total": 0, "kept": 0, "snippets": []}

    base = sym.replace("USDT", "")
    q = f"{sym} OR ${base}"

    rows = _run_bird_search(q, n=30)
    total = len(rows)

    snippets: List[str] = []
    for r in rows:
        txt = (r.get("text") if isinstance(r, dict) else "") or ""
        txt = txt.replace("\n", " ").strip()
        if not _is_good_snippet(txt, symbol=sym, base=base):
            continue
        # compact
        txt = re.sub(r"https?://\S+", "", txt).strip()
        txt = re.sub(r"\s+", " ", txt).strip()
        snippets.append(txt[:180])
        if len(snippets) >= limit:
            break

    return {"total": total, "kept": len(snippets), "snippets": snippets}

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
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


_PROMO_PAT = re.compile(
    r"(join our telegram|vip telegram|dm to join|link in bio|join alpha|calls|signal active|\bvip\b|airdrop\b|giveaway|\bdaily alpha\b|\bjoin:\b)",
    re.IGNORECASE,
)

_BOTISH_PAT = re.compile(r"(#\w+\s*){6,}")

# Some tickers are highly ambiguous English words and create massive irrelevant recall.
# For these, require stronger anchors (e.g., $TICKER, pair symbol, or explicit trading context).
_DEFAULT_AMBIGUOUS_BASES = {
    "PUMP",
    "TIME",
    "PEACE",
    "HOPE",
    "LIFE",
    "LOVE",
}


def _ambiguous_bases() -> set[str]:
    import os

    raw = (os.environ.get("TWITTER_AMBIGUOUS_TICKERS") or "").strip()
    extra = {x.strip().upper() for x in raw.split(",") if x.strip()}
    return set(_DEFAULT_AMBIGUOUS_BASES) | extra


_CONTEXT_KW = [
    "usdt",
    "perp",
    "perps",
    "futures",
    "binance",
    "bybit",
    "okx",
    "hyperliquid",
    "funding",
    "oi",
    "open interest",
    "chart",
    "entry",
    "exit",
    "tp",
    "sl",
    "stop",
    "support",
    "resistance",
    "long",
    "short",
]


def _has_crypto_context(low: str) -> bool:
    return any(k in low for k in _CONTEXT_KW)


def _is_relevant(raw: str, *, aliases: List[str], base: str) -> bool:
    """Relevance gate for evidence gathering.

    - For normal tickers: accept if mentions base or $base or any alias.
    - For ambiguous tickers: require $base OR explicit alias OR (base as word + crypto context).
    """

    t = (raw or "").strip()
    if not t:
        return False
    # Strip URLs before relevance/context checks (URLs can accidentally match keywords like "tp").
    t2 = re.sub(r"https?://\S+", " ", t)
    low = re.sub(r"\s+", " ", t2).strip().lower()

    base_u = (base or "").upper().strip()
    base_l = base_u.lower()

    # Any explicit alias mention counts (with safeguards against substring false positives).
    amb = _ambiguous_bases()
    for a in aliases or []:
        al = (a or "").strip()
        if not al:
            continue
        al_u = al.upper().lstrip("$")
        # Skip bare ambiguous base aliases like "PUMP"; require $PUMP or pair alias.
        if al_u in amb and not al.strip().startswith("$"):
            continue
        # For ticker-like aliases, require safe matching.
        if re.fullmatch(r"\$?[A-Za-z0-9]{2,12}", al):
            tok = al.lower().lstrip("$")
            if al.startswith("$"):
                # Cashtag must appear literally, otherwise it matches generic words like "pump".
                if re.search(rf"\${re.escape(tok)}(?![a-z0-9_])", low):
                    return True
            else:
                if re.search(rf"\b{re.escape(tok)}\b", low):
                    return True
            continue
        if al.lower() in low:
            return True

    # No base available
    if not base_u:
        return True

    # Ambiguous tickers need stronger anchor.
    if base_u in _ambiguous_bases():
        # If a futures pair alias like XXXUSDT is provided, require either that explicit alias
        # or explicit derivatives context; otherwise generic "pump" chatter dominates.
        has_pair = any((a or "").strip().upper().endswith("USDT") for a in (aliases or []))
        if has_pair:
            if re.search(rf"\b{re.escape((base_l+'usdt'))}\b", low):
                return True
            # Allow $BASE only if derivatives context exists (avoid pump.fun memes)
            if re.search(rf"\${re.escape(base_l)}(?![a-z0-9_])", low) and any(k in low for k in ["usdt", "perp", "futures", "funding", "oi"]):
                return True
        else:
            if re.search(rf"\${re.escape(base_l)}(?![a-z0-9_])", low):
                return True

        # base appears as standalone token + crypto/derivatives context
        if re.search(rf"\b{re.escape(base_l)}\b", low) and _has_crypto_context(low):
            return True
        return False

    # Normal tickers: keep loose.
    return (base_l in low) or (f"${base_l}" in low)


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

    # Symbol relevance (keep relatively loose across all symbols).
    # Accept if it mentions the explicit futures symbol OR the base (plain or $base).
    if sym_l not in low and base_l not in low and (f"${base_l}" not in low):
        return False

    # violent/off-topic
    if any(k in low for k in ["rpg", "rocket", "grenade", "shooting", "killed", "dead", "bomb"]):
        return False

    # bot-like alert/broadcast templates (not trader opinions)
    if any(k in low for k in ["whale alert", "liquidation", "liquidated", "liq", "filled", "profit", "returns", "mcap", "market cap"]) or re.search(r"\bmc\b", low) or re.search(r"\b\d+(?:\.\d+)?x+\b", low, re.IGNORECASE):
        # allow only if it also contains explicit tp/sl/support/resistance type content
        if not re.search(r"\b(tp\d*|sl|stop|support|resistance|entry|exit)\b", low):
            return False

    # reject obvious cross-token signal spam: too many $TICKER
    if len(re.findall(r"\$[A-Za-z0-9]{2,10}", t)) >= 6:
        return False

    # keep if looks like trading talk (levels / tp / sl / support / resistance)
    if re.search(r"\b(tp\d*|sl|stop|support|resistance|break|hold|bias|entry|exit|long|short|buy|sell)\b", low):
        return True

    # keep if includes numeric levels
    if re.search(r"\b0\.\d{3,}|\b\d+\.\d+", t):
        return True

    # otherwise: allow some short chatter, but avoid ultra-short noise
    return len(t) <= 90


def _clean_snippet(t: str) -> str:
    t = (t or "").replace("\n", " ").strip()
    # drop urls
    t = re.sub(r"https?://\S+", "", t)
    # drop most emojis / symbols (keep $, letters, digits, basic punct)
    t = re.sub(r"[^\w\s\$\./%\-\+\,\;\:\(\)\[\]\#]", " ", t)
    # collapse spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _derive_base_from_aliases(aliases: List[str]) -> str:
    # Prefer futures pair aliases like XXXUSDT -> base XXX
    for a in aliases or []:
        s = (a or "").strip().lstrip("$")
        if s.upper().endswith("USDT") and len(s) > 4:
            return s.upper().replace("USDT", "")
    # Fall back to first ticker-like alias
    for a in aliases or []:
        s = (a or "").strip().lstrip("$")
        if s and re.fullmatch(r"[A-Z0-9]{2,10}", s):
            return s.upper()
    return ""


@dataclass
class TwitterQuerySpec:
    """Structured spec for consistent Twitter evidence collection."""

    topic: str
    aliases: List[str]
    intent: str = "catalyst"  # catalyst|reason|plan|sentiment|risk
    window_hours: int = 24
    max_rows: int = 120
    snippet_limit: int = 10


def _build_queries(spec: TwitterQuerySpec) -> List[str]:
    # X advanced search supports since/until dates, but bird search is cookie-scrape-like and
    # may not reliably support time filters. We therefore encode time intent via keywords.

    aliases = [a for a in (spec.aliases or []) if a]

    # Reduce recall for ambiguous tickers: drop the bare base (e.g., PUMP) and keep stronger anchors
    # like $PUMP or PUMPUSDT.
    base = _derive_base_from_aliases(aliases)
    if base and base.upper() in _ambiguous_bases():
        aliases = [a for a in aliases if a.strip().upper() != base.upper()]

    alias_expr = " OR ".join(aliases)
    time_hint = "today" if spec.window_hours <= 24 else "past week"

    intent = (spec.intent or "").lower().strip()
    if intent in ("reason", "why"):
        kws = ["why", "reason", "selloff", "dump", time_hint]
    elif intent in ("plan", "trade"):
        kws = ["entry", "tp", "sl", "support", "resistance", time_hint]
    elif intent in ("risk",):
        kws = ["risk", "bear", "rug", "unlock", "vesting", time_hint]
    elif intent in ("sentiment",):
        kws = ["bull", "bear", "long", "short", time_hint]
    else:  # catalyst
        kws = ["catalyst", "news", "update", "announcement", time_hint]

    q1 = f"({alias_expr}) ({' OR '.join(kws)})"
    q2 = f"{alias_expr} {spec.topic}".strip()
    # Keep a small set (avoid over-querying, which increases noise and runtime)
    return [q1, q2]


def twitter_evidence(spec: TwitterQuerySpec) -> Dict[str, Any]:
    """Standardized pipeline: search -> clean -> filter -> dedup.

    Returns:
      {
        total, kept, snippets,
        meta: {queries, intent, window_hours, dropped:{...}}
      }
    """

    dropped = {"promo": 0, "bot": 0, "irrelevant": 0, "dup": 0, "empty": 0}

    queries = _build_queries(spec)
    rows: List[Dict[str, Any]] = []
    for q in queries:
        rows.extend(_run_bird_search(q, n=60))
        if len(rows) >= spec.max_rows:
            break

    total = len(rows)

    # Derive base ticker from aliases (best-effort)
    base = _derive_base_from_aliases(spec.aliases)

    snippets: List[str] = []
    seen = set()

    for r in rows:
        raw = (r.get("text") if isinstance(r, dict) else "") or ""
        if not raw.strip():
            dropped["empty"] += 1
            continue

        if _PROMO_PAT.search(raw) or _BOTISH_PAT.search(raw):
            dropped["promo"] += 1
            continue

        # Relevance + spam filter.
        if base:
            if not _is_relevant(raw, aliases=spec.aliases, base=base):
                dropped["irrelevant"] += 1
                continue
            # Reuse existing strong filters (promo/bot/trader-ish heuristics)
            if not _is_good_snippet(raw, symbol=base, base=base):
                dropped["irrelevant"] += 1
                continue

        txt = _clean_snippet(raw)
        if not txt:
            dropped["empty"] += 1
            continue

        k = txt.lower()[:90]
        if k in seen:
            dropped["dup"] += 1
            continue
        seen.add(k)

        snippets.append(txt[:180])
        if len(snippets) >= spec.snippet_limit:
            break

    return {
        "total": total,
        "kept": len(snippets),
        "snippets": snippets,
        "meta": {
            "queries": queries,
            "intent": spec.intent,
            "window_hours": spec.window_hours,
            "dropped": dropped,
        },
    }


def twitter_context_for_symbol(symbol: str, *, limit: int = 6) -> Dict[str, Any]:
    """Backward-compatible helper for OI plans."""

    sym = (symbol or "").upper().strip()
    if not sym:
        return {"total": 0, "kept": 0, "snippets": []}

    base = sym.replace("USDT", "")
    # Drop bare base to avoid ambiguous recall (e.g., PUMP matches generic 'pump').
    spec = TwitterQuerySpec(topic=sym, aliases=[sym, f"${base}"], intent="plan", window_hours=24, snippet_limit=limit)
    out = twitter_evidence(spec)
    # keep return shape stable
    return {"total": out.get("total", 0), "kept": out.get("kept", 0), "snippets": out.get("snippets", [])}

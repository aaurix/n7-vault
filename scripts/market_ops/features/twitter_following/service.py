#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Twitter/X following timeline analysis (last 60 min)."""

from __future__ import annotations

import datetime as dt
import re
from typing import Any, Dict, List, Optional, Tuple

from scripts.market_data import get_shared_social_batcher
from ...config import SH_TZ, UTC
from ...embed_cluster import greedy_cluster
from ...shared.filters import extract_symbols_and_addrs
from ...llm_openai import embeddings, detect_twitter_following_events, summarize_twitter_following
from ...models import PipelineContext
from ...services.evidence_cleaner import _clean_evidence_snippet
from ...services.diagnostics import log_llm_failure
from ...services.diagnostics import measure


_RT_PREFIX_RE = re.compile(r"^RT @\w+:\s*", re.IGNORECASE)

_LIGHT_NOISE = {
    "gm",
    "gn",
    "gm gm",
    "good morning",
    "good night",
    "wagmi",
    "ngmi",
    "lfg",
}

_ALLOWED_SENTIMENTS = ("偏多", "偏空", "分歧", "中性")

_BULL_KWS = [
    "bull",
    "long",
    "buy",
    "pump",
    "moon",
    "看多",
    "做多",
    "上涨",
    "突破",
    "拉盘",
]

_BEAR_KWS = [
    "bear",
    "short",
    "sell",
    "dump",
    "rug",
    "看空",
    "做空",
    "下跌",
    "破位",
    "砸盘",
]

_NARRATIVE_PATTERNS: List[Dict[str, Any]] = [
    {"label": "突破/新高", "kws": ["breakout", "突破", "新高", "ath", "新高点", "突破位"]},
    {"label": "回调/走弱", "kws": ["回调", "下跌", "走弱", "砸盘", "dump", "selloff"]},
    {"label": "多头升温", "kws": ["bull", "long", "做多", "看多", "pump", "moon"]},
    {"label": "空头升温", "kws": ["bear", "short", "做空", "看空", "砸盘", "rug"]},
    {"label": "资金流入/热度升温", "kws": ["inflow", "资金流入", "热度", "volume", "成交放大", "买盘"]},
    {"label": "资金流出/热度降温", "kws": ["outflow", "资金流出", "降温", "抛压", "卖压"]},
]

_EVENT_PATTERNS: List[Dict[str, Any]] = [
    {"label": "上所/上架", "kws": ["上线", "上所", "上架", "list", "listing", "binance", "coinbase", "okx", "bybit"]},
    {"label": "解锁/释放", "kws": ["unlock", "解锁", "释放", "vesting"]},
    {"label": "黑客/安全", "kws": ["hack", "exploit", "漏洞", "被盗", "攻击", "黑客"]},
    {"label": "清算/爆仓", "kws": ["liquidation", "清算", "爆仓"]},
    {"label": "监管/诉讼", "kws": ["sec", "监管", "诉讼", "court", "delist", "下架"]},
    {"label": "融资/投资", "kws": ["融资", "投资", "funding", "raise", "round"]},
    {"label": "空投/激励", "kws": ["airdrop", "空投", "激励", "points", "积分"]},
    {"label": "回购/销毁", "kws": ["buyback", "回购", "销毁", "burn"]},
    {"label": "合作/集成", "kws": ["合作", "partner", "partnership", "integrate", "integration"]},
    {"label": "脱锚/稳定币", "kws": ["depeg", "脱锚", "peg", "稳定币"]},
]

_SYMBOL_RE = re.compile(r"\$[A-Za-z0-9]{2,10}")
_MAJOR_SYMS = {
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "XRP",
    "ADA",
    "DOGE",
    "AVAX",
    "OP",
    "ARB",
    "SUI",
    "SEI",
    "APT",
}
_MAJOR_RE = re.compile(r"\b(?:" + "|".join(sorted(_MAJOR_SYMS)) + r")\b", re.IGNORECASE)


def _guess_sentiment(snippets: List[str]) -> str:
    bull = 0
    bear = 0
    for s in snippets:
        low = s.lower()
        if any(k in low for k in _BULL_KWS):
            bull += 1
        if any(k in low for k in _BEAR_KWS):
            bear += 1
    if bull and bear:
        if bull >= bear * 1.5:
            return "偏多"
        if bear >= bull * 1.5:
            return "偏空"
        return "分歧"
    if bull:
        return "偏多"
    if bear:
        return "偏空"
    return "中性"


def _extract_symbol_hint(text: str) -> str:
    m = _SYMBOL_RE.search(text or "")
    if not m:
        return ""
    return m.group(0)[1:].upper()


def _extract_symbols(text: str, *, resolver: Optional[Any] = None) -> List[str]:
    syms: List[str] = []
    if resolver is not None:
        try:
            syms, _addrs = resolver.extract_symbols_and_addrs(text or "")
        except Exception:
            syms = []
    if not syms:
        syms, _addrs = extract_symbols_and_addrs(text or "")
    majors = [x.upper() for x in _MAJOR_RE.findall(text or "")]
    for sym in majors:
        if sym and sym not in syms:
            syms.append(sym)
    return syms


def _pick_symbol(text: str, *, resolver: Optional[Any] = None) -> str:
    syms = _extract_symbols(text, resolver=resolver)
    if syms:
        return str(syms[0])
    return _extract_symbol_hint(text)


def _event_label(text: str) -> str:
    low = (text or "").lower()
    for pat in _EVENT_PATTERNS:
        if any(k in low for k in pat["kws"]):
            return str(pat["label"])
    return ""


def _has_anchor(text: str, *, resolver: Optional[Any] = None) -> bool:
    return bool(_pick_symbol(text, resolver=resolver) or _event_label(text))


def _narrative_hint(text: str, *, resolver: Optional[Any] = None) -> str:
    low = (text or "").lower()
    sym = _pick_symbol(text, resolver=resolver)
    for pat in _NARRATIVE_PATTERNS:
        if any(k in low for k in pat["kws"]):
            label = str(pat["label"])
            return f"{sym}{label}" if sym else label
    return ""


def _detect_events_from_items(
    items: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    resolver: Optional[Any] = None,
) -> List[str]:
    scored: List[Tuple[int, int, str]] = []
    for idx, it in enumerate(items):
        text = str(it.get("text") or it.get("snippet") or "")
        label = _event_label(text)
        if not label:
            continue
        sym = _pick_symbol(text, resolver=resolver)
        ev = f"{sym}{label}" if sym else f"{label}相关讨论"
        score = int(it.get("_cluster_size") or 1)
        scored.append((score, idx, ev))
    out: List[str] = []
    for _score, _idx, ev in sorted(scored, key=lambda x: (-x[0], x[1])):
        if ev in out:
            continue
        out.append(ev)
        if len(out) >= max_items:
            break
    return out


def _pick_narratives(snippets: List[str], *, max_items: int = 3) -> List[str]:
    out: List[str] = []
    for s in snippets:
        s = str(s).strip().lstrip("- ")
        if not s:
            continue
        if len(s) > 50:
            s = s[:50]
        if s in out:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _extract_narratives_from_items(
    items: List[Dict[str, Any]],
    *,
    max_items: int = 3,
    resolver: Optional[Any] = None,
) -> List[str]:
    out: List[str] = []
    for it in items:
        text = str(it.get("text") or it.get("snippet") or "")
        hint = _narrative_hint(text, resolver=resolver)
        if not hint:
            continue
        if hint in out:
            continue
        out.append(hint)
        if len(out) >= max_items:
            break
    return out


def _normalize_list(val: Any, *, max_items: int = 3) -> List[str]:
    items: List[str] = []
    if isinstance(val, list):
        items = [str(x) for x in val]
    elif isinstance(val, str):
        items = [val]
    out: List[str] = []
    for it in items:
        s = str(it).strip().lstrip("- ")
        if not s:
            continue
        if len(s) > 80:
            s = s[:80]
        if s in out:
            continue
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def _normalize_sentiment(val: Any, *, fallback: str) -> str:
    s = str(val or "").strip()
    if not s:
        return fallback
    if any(tag in s for tag in _ALLOWED_SENTIMENTS):
        return s[:40]
    return fallback


def _fallback_summary(
    *,
    items: List[Dict[str, Any]],
    snippets: List[str],
    total: int,
    kept: int,
    clusters: int,
    metrics: Optional[Dict[str, Any]] = None,
    resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    rep_texts = [str(it.get("text") or it.get("snippet") or "") for it in items]
    rep_texts = [t for t in rep_texts if t]
    narratives = _extract_narratives_from_items(items, max_items=3, resolver=resolver)
    if not narratives:
        narratives = _pick_narratives(rep_texts or snippets, max_items=3)
    events = _detect_events_from_items(items, max_items=3, resolver=resolver)
    if not events:
        events = _detect_events_from_items(
            [{"text": s, "_cluster_size": 1} for s in (rep_texts or snippets)],
            max_items=3,
            resolver=resolver,
        )
    meta = {"total": total, "kept": kept, "clusters": clusters}
    if metrics:
        meta["metrics"] = metrics
    return {
        "narratives": narratives,
        "sentiment": _guess_sentiment(rep_texts or snippets),
        "events": events,
        "meta": meta,
    }


def _filter_anchor_items(items: List[str], *, resolver: Optional[Any] = None) -> List[str]:
    anchored = [it for it in items if _has_anchor(it, resolver=resolver)]
    return anchored or items


def _merge_lists(primary: List[str], fallback: List[str], *, max_items: int = 3) -> List[str]:
    out: List[str] = []
    for seq in (primary, fallback):
        for it in seq:
            s = str(it).strip().lstrip("- ")
            if not s:
                continue
            if s in out:
                continue
            out.append(s)
            if len(out) >= max_items:
                return out
    return out


def _norm_compare_text(text: str) -> str:
    t = re.sub(r"[\s\W_]+", "", str(text or "").lower())
    return t


def _sentiment_tag(val: str) -> str:
    s = str(val or "")
    for tag in _ALLOWED_SENTIMENTS:
        if tag in s:
            return tag
    return ""


def _compare_lists(base: List[str], other: List[str]) -> Dict[str, Any]:
    base_keys = {_norm_compare_text(x) for x in base if _norm_compare_text(x)}
    other_keys = {_norm_compare_text(x) for x in other if _norm_compare_text(x)}
    only_base = [x for x in base if _norm_compare_text(x) not in other_keys]
    only_other = [x for x in other if _norm_compare_text(x) not in base_keys]
    overlap = [x for x in base if _norm_compare_text(x) in other_keys]
    return {
        "only_base": only_base[:3],
        "only_other": only_other[:3],
        "overlap": overlap[:3],
        "base_count": len(base),
        "other_count": len(other),
    }


def _compare_summaries(fallback: Dict[str, Any], agent: Dict[str, Any]) -> Dict[str, Any]:
    base_n = _normalize_list(fallback.get("narratives"), max_items=6)
    base_e = _normalize_list(fallback.get("events"), max_items=6)
    agent_n = _normalize_list(agent.get("narratives"), max_items=6)
    agent_e = _normalize_list(agent.get("events"), max_items=6)
    base_s = str(fallback.get("sentiment") or "")
    agent_s = str(agent.get("sentiment") or "")
    return {
        "sentiment_base": base_s,
        "sentiment_agent": agent_s,
        "sentiment_match": _sentiment_tag(base_s) == _sentiment_tag(agent_s),
        "narratives": _compare_lists(base_n, agent_n),
        "events": _compare_lists(base_e, agent_e),
    }


def _merge_summary(
    *,
    fallback: Dict[str, Any],
    agent: Dict[str, Any],
    resolver: Optional[Any] = None,
) -> Dict[str, Any]:
    base_n = _normalize_list(fallback.get("narratives"), max_items=6)
    base_e = _normalize_list(fallback.get("events"), max_items=6)
    agent_n = _filter_anchor_items(_normalize_list(agent.get("narratives"), max_items=6), resolver=resolver)
    agent_e = _filter_anchor_items(_normalize_list(agent.get("events"), max_items=6), resolver=resolver)
    return {
        "narratives": _merge_lists(agent_n, base_n, max_items=3),
        "sentiment": _normalize_sentiment(agent.get("sentiment"), fallback=str(fallback.get("sentiment") or "中性")),
        "events": _merge_lists(agent_e, base_e, max_items=3),
        "meta": fallback.get("meta") or {},
    }


def _parse_bird_time(s: str) -> Optional[dt.datetime]:
    if not s:
        return None
    try:
        return dt.datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        pass
    try:
        ts = dt.datetime.fromisoformat(s)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return ts
    except Exception:
        return None


def _fetch_following_rows(*, hours: int, limit: int, now_sh: dt.datetime) -> List[Dict[str, Any]]:
    tries = [limit, max(80, limit // 2), 80, 60, 40]
    tweets: Optional[List[Dict[str, Any]]] = None
    last_err: Optional[Exception] = None
    social = get_shared_social_batcher()
    for nn in tries:
        try:
            tweets = social.bird_following(n=nn)
            break
        except Exception as e:
            last_err = e
            tweets = None
    if tweets is None:
        raise RuntimeError(f"bird_following_failed:{last_err}")

    cut = now_sh - dt.timedelta(hours=hours)
    rows: List[Dict[str, Any]] = []
    for t in tweets:
        created = _parse_bird_time(t.get("created_at") or t.get("createdAt") or t.get("time") or "")
        if not created:
            continue
        created_sh = created.astimezone(SH_TZ)
        if created_sh < cut:
            continue

        user = t.get("user") if isinstance(t.get("user"), dict) else {}
        handle = (user.get("screen_name") or user.get("username") or "").strip()
        text = (t.get("full_text") or t.get("text") or t.get("content") or "").strip()
        if not text:
            continue

        rows.append(
            {
                "createdAt": created_sh.isoformat(),
                "handle": handle,
                "text": text,
                "id": str(t.get("id") or t.get("tweet_id") or ""),
            }
        )

    return rows


def _clean_following_text(text: str) -> str:
    t = _RT_PREFIX_RE.sub("", text or "").strip()
    return _clean_evidence_snippet(t, max_len=160)


def _is_light_noise(text: str) -> bool:
    if not text:
        return True
    t = text.strip()
    if not t:
        return True
    if t.lower() in _LIGHT_NOISE:
        return True
    if re.fullmatch(r"[\W_]+", t):
        return True
    return False


def _prep_snippets(rows: List[Dict[str, Any]], *, limit: int = 140) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    out: List[Dict[str, str]] = []
    seen: set[str] = set()
    noise_dropped = 0
    exact_dupe_dropped = 0
    candidates = 0
    capped = 0

    for r in rows:
        text = _clean_following_text(r.get("text") or "")
        if not text or _is_light_noise(text):
            noise_dropped += 1
            continue

        candidates += 1
        handle = (r.get("handle") or "").strip()
        snippet = f"{handle} | {text}" if handle else text
        snippet = re.sub(r"\s+", " ", snippet).strip()
        key = text.lower()[:140]
        if key in seen:
            exact_dupe_dropped += 1
            continue
        seen.add(key)

        if len(out) < limit:
            out.append({"text": text, "snippet": snippet, "handle": handle})
        else:
            capped += 1

    metrics = {
        "noise_dropped": noise_dropped,
        "exact_dedupe_dropped": exact_dupe_dropped,
        "candidates": candidates,
        "capped": capped,
    }
    return out, metrics


def _semantic_dedupe_items(
    items: List[Dict[str, str]],
    *,
    ctx: PipelineContext,
    threshold: float = 0.92,
    embed_timeout: int = 18,
    allow_embeddings: bool = True,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    if not items or len(items) <= 1:
        return items, {"semantic_dedupe_dropped": 0}
    if not allow_embeddings:
        return items, {"semantic_dedupe_dropped": 0}
    if ctx.budget.over(reserve_s=45.0):
        ctx.errors.append("twitter_following_semantic_dedupe_skipped:budget")
        return items, {"semantic_dedupe_dropped": 0}
    try:
        vecs = embeddings(texts=[(it.get("text") or "")[:240] for it in items], timeout=embed_timeout)
        reps = greedy_cluster(items, vecs, max_clusters=len(items), threshold=threshold)
        reps = [it for it in reps if isinstance(it, dict)]
        dedupe_dropped = 0
        cleaned: List[Dict[str, str]] = []
        for it in reps:
            size = int(it.get("_cluster_size") or 1)
            if size > 1:
                dedupe_dropped += size - 1
            cleaned.append({k: v for k, v in it.items() if not str(k).startswith("_cluster")})
        return cleaned, {"semantic_dedupe_dropped": dedupe_dropped}
    except Exception as e:
        ctx.errors.append(f"twitter_following_semantic_dedupe_failed:{type(e).__name__}:{e}")
        return items, {"semantic_dedupe_dropped": 0}


def _rate(num: int, denom: int) -> float:
    if denom <= 0:
        return 0.0
    return round(num / denom, 3)


def _build_quality_metrics(
    *,
    total: int,
    kept: int,
    clusters: int,
    noise_dropped: int,
    exact_dedupe_dropped: int,
    semantic_dedupe_dropped: int,
    candidates: int,
    capped: int = 0,
) -> Dict[str, Any]:
    dedupe_dropped = int(exact_dedupe_dropped or 0) + int(semantic_dedupe_dropped or 0)
    return {
        "total": int(total),
        "kept": int(kept),
        "candidates": int(candidates),
        "noise_dropped": int(noise_dropped),
        "noise_drop_rate": _rate(int(noise_dropped), int(total)),
        "exact_dedupe_dropped": int(exact_dedupe_dropped),
        "semantic_dedupe_dropped": int(semantic_dedupe_dropped),
        "dedupe_dropped": dedupe_dropped,
        "dedupe_rate": _rate(dedupe_dropped, int(candidates)),
        "capped": int(capped),
        "clusters": int(clusters),
    }


def _cluster_params(total: int) -> Tuple[int, float]:
    if total <= 18:
        return max(1, min(total, 5)), 0.84
    if total <= 45:
        return 6, 0.82
    if total <= 90:
        return 7, 0.80
    if total <= 140:
        return 8, 0.79
    return 9, 0.78


def _coarse_cluster_by_symbol(
    items: List[Dict[str, Any]],
    *,
    max_clusters: int,
    resolver: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for idx, it in enumerate(items):
        text = str(it.get("text") or it.get("snippet") or "")
        sym = _pick_symbol(text, resolver=resolver)
        key = sym or f"__misc_{idx}"
        if sym:
            if key not in groups:
                order.append(key)
            groups.setdefault(key, []).append(it)
        else:
            order.append(key)
            groups[key] = [it]

    reps: List[Dict[str, Any]] = []
    for key in order:
        group = groups.get(key) or []
        if not group:
            continue
        rep = dict(group[0])
        rep["_cluster_size"] = len(group)
        members = [str(g.get("text") or g.get("snippet") or "")[:140] for g in group if g]
        if members:
            rep["_cluster_members"] = members[:3]
        reps.append(rep)

    reps.sort(key=lambda x: int(x.get("_cluster_size") or 1), reverse=True)
    return reps[:max_clusters]


def _merge_clusters_by_symbol(
    reps: List[Dict[str, Any]],
    *,
    max_clusters: int,
    resolver: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for idx, it in enumerate(reps):
        text = str(it.get("text") or it.get("snippet") or "")
        sym = _pick_symbol(text, resolver=resolver)
        key = sym or f"__misc_{idx}"
        if sym:
            if key not in groups:
                order.append(key)
            groups.setdefault(key, []).append(it)
        else:
            order.append(key)
            groups[key] = [it]

    merged: List[Dict[str, Any]] = []
    for key in order:
        group = groups.get(key) or []
        if not group:
            continue
        rep = dict(group[0])
        total = 0
        members: List[str] = []
        for it in group:
            total += int(it.get("_cluster_size") or 1)
            mem = it.get("_cluster_members") or []
            if isinstance(mem, list):
                for m in mem:
                    t = str(m).strip()
                    if t and t not in members:
                        members.append(t[:140])
                    if len(members) >= 3:
                        break
            if len(members) < 3:
                t = str(it.get("text") or it.get("snippet") or "").strip()
                if t and t not in members:
                    members.append(t[:140])
            if len(members) >= 3:
                break
        rep["_cluster_size"] = total
        if members:
            rep["_cluster_members"] = members[:3]
        merged.append(rep)

    merged.sort(key=lambda x: int(x.get("_cluster_size") or 1), reverse=True)
    return merged[:max_clusters]


def _cluster_snippets(
    items: List[Dict[str, str]],
    *,
    ctx: PipelineContext,
    max_clusters: int = 12,
    threshold: float = 0.82,
    embed_timeout: int = 26,
    allow_embeddings: bool = True,
) -> List[Dict[str, Any]]:
    if not items:
        return []
    if len(items) <= max_clusters:
        return _merge_clusters_by_symbol(list(items), max_clusters=max_clusters, resolver=ctx.resolver)
    if not allow_embeddings:
        return _coarse_cluster_by_symbol(items, max_clusters=max_clusters, resolver=ctx.resolver)
    if ctx.budget.over(reserve_s=45.0):
        ctx.errors.append("twitter_following_embed_skipped:budget")
        return _coarse_cluster_by_symbol(items, max_clusters=max_clusters, resolver=ctx.resolver)

    try:
        vecs = embeddings(texts=[(it.get("text") or "")[:240] for it in items], timeout=embed_timeout)
        reps = greedy_cluster(items, vecs, max_clusters=max_clusters, threshold=threshold)
        reps = [it for it in reps if isinstance(it, dict)]
        return _merge_clusters_by_symbol(reps, max_clusters=max_clusters, resolver=ctx.resolver)
    except Exception as e:
        ctx.errors.append(f"twitter_following_embed_failed:{type(e).__name__}:{e}")
        return _coarse_cluster_by_symbol(items, max_clusters=max_clusters, resolver=ctx.resolver)


def _build_llm_inputs(reps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for it in reps:
        if not isinstance(it, dict):
            continue
        text = str(it.get("text") or it.get("snippet") or "").strip()
        if not text:
            continue
        out.append({"text": text[:180], "count": int(it.get("_cluster_size") or 1)})
        if len(out) >= 120:
            break
    return out




def build_twitter_following_summary(
    ctx: PipelineContext,
    *,
    allow_llm: bool = True,
    hours: int = 1,
    tweet_limit: int = 160,
) -> None:
    done = measure(ctx.perf, "twitter_following")
    try:
        rows = _fetch_following_rows(hours=hours, limit=tweet_limit, now_sh=ctx.now_sh)
        items, prep_metrics = _prep_snippets(rows, limit=140)

        total = len(rows)
        allow_embeddings = bool(ctx.use_embeddings)
        items, semantic_metrics = _semantic_dedupe_items(
            items,
            ctx=ctx,
            threshold=0.92,
            embed_timeout=18,
            allow_embeddings=allow_embeddings,
        )
        snippets = [it.get("snippet") or it.get("text") or "" for it in items]
        kept = len(snippets)

        target_clusters, threshold = _cluster_params(len(items))
        reps = _cluster_snippets(
            items,
            ctx=ctx,
            max_clusters=target_clusters,
            threshold=threshold,
            embed_timeout=26,
            allow_embeddings=allow_embeddings,
        )
        rep_texts = [str(it.get("text") or it.get("snippet") or "").strip() for it in reps if it]
        rep_texts = [t for t in rep_texts if t]
        cluster_count = len(reps) if reps else 0

        metrics = _build_quality_metrics(
            total=total,
            kept=kept,
            clusters=cluster_count,
            noise_dropped=int(prep_metrics.get("noise_dropped") or 0),
            exact_dedupe_dropped=int(prep_metrics.get("exact_dedupe_dropped") or 0),
            semantic_dedupe_dropped=int(semantic_metrics.get("semantic_dedupe_dropped") or 0),
            candidates=int(prep_metrics.get("candidates") or 0),
            capped=int(prep_metrics.get("capped") or 0),
        )

        ctx.twitter_following = {
            "total": total,
            "kept": kept,
            "clusters": cluster_count,
            "metrics": metrics,
            "snippets": snippets,
            "clustered_snippets": [it.get("snippet") or it.get("text") for it in reps if it] if reps else [],
        }

        fallback_summary = _fallback_summary(
            items=reps,
            snippets=snippets,
            total=total,
            kept=kept,
            clusters=cluster_count,
            metrics=metrics,
            resolver=ctx.resolver,
        )
        summary = fallback_summary

        diagnostics: Dict[str, Any] = {}

        llm_budget_over = ctx.budget.over(reserve_s=50.0)
        llm_summary_allowed = bool(allow_llm and ctx.use_llm and rep_texts and (not llm_budget_over))

        if allow_llm and ctx.use_llm and rep_texts and (not llm_summary_allowed):
            if not ctx.budget.over(reserve_s=40.0):
                try:
                    llm_inputs = _build_llm_inputs(reps)
                    out = detect_twitter_following_events(twitter_snippets=llm_inputs or rep_texts)
                    if isinstance(out, dict):
                        llm_events = _normalize_list(out.get("events"), max_items=3)
                        if llm_events:
                            fallback_summary["events"] = _merge_lists(
                                llm_events,
                                _normalize_list(fallback_summary.get("events"), max_items=3),
                                max_items=3,
                            )
                            diagnostics["llm_events"] = llm_events
                    else:
                        log_llm_failure(ctx, "twitter_following_llm_events_parse_failed", raw=str(out))
                except Exception as e:
                    log_llm_failure(ctx, "twitter_following_llm_events_failed", exc=e)

        if llm_summary_allowed:
            try:
                llm_inputs = _build_llm_inputs(reps)
                out = summarize_twitter_following(twitter_snippets=llm_inputs or rep_texts)
                if isinstance(out, dict):
                    agent_summary = {
                        "narratives": _normalize_list(out.get("narratives"), max_items=3),
                        "sentiment": _normalize_sentiment(out.get("sentiment"), fallback=fallback_summary["sentiment"]),
                        "events": _normalize_list(out.get("events"), max_items=3),
                        "meta": fallback_summary.get("meta") or {},
                    }
                    summary = _merge_summary(fallback=fallback_summary, agent=agent_summary, resolver=ctx.resolver)
                    diagnostics.update(
                        {
                            "fallback_summary": fallback_summary,
                            "agent_summary": agent_summary,
                            "compare": _compare_summaries(fallback_summary, agent_summary),
                        }
                    )
                else:
                    log_llm_failure(ctx, "twitter_following_llm_parse_failed", raw=str(out))
            except Exception as e:
                log_llm_failure(ctx, "twitter_following_llm_failed", exc=e)

        if diagnostics:
            ctx.twitter_following["diagnostics"] = diagnostics
        ctx.twitter_following_summary = summary
    except Exception as e:
        ctx.errors.append(f"twitter_following_failed:{type(e).__name__}:{e}")
        metrics = _build_quality_metrics(
            total=0,
            kept=0,
            clusters=0,
            noise_dropped=0,
            exact_dedupe_dropped=0,
            semantic_dedupe_dropped=0,
            candidates=0,
            capped=0,
        )
        ctx.twitter_following = {
            "total": 0,
            "kept": 0,
            "clusters": 0,
            "metrics": metrics,
            "snippets": [],
            "clustered_snippets": [],
        }
        ctx.twitter_following_summary = {
            "narratives": [],
            "sentiment": "中性",
            "events": [],
            "meta": {"total": 0, "kept": 0, "clusters": 0, "metrics": metrics},
        }
    done()


def self_check_twitter_following() -> str:
    class _DummyResolver:
        def extract_symbols_and_addrs(self, text: str, require_sol_digit: bool = False):
            return extract_symbols_and_addrs(text)

    class _DummyBudget:
        def over(self, reserve_s: float = 0.0) -> bool:
            return False

    class _DummyCtx:
        resolver = _DummyResolver()
        budget = _DummyBudget()
        errors: List[str] = []

    sample_rows = [
        {"handle": "alpha", "text": "BTC 突破关键阻力，考虑做多", "createdAt": "2025-01-01T00:00:00+08:00"},
        {"handle": "beta", "text": "SOL 遇阻回落，短线偏空", "createdAt": "2025-01-01T00:02:00+08:00"},
        {"handle": "gamma", "text": "ETH 上所传闻暂无证实", "createdAt": "2025-01-01T00:03:00+08:00"},
        {"handle": "delta", "text": "OP 解锁临近，谨慎", "createdAt": "2025-01-01T00:04:00+08:00"},
    ]
    items, prep_metrics = _prep_snippets(sample_rows, limit=10)
    items, semantic_metrics = _semantic_dedupe_items(
        items,
        ctx=_DummyCtx(),
        threshold=0.92,
        embed_timeout=10,
        allow_embeddings=False,
    )
    snippets = [it.get("text") or it.get("snippet") or "" for it in items]
    reps = _cluster_snippets(items, ctx=_DummyCtx(), max_clusters=4, threshold=0.8, allow_embeddings=False)
    metrics = _build_quality_metrics(
        total=len(sample_rows),
        kept=len(snippets),
        clusters=len(reps),
        noise_dropped=int(prep_metrics.get("noise_dropped") or 0),
        exact_dedupe_dropped=int(prep_metrics.get("exact_dedupe_dropped") or 0),
        semantic_dedupe_dropped=int(semantic_metrics.get("semantic_dedupe_dropped") or 0),
        candidates=int(prep_metrics.get("candidates") or 0),
        capped=int(prep_metrics.get("capped") or 0),
    )
    summary = _fallback_summary(
        items=reps,
        snippets=snippets,
        total=len(sample_rows),
        kept=len(snippets),
        clusters=len(reps),
        metrics=metrics,
        resolver=_DummyCtx().resolver,
    )
    meta = summary.get("meta") or {}
    if not isinstance(meta.get("metrics"), dict):
        return "self_check_twitter_following:fail:metrics_missing"

    if not snippets:
        return "self_check_twitter_following:fail:empty_snippets"
    if len(reps) > 4:
        return "self_check_twitter_following:fail:cluster_limit"
    if summary.get("sentiment") not in _ALLOWED_SENTIMENTS:
        return "self_check_twitter_following:fail:bad_sentiment"
    if not summary.get("events"):
        return "self_check_twitter_following:fail:events_empty"
    return "self_check_twitter_following:ok"

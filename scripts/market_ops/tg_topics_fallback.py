#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic Telegram topics summarizer (no chat LLM).

Uses clustering + keyword/entity extraction to synthesize narrative items.
Embeddings are optional: if unavailable or disallowed, it falls back to lexical clustering.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from .embed_cluster import cosine
from .shared.filters import stance_from_texts
from .llm_openai import embeddings
from .services.entity_resolver import EntityResolver, get_shared_entity_resolver
from .services.tg_preprocess import (
    clean_tg_text,
    extract_event_words,
    filter_tg_topic_texts,
    postfilter_tg_topic_item,
    score_tg_cluster,
)


_LATIN_RE = re.compile(r"[a-z][a-z0-9_\-]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_NUMERIC_RE = re.compile(r"\d+(?:[\.,]\d+)?\s*(?:[kKmMwW]|万|亿|M|B|%)?")

_STOPWORDS = {
    # zh
    "大家",
    "市场",
    "项目",
    "代币",
    "价格",
    "走势",
    "交易",
    "关注",
    "消息",
    "今天",
    "现在",
    "小时",
    "社区",
    "感觉",
    "可能",
    "这个",
    "那个",
    "还是",
    "已经",
    "继续",
    "没有",
    "就是",
    "出来",
    "因为",
    "而且",
    "应该",
    "需要",
    "看到",
    "一些",
    "有人",
    "用户",
    "群友",
    "拉盘",
    "出货",
    "庄",
    "交易所",
    "资金",
    "上涨",
    "下跌",
    "回调",
    "新高",
    "新低",
    "趋势",
    "情绪",
    "逻辑",
    # en
    "token",
    "coin",
    "project",
    "market",
    "price",
    "volume",
    "chart",
    "group",
    "telegram",
    "tg",
    "alpha",
    "pump",
    "dump",
    "moon",
    "signal",
    "entry",
    "exit",
    "long",
    "short",
}


def _dedup_texts(texts: List[str], *, key_len: int = 120, limit: int = 240) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for t in texts:
        t = (t or "").strip()
        if not t:
            continue
        k = t.lower()[:key_len]
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _tokenize_keywords(text: str) -> List[str]:
    t = clean_tg_text(text)
    if not t:
        return []
    t_lower = t.lower()

    out: List[str] = []
    for w in _LATIN_RE.findall(t_lower):
        if w in _STOPWORDS:
            continue
        if len(w) < 3:
            continue
        out.append(w)

    for w in _CJK_RE.findall(t):
        w = w.strip()
        if not w or w in _STOPWORDS:
            continue
        if len(w) <= 6:
            out.append(w)
        else:
            # add short bigrams for long CJK chunks
            for i in range(0, min(len(w) - 1, 5)):
                out.append(w[i : i + 2])

    out2: List[str] = []
    seen: set[str] = set()
    for w in out:
        if not w or w in _STOPWORDS:
            continue
        if w not in seen:
            seen.add(w)
            out2.append(w)
    return out2


def _extract_keywords(texts: List[str], *, center: str, limit: int = 6) -> List[str]:
    counts: Dict[str, int] = {}
    for t in texts:
        toks = set(_tokenize_keywords(t))
        for w in toks:
            counts[w] = counts.get(w, 0) + 1

    # Boost center tokens (representative text)
    for w in _tokenize_keywords(center):
        counts[w] = counts.get(w, 0) + 1

    ranked = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [w for w, _c in ranked[:limit]]


def _extract_entities(texts: List[str], *, resolver: EntityResolver) -> List[str]:
    counts: Dict[str, int] = {}
    for t in texts:
        syms, _addrs = resolver.resolve_symbols_from_text(t)
        for s in syms:
            s = str(s).upper().strip().lstrip("$")
            if not s:
                continue
            counts[s] = counts.get(s, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (kv[1], len(kv[0])), reverse=True)
    return [s for s, _c in ranked[:6]]


def _extract_numeric(texts: List[str]) -> str:
    for t in texts:
        m = _NUMERIC_RE.search(t)
        if m:
            return m.group(0)
    return ""


def _compose_one_liner(anchor: str, events: List[str], keywords: List[str]) -> str:
    kw = "/".join(keywords[:2]) if keywords else ""
    if anchor and events:
        return f"{anchor} {events[0]}话题升温"
    if anchor and kw:
        return f"{anchor} 讨论集中：{kw}"
    if anchor:
        return f"{anchor} 讨论升温"
    if events and kw:
        return f"{events[0]} 话题升温：{kw}"
    if events:
        return f"{events[0]} 话题升温"
    if kw:
        return f"{kw} 成为讨论焦点"
    return "热点话题讨论升温"


def _compose_triggers(events: List[str], keywords: List[str], *, limit: int = 6) -> str:
    out: List[str] = []
    for w in events:
        if w and w not in out:
            out.append(w)
    for w in keywords:
        if w and w not in out:
            out.append(w)
    return "；".join(out[:limit])


def _cluster_key(text: str, *, resolver: EntityResolver) -> Tuple[str, str]:
    syms, _addrs = resolver.resolve_symbols_from_text(text, max_addrs=1)
    if syms:
        sym = str(syms[0]).upper().strip().lstrip("$")
        if sym:
            return f"sym:{sym}", sym

    events = extract_event_words(text)
    if events:
        ev = str(events[0]).strip()
        return f"event:{ev.lower()}", ev

    kw = _tokenize_keywords(text)[:1]
    if kw:
        return f"kw:{kw[0]}", kw[0]
    return "misc", ""


def _cluster_with_embeddings(
    texts: List[str],
    *,
    max_clusters: int,
    threshold: float,
    embed_timeout: int,
) -> List[Dict[str, Any]]:
    vecs = embeddings(texts=[t[:240] for t in texts], timeout=embed_timeout)
    clusters: List[Dict[str, Any]] = []
    centroids: List[List[float]] = []

    for text, vec in zip(texts, vecs):
        if not vec:
            continue
        best_i = -1
        best_sim = -1.0
        for i, c in enumerate(centroids):
            s = cosine(vec, c)
            if s > best_sim:
                best_sim = s
                best_i = i
        if best_i >= 0 and best_sim >= threshold:
            cl = clusters[best_i]
            size = int(cl.get("_cluster_size") or 1)
            cl["_cluster_size"] = size + 1
            cl["_texts"].append(text)
            # update centroid incrementally
            c = centroids[best_i]
            new_size = size + 1
            centroids[best_i] = [(c[i] * size + vec[i]) / new_size for i in range(len(c))]
            continue

        if len(clusters) >= max_clusters:
            continue
        clusters.append({"text": text, "_cluster_size": 1, "_texts": [text], "_best_score": 0.0})
        centroids.append(vec)

    return clusters


def _cluster_lexical(
    texts: List[str],
    *,
    resolver: EntityResolver,
    max_clusters: int,
) -> List[Dict[str, Any]]:
    clusters: Dict[str, Dict[str, Any]] = {}
    for text in texts:
        key, _anchor = _cluster_key(text, resolver=resolver)
        if key not in clusters:
            if len(clusters) >= max_clusters:
                continue
            clusters[key] = {"text": text, "_cluster_size": 0, "_texts": [], "_best_score": 0.0}
        cl = clusters[key]
        cl["_cluster_size"] = int(cl.get("_cluster_size") or 0) + 1
        cl["_texts"].append(text)
        score = score_tg_cluster({"text": text, "_cluster_size": cl["_cluster_size"]}, resolver=resolver)
        if score > float(cl.get("_best_score") or 0.0):
            cl["text"] = text
            cl["_best_score"] = score
    return list(clusters.values())


def _build_topic_from_cluster(
    cluster: Dict[str, Any],
    *,
    resolver: EntityResolver,
) -> Optional[Dict[str, Any]]:
    texts = [str(x) for x in (cluster.get("_texts") or []) if str(x).strip()]
    if not texts:
        return None
    center = str(cluster.get("text") or texts[0]).strip()

    entities = _extract_entities(texts, resolver=resolver)
    events: List[str] = []
    for t in texts:
        events.extend(extract_event_words(t))
    # unique events, preserve order
    ev_seen: set[str] = set()
    ev2: List[str] = []
    for e in events:
        key = e.lower()
        if not key or key in ev_seen:
            continue
        ev_seen.add(key)
        ev2.append(e)
    events = ev2

    keywords = _extract_keywords(texts, center=center, limit=6)
    anchor = entities[0] if entities else (events[0] if events else (keywords[0] if keywords else ""))

    one = _compose_one_liner(anchor, events, keywords)
    tri = _compose_triggers(events, keywords)
    sentiment = stance_from_texts(texts)
    item = {
        "one_liner": one[:72],
        "sentiment": sentiment,
        "triggers": tri,
        "related_assets": entities,
        "_inferred": True,
    }

    if not postfilter_tg_topic_item(item, resolver=resolver):
        # Try to inject an event or numeric anchor
        if events:
            item["one_liner"] = f"{events[0]} 话题升温"
        else:
            num = _extract_numeric(texts)
            if num:
                item["one_liner"] = f"{num} 相关讨论升温"
        if not postfilter_tg_topic_item(item, resolver=resolver):
            return None

    return item


def _fallback_by_symbols(texts: List[str], *, resolver: EntityResolver, limit: int) -> List[Dict[str, Any]]:
    sym_hits: Dict[str, int] = {}
    sym_samples: Dict[str, List[str]] = {}

    for t in texts[:400]:
        syms, _addrs = resolver.extract_symbols_and_addrs(t)
        for s in syms[:3]:
            sym_hits[s] = sym_hits.get(s, 0) + 1
            sym_samples.setdefault(s, []).append(t)

    items: List[Dict[str, Any]] = []
    for sym, cnt in sorted(sym_hits.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]:
        samples = sym_samples.get(sym, [])[:30]
        stance = stance_from_texts(samples)
        one = f"{sym} 讨论升温（提及{cnt}）"
        tri = "关注关键位/催化/风险"
        items.append(
            {
                "one_liner": one,
                "sentiment": stance,
                "triggers": tri,
                "related_assets": [sym],
                "_inferred": True,
            }
        )

    return items[:limit]


def tg_topics_fallback(
    texts: List[str],
    *,
    limit: int = 5,
    resolver: Optional[EntityResolver] = None,
    use_embeddings: bool = True,
    embed_timeout: int = 24,
    max_clusters: int = 12,
    threshold: float = 0.82,
    errors: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Deterministic TG topic extraction fallback (no chat LLM)."""

    resolver = resolver or get_shared_entity_resolver()
    if errors is None:
        errors = []

    filtered = filter_tg_topic_texts(texts, resolver=resolver, limit=400)
    filtered = _dedup_texts(filtered, limit=240)
    if not filtered:
        return []

    clusters: List[Dict[str, Any]] = []
    if use_embeddings and len(filtered) > 6:
        try:
            clusters = _cluster_with_embeddings(
                filtered,
                max_clusters=max_clusters,
                threshold=threshold,
                embed_timeout=embed_timeout,
            )
        except Exception as e:
            errors.append(f"tg_topics_fallback_embed_failed:{type(e).__name__}:{e}")
            clusters = []

    if not clusters:
        clusters = _cluster_lexical(filtered, resolver=resolver, max_clusters=max_clusters)

    # rank clusters
    for cl in clusters:
        cl["_cluster_score"] = score_tg_cluster(
            {"text": cl.get("text"), "_cluster_size": cl.get("_cluster_size")}, resolver=resolver
        )
    clusters = sorted(
        clusters,
        key=lambda x: (float(x.get("_cluster_score") or 0.0), int(x.get("_cluster_size") or 0)),
        reverse=True,
    )

    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for cl in clusters:
        item = _build_topic_from_cluster(cl, resolver=resolver)
        if not item:
            continue
        k = str(item.get("one_liner") or "").lower()[:40]
        if k in seen:
            continue
        seen.add(k)
        items.append(item)
        if len(items) >= limit:
            break

    if items:
        return items[:limit]

    return _fallback_by_symbols(filtered, resolver=resolver, limit=limit)


def self_check_tg_topics_fallback() -> Dict[str, Any]:
    samples = [
        "$ABC 上所传闻升温，社区讨论明显",
        "解锁500万 $XYZ，短线抛压值得关注",
        "0x1234567890abcdef1234567890abcdef12345678 快速拉盘",
        "某项目空投细节曝光，热度上来",
        "价格突破区间，成交量放大",
    ]

    items = tg_topics_fallback(samples, limit=3, use_embeddings=False)
    ok = bool(items) and all(isinstance(it, dict) and it.get("one_liner") for it in items)
    return {"ok": ok, "items": items}


__all__ = ["tg_topics_fallback", "self_check_tg_topics_fallback"]

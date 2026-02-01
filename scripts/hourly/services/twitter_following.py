#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Twitter/X following timeline analysis (last 60 min)."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from typing import Any, Dict, List, Optional

from ..config import SH_TZ, UTC
from ..llm_openai import summarize_twitter_following
from ..models import PipelineContext
from .evidence_cleaner import _clean_evidence_snippet
from .llm_failures import _log_llm_failure
from .pipeline_timing import measure


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


def _run_bird_home_following(n: int, *, timeout_s: int = 35) -> str:
    cmd = ["bird", "home", "--following", "-n", str(n), "--json", "--quote-depth", "1"]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout_s)
    if p.returncode != 0 and not (p.stdout or "").strip():
        raise RuntimeError(f"bird home failed: {p.stderr}")
    return p.stdout or ""


def _salvage_json(raw: str) -> Any:
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty json")
    start = min([i for i in [s.find("{"), s.find("[")] if i != -1] or [0])
    tail = max(s.rfind("}"), s.rfind("]"))
    if tail != -1:
        s = s[start : tail + 1]
    else:
        s = s[start:]
    return json.loads(s)


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


def _extract_list(obj: Any) -> List[Dict[str, Any]]:
    if isinstance(obj, dict):
        for k in ["tweets", "data", "items", "results", "timeline", "entries"]:
            if k in obj and isinstance(obj[k], list):
                return [x for x in obj[k] if isinstance(x, dict)]
    if isinstance(obj, list):
        return [x for x in obj if isinstance(x, dict)]
    return []


def _fetch_following_rows(*, hours: int, limit: int, now_sh: dt.datetime) -> List[Dict[str, Any]]:
    tries = [limit, max(80, limit // 2), 80, 60, 40]
    obj = None
    last_err: Optional[Exception] = None
    for nn in tries:
        raw = _run_bird_home_following(nn)
        try:
            obj = json.loads(raw)
            break
        except Exception:
            try:
                obj = _salvage_json(raw)
                break
            except Exception as e:
                last_err = e
                obj = None
    if obj is None:
        raise RuntimeError(f"Failed to parse bird JSON (last error: {last_err})")

    tweets = _extract_list(obj)

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
    return _clean_evidence_snippet(text, max_len=160)


def _prep_snippets(rows: List[Dict[str, Any]], *, limit: int = 120) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for r in rows:
        text = _clean_following_text(r.get("text") or "")
        if not text:
            continue
        handle = (r.get("handle") or "").strip()
        snippet = f"{handle} | {text}" if handle else text
        snippet = re.sub(r"\s+", " ", snippet).strip()
        k = snippet.lower()[:120]
        if k in seen:
            continue
        seen.add(k)
        out.append(snippet)
        if len(out) >= limit:
            break
    return out


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


def _fallback_summary(snippets: List[str], *, total: int, kept: int) -> Dict[str, Any]:
    return {
        "narratives": [],
        "sentiment": _guess_sentiment(snippets),
        "events": [],
        "meta": {"total": total, "kept": kept},
    }


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
        snippets = _prep_snippets(rows, limit=120)

        total = len(rows)
        kept = len(snippets)
        ctx.twitter_following = {
            "total": total,
            "kept": kept,
            "snippets": snippets,
        }

        summary = _fallback_summary(snippets, total=total, kept=kept)

        llm_budget_over = ctx.budget.over(reserve_s=50.0)
        if allow_llm and ctx.use_llm and snippets and (not llm_budget_over):
            try:
                out = summarize_twitter_following(twitter_snippets=snippets)
                if isinstance(out, dict):
                    summary = {
                        "narratives": _normalize_list(out.get("narratives"), max_items=3),
                        "sentiment": _normalize_sentiment(out.get("sentiment"), fallback=summary["sentiment"]),
                        "events": _normalize_list(out.get("events"), max_items=3),
                        "meta": {"total": total, "kept": kept},
                    }
                else:
                    _log_llm_failure(ctx, "twitter_following_llm_parse_failed", raw=str(out))
            except Exception as e:
                _log_llm_failure(ctx, "twitter_following_llm_failed", exc=e)

        ctx.twitter_following_summary = summary
    except Exception as e:
        ctx.errors.append(f"twitter_following_failed:{type(e).__name__}:{e}")
        ctx.twitter_following = {"total": 0, "kept": 0, "snippets": []}
        ctx.twitter_following_summary = {
            "narratives": [],
            "sentiment": "中性",
            "events": [],
            "meta": {"total": 0, "kept": 0},
        }
    done()


def self_check_twitter_following() -> str:
    sample_rows = [
        {"handle": "alpha", "text": "BTC 突破关键阻力，考虑做多", "createdAt": "2025-01-01T00:00:00+08:00"},
        {"handle": "beta", "text": "SOL 遇阻回落，短线偏空", "createdAt": "2025-01-01T00:02:00+08:00"},
        {"handle": "gamma", "text": "ETH 上所传闻暂无证实", "createdAt": "2025-01-01T00:03:00+08:00"},
    ]
    snippets = _prep_snippets(sample_rows, limit=10)
    summary = _fallback_summary(snippets, total=len(sample_rows), kept=len(snippets))
    if not snippets:
        return "self_check_twitter_following:fail:empty_snippets"
    if summary.get("sentiment") not in _ALLOWED_SENTIMENTS:
        return "self_check_twitter_following:fail:bad_sentiment"
    return "self_check_twitter_following:ok"

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OpenAI API helper for LLM-based summarization.

This module is ONLY used by the hourly summarization pipeline when explicitly enabled.
It uses OPENAI_API_KEY (env) or reads ~/.clawdbot/.env as a fallback.

We keep calls minimal:
- 1 telegram narratives summary (top 5)
- 1 twitter topics summary (top 5)
- 1 OI+Kline trading plan summary (top 3)
- optional: 1 token-thread batch summary (top 3, only on strong hours)
"""

from __future__ import annotations

import json
import os
import re
import hashlib
import urllib.request as urlreq
from typing import Any, Dict, List, Optional, Sequence, Tuple

from repo_paths import memory_path


def _load_env_key(name: str) -> Optional[str]:
    k = os.environ.get(name)
    if k:
        return k.strip()

    # Fallback for daemon-less local runs
    env_path = os.path.expanduser("~/.clawdbot/.env")
    try:
        if os.path.exists(env_path):
            raw = open(env_path, "r", encoding="utf-8").read()
            m = re.search(rf"^{re.escape(name)}\s*=\s*(.+)\s*$", raw, re.MULTILINE)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    except Exception:
        pass

    return None


def load_openai_api_key() -> Optional[str]:
    """OpenAI key (for OpenAI endpoints, embeddings, etc)."""

    return _load_env_key("OPENAI_API_KEY")


def load_openrouter_api_key() -> Optional[str]:
    """OpenRouter key (OpenAI-compatible endpoint)."""

    return _load_env_key("OPENROUTER_API_KEY")


def load_chat_api_key() -> Optional[str]:
    """Key resolver for *chat* calls.

    Preference:
    - If OPENAI_API_KEY exists: use OpenAI.
    - Else if OPENROUTER_API_KEY exists: use OpenRouter.
    """

    return load_openai_api_key() or load_openrouter_api_key()


def _sha1(s: str) -> str:
    return hashlib.sha1((s or "").encode("utf-8")).hexdigest()


def _default_embed_cache_path() -> str:
    return str(memory_path("embeddings_cache.json"))


_EMBED_CACHE: Optional[Dict[str, List[float]]] = None
_EMBED_CACHE_PATH: Optional[str] = None
_EMBED_DIRTY: bool = False


def _load_embed_cache(path: str) -> Dict[str, List[float]]:
    try:
        if os.path.exists(path):
            data = json.loads(open(path, "r", encoding="utf-8").read())
            if isinstance(data, dict):
                out: Dict[str, List[float]] = {}
                for k, v in data.items():
                    if isinstance(k, str) and isinstance(v, list):
                        out[k] = [float(x) for x in v]
                return out
    except Exception:
        pass
    return {}


def _save_embed_cache(path: str, cache: Dict[str, List[float]], *, max_items: int = 5000) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # naive prune: keep most-recent by insertion order is not tracked; just cap by arbitrary slice
        if len(cache) > max_items:
            keys = list(cache.keys())[-max_items:]
            cache = {k: cache[k] for k in keys}
        open(path, "w", encoding="utf-8").write(json.dumps(cache, ensure_ascii=False))
    except Exception:
        pass


def flush_embeddings_cache() -> None:
    """Best-effort flush to disk (optional)."""
    global _EMBED_DIRTY
    if not _EMBED_DIRTY:
        return
    if _EMBED_CACHE is None or not _EMBED_CACHE_PATH:
        return
    _save_embed_cache(_EMBED_CACHE_PATH, _EMBED_CACHE)
    _EMBED_DIRTY = False


def embeddings(
    *,
    texts: Sequence[str],
    model: str = "text-embedding-3-small",
    timeout: int = 30,
    cache_path: Optional[str] = None,
) -> List[List[float]]:
    """Embedding with disk cache keyed by sha1(text).

    Cache is best-effort. On any cache error, falls back to direct API call.
    Uses an in-process singleton cache to avoid reloading the JSON file multiple times per run.
    """

    global _EMBED_CACHE, _EMBED_CACHE_PATH, _EMBED_DIRTY

    api_key = load_openai_api_key()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not found")

    cache_path = cache_path or _default_embed_cache_path()
    if _EMBED_CACHE is None or _EMBED_CACHE_PATH != cache_path:
        _EMBED_CACHE_PATH = cache_path
        _EMBED_CACHE = _load_embed_cache(cache_path)
        _EMBED_DIRTY = False

    cache = _EMBED_CACHE or {}

    # Resolve cached vectors
    keys = [_sha1(t) for t in texts]
    out: List[Optional[List[float]]] = [None] * len(keys)
    missing_idx: List[int] = []
    missing_texts: List[str] = []

    for i, k in enumerate(keys):
        if k in cache:
            out[i] = cache[k]
        else:
            missing_idx.append(i)
            missing_texts.append(texts[i])

    # Fetch only missing
    if missing_texts:
        payload = {"model": model, "input": list(missing_texts)}

        req = urlreq.Request(
            "https://api.openai.com/v1/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "clawdbot-hourly/1.0",
            },
            method="POST",
        )

        with urlreq.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        vecs: List[List[float]] = []
        for row in (data.get("data") or []):
            v = row.get("embedding")
            if isinstance(v, list):
                vecs.append([float(x) for x in v])

        # Fill outputs + write-through cache
        for j, i in enumerate(missing_idx):
            if j < len(vecs):
                out[i] = vecs[j]
                cache[keys[i]] = vecs[j]
                _EMBED_DIRTY = True

        # write-through (best-effort)
        flush_embeddings_cache()

    # Persist the singleton back
    _EMBED_CACHE = cache

    return [v or [] for v in out]


def _resolve_chat_endpoint(model: str) -> Tuple[str, str, str]:
    """Return (base_url, api_key, model_id) for chat.completions.

    Policy:
    - Script chat calls ALWAYS go through OpenRouter (stable single provider),
      regardless of OPENAI_API_KEY.
    - Embeddings remain on OpenAI (see embeddings()).

    You can set OPENROUTER_CHAT_MODEL to override the default model.
    """

    model = (model or "").strip()

    k_or = load_openrouter_api_key()
    if not k_or:
        raise RuntimeError("OPENROUTER_API_KEY not found")

    def _normalize_openrouter_model(m: str) -> str:
        m = (m or "").strip()
        # In OpenClaw/Clawdbot configs we often prefix with "openrouter/".
        # OpenRouter's OpenAI-compatible API expects provider/model (no openrouter/ prefix).
        if m.startswith("openrouter/"):
            return m[len("openrouter/") :]
        return m

    # If caller already passes an OpenRouter model ref, normalize it.
    if model.startswith("openrouter/"):
        return "https://openrouter.ai/api/v1", k_or, _normalize_openrouter_model(model)

    # Otherwise, force to configured OpenRouter model.
    forced_model = os.environ.get("OPENROUTER_CHAT_MODEL") or "deepseek/deepseek-v3.2"
    return "https://openrouter.ai/api/v1", k_or, _normalize_openrouter_model(forced_model)


def chat_json(
    *,
    system: str,
    user: str,
    model: str = "openai-codex/gpt-5.2",
    temperature: float = 0.2,
    max_tokens: int = 500,
    timeout: int = 30,
) -> Dict[str, Any]:
    base_url, api_key, model_id = _resolve_chat_endpoint(model)

    payload = {
        "model": model_id,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }

    # OpenAI supports strict JSON mode; OpenRouter providers vary, so keep it compatible.
    if "api.openai.com" in base_url:
        payload["response_format"] = {"type": "json_object"}

    req = urlreq.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "clawdbot-hourly/1.0",
        },
        method="POST",
    )

    with urlreq.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()

    def _try_parse_json(s: str) -> Optional[Dict[str, Any]]:
        if not s:
            return None
        s2 = s.strip()
        try:
            out = json.loads(s2)
            return out if isinstance(out, dict) else None
        except Exception:
            pass

        # Strip fenced code blocks
        if "```" in s2:
            import re as _re

            m = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", s2, _re.S | _re.I)
            if m:
                try:
                    out = json.loads(m.group(1))
                    return out if isinstance(out, dict) else None
                except Exception:
                    pass

        # Best-effort: take the first {...} span
        i = s2.find("{")
        j = s2.rfind("}")
        if 0 <= i < j:
            frag = s2[i : j + 1]
            try:
                out = json.loads(frag)
                return out if isinstance(out, dict) else None
            except Exception:
                return None
        return None

    parsed = _try_parse_json(content)
    if parsed is not None:
        return parsed

    # Return as best-effort
    return {"raw": content}


def summarize_token_thread(
    *,
    sym: str,
    metrics: Dict[str, Any],
    tg_messages: List[str],
    twitter_snippets: Optional[List[str]] = None,
) -> Dict[str, Any]:
    system = (
        "你是加密交易员助手。输入是一段过去1小时的Telegram观点源聊天（已去除机器人播报）+ 可选的Twitter片段 + 市场指标。\n"
        "输出必须是JSON，不要引用原话，不要复述聊天记录。\n"
        "目标：提炼可交易的叙事/分歧点/风险点，并给出1句交易含义。"
    )

    user = {
        "token": sym,
        "metrics": metrics,
        "telegram": tg_messages[:20],
        "twitter": (twitter_snippets or [])[:5],
        "requirements": {
            "language": "zh",
            "no_quotes": True,
            "fields": ["stance", "thesis", "drivers", "risks", "trade_implication"],
            "stance_values": ["偏多", "偏空", "分歧", "中性"],
        },
    }

    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), max_tokens=520)


def summarize_token_threads_batch(*, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Batch summarize up to 3 token threads in ONE call.

    items: [{token, metrics, telegram, twitter}]
    output: {items:[{token, stance, thesis, drivers, risks, trade_implication}]}
    """

    system = (
        "你是加密交易员助手。输入是过去1小时内最多3个token的Telegram观点源聊天摘要（已过滤机器人）+ 可选Twitter片段 + 市场指标。\n"
        "请对每个token分别输出结构化总结，不要引用原话，不要复述聊天记录。\n"
        "输出JSON：{items:[{token, stance, thesis, drivers, risks, trade_implication}]}。\n"
        "- stance只能是: 偏多/偏空/分歧/中性\n"
    )

    user = {
        "items": items[:3],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), temperature=0.1, max_tokens=700)


def summarize_oi_trading_plans(*, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Create trader-usable plans for top OI movers (ONE call).

    items: [{
      symbol,
      price_now, price_1h, price_4h, price_24h,
      vol_1h, vol_ratio,
      oi_now, oi_1h, oi_4h, oi_24h,
      flow,
      kline_1h, kline_4h
    }]

    output: {items:[{symbol, bias, setup, triggers, invalidation, targets, risk_notes}]}

    bias: 多 / 空 / 观望 (only 多/空 when very clear or extreme).
    """

    system = (
        "你是专业交易员助手，负责把结构化的OI/价格/K线信息转成可执行的交易计划。\n"
        "只允许使用输入字段推导，不要编造新闻/链上/资金流。不要引用原话。\n"
        "输出JSON：{items:[{symbol,bias,setup,triggers,invalidation,targets,risk_notes,twitter_bull,twitter_bear,twitter_quality}]}。\n"
        "- bias 只能是: 多 / 空 / 观望\n"
        "- 只有在趋势非常明显或出现极端条件才允许 bias=多/空；否则一律 bias=观望\n"
        "- 你会拿到 kline_1h/kline_4h 的结构化字段：range(lo/hi/pos/loc), swing(hi/lo), ema20_slope_pct, rsi14, volume(ratio) 等。\n"
        "- setup 必须一句话，<=60字：1h/4h趋势 + 位置 + 量能(量比) + OI flow\n"
        "- triggers 必须给2条，简短，<=24字/条（可用‘突破区间上沿/跌破区间下沿/回踩EMA20确认’这种模板）\n"
        "- targets 必须给2条，<=24字/条（优先：区间上沿/下沿、swing high/low）\n"
        "- invalidation 必须给1条，<=28字（明确一个失效条件）\n"
        "- risk_notes 给1条，<=24字\n"
        "- 如果输入里含 twitter_summary 或 twitter.snippets：请额外输出\n"
        "  - twitter_quality: 一句话（例如：讨论偏少/偏营销/分歧/有交易员共识）\n"
        "  - twitter_bull: 1句<=24字概括看多理由（没有则空字符串）\n"
        "  - twitter_bear: 1句<=24字概括看空理由（没有则空字符串）\n"
    )

    user = {
        "items": items[:3],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), temperature=0.1, max_tokens=780)


def summarize_narratives(*, tg_messages: List[str]) -> Dict[str, Any]:
    system = (
        "你是加密交易员助手。输入是过去1小时的Telegram观点源人类聊天（已过滤机器人）。\n"
        "请提炼Top5‘叙事/事件’，目标是可操作、可定位。不要引用原话，不要复述聊天记录。\n"
        "输出JSON：{items:[{one_liner, sentiment, triggers, related_assets}]}。\n"
        "硬性要求：\n"
        "- sentiment只能是: 偏多/偏空/分歧/中性\n"
        "- 禁止使用泛指开头：某个/某些/一些/有人/用户/群友/大家/市场参与者/投资者。\n"
        "- one_liner必须包含至少一个可定位锚点：明确token/项目名/链名/平台名/具体事件（如上线/上所/解锁/黑客/清算/回购/治理）/时间窗。\n"
        "- 如果无法满足锚点要求，请不要输出该条（宁可少于5条）。\n"
        "- triggers用3~8个短词/短语概括（用分号或逗号连接），不要写长段。\n"
        "- related_assets尽量填token/链/平台/人物；不确定就留空数组（不要编）。\n"
    )

    user = {
        "telegram": tg_messages[:80],
        "requirements": {
            "language": "zh",
            "no_quotes": True,
            "fields": ["items"],
        },
    }

    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), temperature=0.1, max_tokens=520)


def summarize_twitter_topics(*, twitter_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    system = (
        "你是加密交易员助手。输入是过去2小时Twitter雷达抓到的片段（已聚合/去重）。\n"
        "请按‘主题/事件’聚合并提炼Top5，不要引用原话，不要输出链接。\n"
        "输出JSON：{items:[{one_liner, sentiment, signals, related_assets}]}。\n"
        "硬性要求：\n"
        "- sentiment只能是: 偏多/偏空/分歧/中性\n"
        "- one_liner必须具体，避免泛化；至少包含一个可定位锚点（人物/项目/平台/事件）。\n"
        "- signals用3~8个短词/短语概括（用分号或逗号连接）。\n"
        "- related_assets尽量填token/项目/平台；不确定就留空数组（不要编）。\n"
    )

    user = {
        "twitter": twitter_items[:60],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), temperature=0.1, max_tokens=520)


def summarize_twitter_ca_viewpoints(*, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize viewpoints for on-chain meme candidates.

    CA is OPTIONAL. The goal is to summarize what Twitter is saying about a token,
    and use CA only as an additional disambiguation anchor when available.

    Input items schema (best-effort):
      [{sym, ca?, evidence:{snippets}}]

    Output:
      {items:[{sym, ca?, one_liner, sentiment, signals}]}
    """

    system = (
        "你是加密交易员助手。输入是若干候选token，每个候选给：symbol、(可选)合约地址、以及Twitter证据片段(去噪后的短句)。\n"
        "任务：为每个候选提炼‘当前社交讨论在说什么’的一句话观点总结，最多Top5。\n"
        "硬约束：不能引用原文句子；不能输出链接；不能编造未出现的事实。\n"
        "非常重要：只要某个候选的snippets非空，就必须为它产出一条items（即使只能给出‘共识不足/分歧点’也要写清楚主要争论点）。\n"
        "输出JSON：{items:[{sym, ca?, one_liner, sentiment, signals}]}\n"
        "规则：\n"
        "- sentiment只能是: 偏多/偏空/分歧/中性\n"
        "- one_liner：20~60字，写‘讨论的主张/分歧’，避免只报数字。\n"
        "- signals：3~8个短词/短语（用分号连接），只从snippets里抽象，不要扩展新概念。\n"
    )

    user = {
        "items": items[:8],
        "requirements": {"language": "zh", "no_quotes": True, "topN": 5},
    }

    # Prefer a stronger model for reliable JSON + non-empty items.
    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), model="openai-codex/gpt-5.2", temperature=0.1, max_tokens=700, timeout=45)


def summarize_overall(
    *,
    token_summaries: List[Dict[str, Any]],
    oi_lines: List[str],
    twitter_top: List[str],
    narratives: Optional[List[Dict[str, Any]]] = None,
    twitter_topics: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    system = (
        "你是加密交易员助手。请把输入信息压缩成一个小时级别的总览，不要引用原话。\n"
        "输出JSON：{market_mood, main_themes, watchlist, risk_notes}。"
    )

    user = {
        "oi": oi_lines[:8],
        "narratives": (narratives or [])[:5],
        "twitter_topics": (twitter_topics or [])[:5],
        "token_summaries": token_summaries[:5],
        "twitter_raw": twitter_top[:6],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    # give overall a bit more time; if it still times out, caller will catch and skip
    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), max_tokens=420, timeout=55)

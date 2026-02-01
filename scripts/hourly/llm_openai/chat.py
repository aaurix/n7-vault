#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""OpenRouter/OpenAI chat helper for summarization."""

from __future__ import annotations

import json
import os
import time
import urllib.request as urlreq
from typing import Any, Dict, List, Optional, Tuple

from .keys import load_openrouter_api_key
from .parsing import parse_json_object


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
    retry_on_parse_fail: bool = False,
    retry_delay_s: float = 0.8,
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

    def _call_once() -> str:
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

        return (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "{}").strip()

    content = _call_once()

    parsed = parse_json_object(content)
    if parsed is not None:
        return parsed

    if retry_on_parse_fail:
        time.sleep(max(0.1, float(retry_delay_s)))
        content2 = _call_once()
        parsed2 = parse_json_object(content2)
        if parsed2 is not None:
            return parsed2
        return {"raw": content2, "_parse_failed": True, "_retry_used": True}

    # Return as best-effort
    return {"raw": content, "_parse_failed": True}


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


def summarize_tg_actionables(*, tg_snippets: List[str]) -> Dict[str, Any]:
    """Extract trader-actionable items from Telegram snippets (ONE call)."""

    system = (
        "你是加密交易员助手。输入是过去1小时的Telegram观点短片段（已预处理/去重）。\n"
        "请输出Top5可交易标的。输出JSON：{items:[{asset_name,why_buy,why_not_buy,trigger,risk,evidence_snippets}]}。\n"
        "只用输入信息，不要编造；字段没有就给空字符串/空数组；evidence_snippets 取1-2个短片段，去链接。\n"
        "字段长度限制：asset_name<=18字；why_buy/why_not_buy/trigger/risk<=42字；evidence_snippets<=80字/条。"
    )

    user = {
        "telegram_snippets": tg_snippets[:120],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(
        system=system,
        user=json.dumps(user, ensure_ascii=False),
        temperature=0.1,
        max_tokens=720,
        retry_on_parse_fail=True,
        retry_delay_s=0.9,
    )


def summarize_twitter_actionables(*, twitter_snippets: List[str]) -> Dict[str, Any]:
    """Extract trader-actionable items from Twitter snippets (ONE call)."""

    system = (
        "你是加密交易员助手。输入是过去2小时的Twitter/X短片段（已预处理/去重）。\n"
        "请输出Top5可交易标的。输出JSON：{items:[{asset_name,why_buy,why_not_buy,trigger,risk,evidence_snippets}]}。\n"
        "只用输入信息，不要编造；字段没有就给空字符串/空数组；evidence_snippets 取1-2个短片段，去链接。\n"
        "字段长度限制：asset_name<=18字；why_buy/why_not_buy/trigger/risk<=42字；evidence_snippets<=80字/条。"
    )

    user = {
        "twitter_snippets": twitter_snippets[:120],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(
        system=system,
        user=json.dumps(user, ensure_ascii=False),
        temperature=0.1,
        max_tokens=720,
        retry_on_parse_fail=True,
        retry_delay_s=0.9,
    )


def detect_twitter_following_events(*, twitter_snippets: List[str]) -> Dict[str, Any]:
    """Detect notable events from following timeline snippets (LLM)."""

    system = (
        "你是加密交易员助手。输入是过去1小时following时间线的X短句（已清洗/去重）。\n"
        "输入列表元素可能是字符串，或{ text, count }对象；count代表相似话题的聚类数量。\n"
        "请仅提取重大事件。输出JSON：{events:[...]}。\n"
        "硬性要求：\n"
        "- events每条<=50字，最多3条；没有则输出空数组。\n"
        "- events强调客观事件（上所/解锁/黑客/融资/空投/监管/脱锚/回购等），优先带主体。\n"
        "- 优先考虑count较高的内容作为事件依据。\n"
        "- 只基于输入，不要编造；不要引用原文；不要输出链接。\n"
    )

    user = {
        "twitter_snippets": twitter_snippets[:140],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(
        system=system,
        user=json.dumps(user, ensure_ascii=False),
        temperature=0.1,
        max_tokens=220,
        retry_on_parse_fail=True,
        retry_delay_s=0.9,
    )



def summarize_twitter_following(*, twitter_snippets: List[str]) -> Dict[str, Any]:
    """Summarize following timeline into narratives/sentiment/events."""

    system = (
        "你是加密交易员助手。输入是过去1小时following时间线的X短句（已清洗/去重）。\n"
        "输入列表元素可能是字符串，或{ text, count }对象；count代表相似话题的聚类数量。\n"
        "请输出三部分：叙事、情绪、重大事件。输出JSON：{narratives:[...], sentiment, events:[...]}。\n"
        "硬性要求：\n"
        "- narratives/events每条<=50字，最多3条；没有则输出空数组。\n"
        "- narratives必须包含可定位锚点（项目/代币/平台/事件），避免泛化描述。\n"
        "- events强调客观事件（上所/解锁/黑客/融资/空投/监管/脱锚/回购等），优先带主体。\n"
        "- sentiment必须包含: 偏多/偏空/分歧/中性 之一，可附10字内原因。\n"
        "- 优先考虑count较高的内容作为叙事/事件。\n"
        "- 只基于输入，不要编造；不要引用原文；不要输出链接。\n"
    )

    user = {
        "twitter_snippets": twitter_snippets[:140],
        "requirements": {"language": "zh", "no_quotes": True},
    }

    return chat_json(
        system=system,
        user=json.dumps(user, ensure_ascii=False),
        temperature=0.1,
        max_tokens=420,
        retry_on_parse_fail=True,
        retry_delay_s=0.9,
    )


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
      [{id?, sym, ca?, evidence:{snippets}}]

    Output:
      {items:[{id?, sym, ca?, one_liner, sentiment, signals}]}
    """

    system = (
        "你是加密交易员助手。输入是若干候选token，每个候选给：id(可选)、symbol、(可选)合约地址、以及Twitter证据片段(去噪后的短句)。\n"
        "任务：为每个候选提炼‘当前社交讨论在说什么’的一句话观点总结，最多Top5。\n"
        "硬约束：不能引用原文句子；不能输出链接；不能编造未出现的事实。\n"
        "非常重要：只要某个候选的snippets非空，就必须为它产出一条items（即使只能给出‘共识不足/分歧点’也要写清楚主要争论点）。\n"
        "输出JSON：{items:[{id?, sym, ca?, one_liner, sentiment, signals}]}\n"
        "规则：\n"
        "- 如果输入含id，输出必须原样带回同一id（用于匹配）。\n"
        "- sentiment只能是: 偏多/偏空/分歧/中性\n"
        "- one_liner：20~60字，写‘讨论的主张/分歧’，避免只报数字。\n"
        "- signals：3~8个短词/短语（用分号连接），只从snippets里抽象，不要扩展新概念。\n"
    )

    user = {
        "items": items[:8],
        "requirements": {"language": "zh", "no_quotes": True, "topN": 5},
    }

    # Use default OpenRouter chat model (no hard-coded override).
    return chat_json(system=system, user=json.dumps(user, ensure_ascii=False), temperature=0.1, max_tokens=700, timeout=45)


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


__all__ = [
    "chat_json",
    "summarize_token_thread",
    "summarize_token_threads_batch",
    "summarize_oi_trading_plans",
    "summarize_tg_actionables",
    "summarize_twitter_actionables",
    "detect_twitter_following_events",
    "summarize_twitter_following",
    "summarize_narratives",
    "summarize_twitter_topics",
    "summarize_twitter_ca_viewpoints",
    "summarize_overall",
]

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hourly TG+Twitter market/meme summary (production).

Design principles (user requirements):
- Deterministic pipeline: TG local DB + Twitter radar.
- Viewpoint-first, but ONLY output tradable token/CA threads.
- No raw quotes. Only distilled summaries.
- OI signals: strict 60m window. If empty, replay the same 60m window once.

This script prints a single JSON object to stdout for the cron delivery wrapper.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

# Make ./scripts importable when executed as a script
sys.path.insert(0, os.path.dirname(__file__))

from hourly.tg_client import TgClient, msg_text, sender_id
from hourly.filters import is_botish_text
from hourly.bots import load_bot_sender_ids
from hourly.oi import parse_oi_signals
from hourly.viewpoints import extract_viewpoint_threads
from hourly.render import build_summary
from hourly.dex import enrich_symbol, resolve_addr_symbol
from hourly.llm_openai import (
    embeddings,
    summarize_token_thread,
    summarize_token_threads_batch,
    summarize_narratives,
    summarize_twitter_topics,
    summarize_oi_trading_plans,
    load_openai_api_key,
)
from hourly.narratives import compress_messages
from hourly.embed_cluster import greedy_cluster
from hourly.topic_pipeline import build_topics
from hourly.oi_plan_pipeline import build_oi_items, build_oi_plans
from hourly.kline_fetcher import run_kline_json

SH_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")

# Explicit Telegram channel ids
TG_CHANNELS: Dict[str, str] = {
    "特训组": "3407266761",
    "特训组(同名备用)": "5087005415",
    "Apex Hill Partners 遠見投資": "2325474571",
    "方程式-OI&Price异动（抓庄神器）": "3096206759",
    "推特AI分析": "3041253761",
    "Pow's Gem Calls": "1198046393",
    "AU Trading Journal 🩵😈": "2955560057",
    "Birds of a Feather": "2272160911",
    # Viewpoint sources
    "1000X GEM NFT Group": "2335179695",
    "1000xGem Group": "1956264308",
}

VIEWPOINT_CHAT_IDS = {
    int(TG_CHANNELS["1000X GEM NFT Group"]),
    int(TG_CHANNELS["1000xGem Group"]),
    int(TG_CHANNELS["特训组"]),
    int(TG_CHANNELS["特训组(同名备用)"]),
}


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def run_kline_context(symbol: str, *, interval: str, lookback: int = 80) -> str:
    """Backward-compatible one-line context."""
    cmd = [
        "python3",
        "/Users/massis/clawd/scripts/binance_kline_context.py",
        symbol,
        "--interval",
        interval,
        "--lookback",
        str(lookback),
    ]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=18)
        line = (p.stdout or "").strip().splitlines()[:1]
        return line[0].strip() if line else ""
    except Exception:
        return ""


# (moved) run_kline_json -> hourly.kline_fetcher


def run_meme_radar() -> Dict[str, Any]:
    cmd = [
        "python3",
        "/Users/massis/clawd/scripts/meme_radar.py",
        "--hours",
        "2",
        "--chains",
        "solana",
        "bsc",
        "base",
        "--tweet-limit",
        "120",
        "--limit",
        "8",
    ]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
    except Exception:
        pass

    path = "/Users/massis/clawd/memory/meme/last_candidates.json"
    if os.path.exists(path):
        try:
            return json.loads(open(path, "r", encoding="utf-8").read())
        except Exception:
            return {}
    return {}


def main() -> int:
    client = TgClient()

    now_sh = dt.datetime.now(SH_TZ)
    now_utc = now_sh.astimezone(UTC)

    # --- Time budget (stability-first) ---
    t0 = dt.datetime.now(UTC)

    def _elapsed_s() -> float:
        return (dt.datetime.now(UTC) - t0).total_seconds()

    def _over_budget(limit_s: float = 70.0) -> bool:
        return _elapsed_s() >= limit_s

    since_utc = now_utc - dt.timedelta(minutes=60)
    since = since_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    until = now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    errors: List[str] = []

    # LLM availability flag (used throughout; stability-first gating applies per-step)
    use_llm = bool(load_openai_api_key())

    if not client.health_ok():
        raise SystemExit("TG service not healthy")

    # --- Fetch messages (DB read; replay only when needed) ---
    messages_by_chat: Dict[str, List[Dict[str, Any]]] = {}

    # formula feed
    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    formula_msgs = client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    if not formula_msgs:
        try:
            client.replay(int(formula_id), limit=400, since=since, until=until)
        except Exception as e:
            errors.append(f"formula_replay_failed: {e}")
        formula_msgs = client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    messages_by_chat[formula_id] = formula_msgs

    # viewpoint chats
    for cid in sorted(VIEWPOINT_CHAT_IDS):
        s = str(cid)
        rows = client.fetch_messages(cid, limit=260, since=since, until=until)
        if not rows:
            # replay only if empty (cost control)
            try:
                client.replay(cid, limit=300, since=since, until=until)
            except Exception:
                pass
            rows = client.fetch_messages(cid, limit=260, since=since, until=until)
        messages_by_chat[s] = rows

    # --- OI signals ---
    oi_signals = parse_oi_signals(messages_by_chat.get(formula_id, []))
    oi_lines: List[str] = []

    # Enrich OI signals with flow labels (deterministic)
    for s in oi_signals[:]:
        oi = s.get("oi")
        p1h = s.get("p1h")
        if oi is not None and oi > 0 and (p1h or 0) > 0:
            s["flow"] = "增仓跟涨"
        elif oi is not None and oi > 0:
            s["flow"] = "增仓但走弱"
        elif oi is not None and oi < 0 and (p1h or 0) > 0:
            s["flow"] = "减仓上涨"
        else:
            s["flow"] = "减仓/回撤"

    # Render OI lines (upgraded spec: current price + OI/price/vol changes)
    oi_items = build_oi_items(oi_signals=oi_signals, kline_fetcher=run_kline_json, top_n=5)

    def _fmt_pct(x):
        return "?" if x is None else f"{x:+.1f}%"

    def _fmt_num(x):
        if x is None:
            return "?"
        try:
            return f"{float(x):.4g}"
        except Exception:
            return str(x)

    for it in oi_items[:5]:
        sym = it.get("symbol")
        px_now = it.get("price_now")
        oi1 = it.get("oi_1h")
        oi4 = it.get("oi_4h")
        oi24 = it.get("oi_24h")
        px1 = it.get("price_1h")
        px4 = it.get("price_4h")
        px24 = it.get("price_24h")
        v1 = it.get("vol_1h")
        vr = it.get("vol_ratio")
        flow = it.get("flow")

        line = (
            f"- {sym} 现价{_fmt_num(px_now)} | "
            f"Price 1h{_fmt_pct(px1)} 4h{_fmt_pct(px4)} 24h{_fmt_pct(px24)} | "
            f"OI 1h{_fmt_pct(oi1)} 4h{_fmt_pct(oi4)} 24h{_fmt_pct(oi24)} | "
            f"Vol1h {_fmt_num(v1)} (ratio {('?' if vr is None else f'{vr:.2f}')})：{flow}"
        )
        oi_lines.append(line)

    # --- OI trader plans (Top3, high priority) ---
    oi_plans = build_oi_plans(
        use_llm=use_llm,
        oi_items=oi_items,
        llm_fn=summarize_oi_trading_plans,
        time_budget_ok=lambda lim: (not _over_budget(lim)),
        budget_s=45.0,
        top_n=3,
        errors=errors,
        tag="oi_plan",
    )

    # --- Viewpoint threads (token/CA only; no quotes) ---
    bot_ids = load_bot_sender_ids()
    human_texts: List[str] = []
    for cid in VIEWPOINT_CHAT_IDS:
        for m in messages_by_chat.get(str(cid), []):
            sid = sender_id(m)
            if sid is not None and sid in bot_ids:
                continue
            t = msg_text(m)
            if not t or is_botish_text(t):
                continue
            human_texts.append(t[:260])

    vp = extract_viewpoint_threads(human_texts, min_heat=3, weak_heat=1)
    strong_threads = vp.get("strong") or []
    weak_threads = vp.get("weak") or []

    # --- Telegram topics (热点Top5) via unified topic pipeline ---
    narratives_items: List[Dict[str, Any]] = []
    if use_llm:
        # Build topics (best-effort). On failure/budget, it returns [].
        topics = build_topics(
            texts=human_texts,
            embeddings_fn=embeddings,
            cluster_fn=greedy_cluster,
            llm_summarizer=summarize_narratives,
            llm_items_key="items",
            prefilter=None,
            postfilter=None,
            max_clusters=10,
            threshold=0.82,
            embed_timeout=30,
            time_budget_ok=lambda lim: (not _over_budget(lim)),
            budget_embed_s=55.0,
            budget_llm_s=65.0,
            llm_arg_name="tg_messages",
            errors=errors,
            tag="tg_topics",
        )

        # normalize
        for it in (topics or [])[:5]:
            if not isinstance(it, dict):
                continue
            one = it.get("one_liner") or ""
            sen = it.get("sentiment") or "中性"
            tri = it.get("triggers") or ""
            rel = it.get("related_assets")
            if isinstance(sen, list):
                sen = sen[0] if sen else "中性"
            if isinstance(tri, list):
                tri = "；".join([str(x) for x in tri[:5]])
            if not isinstance(rel, list):
                rel = []
            narratives_items.append({
                "one_liner": str(one).strip(),
                "sentiment": str(sen).strip(),
                "triggers": str(tri).strip(),
                "related_assets": [str(x) for x in rel[:6]],
                "_inferred": False,
            })

    # --- Twitter radar (secondary) ---
    radar = run_meme_radar() or {}
    radar_items = radar.get("items") or []
    twitter_lines: List[str] = []
    radar_syms: List[str] = []

    # Deduplicate repeated radar snippets (e.g. the same Binance Alpha notice posted for multiple tokens)
    seen_snip: Dict[str, Dict[str, Any]] = {}
    for it in radar_items[:30]:
        dex = (it.get("dex") or {})
        sym = (dex.get("baseSymbol") or "").upper().strip()
        if not sym:
            continue
        radar_syms.append(sym)
        m = it.get("mentions")
        ex = ""
        examples = it.get("examples") or []
        if examples and isinstance(examples, list):
            e0 = examples[0]
            ex = (e0.get("text") if isinstance(e0, dict) else str(e0)) or ""
        ex = ex.replace("\n", " ").strip()[:90]
        if not ex:
            continue
        key = ex[:70]
        slot = seen_snip.get(key)
        if not slot:
            seen_snip[key] = {"syms": [sym], "mentions": m, "text": ex}
        else:
            if sym not in slot["syms"]:
                slot["syms"].append(sym)
            # keep max mentions as a proxy
            try:
                slot["mentions"] = max(int(slot.get("mentions") or 0), int(m or 0))
            except Exception:
                pass

    # keep order by mentions desc
    items = list(seen_snip.values())
    items.sort(key=lambda x: -int(x.get("mentions") or 0))
    # Build LLM input items (already deduped)
    def _is_cryptoish_twitter_text(t: str) -> bool:
        # loose filter: keep most crypto content, drop obvious unrelated violent/local news
        tl = (t or "").lower()
        # strong crypto signals
        if any(k in tl for k in ["$", "crypto", "token", "airdrop", "binance", "alpha", "dex", "sol", "bsc", "base", "eth", "btc", "defi", "meme", "rug", "ripple", "xrp", "sec", "lawsuit", "court"]):
            return True
        # drop obvious unrelated violence/local news
        if any(k in tl for k in ["rpg", "rocket", "rocket launcher", "grenade", "shooting", "killed", "dead", "bomb", "terror", "earthquake", "accident"]):
            return False
        # default: keep (loose)
        return True

    twitter_input: List[Dict[str, Any]] = []
    for x in items[:40]:
        txt = x.get("text") or ""
        if not _is_cryptoish_twitter_text(txt):
            continue
        twitter_input.append({
            "syms": x.get("syms") or [],
            "mentions": x.get("mentions") or 0,
            "text": txt,
        })

    # --- Twitter topics (热点Top5) via unified topic pipeline ---
    twitter_topics: List[Dict[str, Any]] = []

    if use_llm and twitter_input:
        tw_syms_set = set([str(x).upper().strip() for x in radar_syms if x])

        def _postfilter_topic(it: Dict[str, Any]) -> bool:
            s = (f"{it.get('one_liner','')} {it.get('signals','')}" or "").lower()
            violence = any(k in s for k in [
                "rpg", "rocket", "grenade", "shooting", "killed", "dead", "bomb",
                "火箭筒", "榴弹", "枪击", "爆炸", "恐袭",
            ])
            crypto_sig = any(k in s for k in [
                "$", "crypto", "token", "airdrop", "binance", "alpha", "dex", "defi", "meme",
                "sol", "bsc", "base", "eth", "btc", "cex", "sec", "lawsuit", "court",
                "ripple", "xrp", "chain", "onchain",
            ])
            if violence and not crypto_sig:
                return False
            if crypto_sig:
                return True
            rel = it.get('related_assets') or []
            if isinstance(rel, list):
                for x in rel:
                    if str(x).upper().strip() in tw_syms_set:
                        return True
            return True

        topics = build_topics(
            texts=[x.get("text") or "" for x in twitter_input],
            embeddings_fn=embeddings,
            cluster_fn=greedy_cluster,
            llm_summarizer=summarize_twitter_topics,
            llm_items_key="items",
            prefilter=_is_cryptoish_twitter_text,
            postfilter=_postfilter_topic,
            max_clusters=10,
            threshold=0.84,
            embed_timeout=30,
            time_budget_ok=lambda lim: (not _over_budget(lim)),
            budget_embed_s=55.0,
            budget_llm_s=65.0,
            llm_arg_name="twitter_items",
            errors=errors,
            tag="tw_topics",
        )

        # normalize to render schema
        for it in (topics or [])[:5]:
            if not isinstance(it, dict):
                continue
            one = str(it.get("one_liner") or "").strip()
            sen = str(it.get("sentiment") or "").strip()
            sig = it.get("signals")
            if isinstance(sig, list):
                sig = "; ".join([str(x) for x in sig[:8]])
            sig = str(sig or "").strip()
            rel = it.get("related_assets")
            if not isinstance(rel, list):
                rel = []
            twitter_topics.append({
                "one_liner": one,
                "sentiment": sen,
                "signals": sig,
                "related_assets": [str(x).strip() for x in rel[:6] if str(x).strip()],
            })

    # --- LLM summarization (Top tokens + 1 overall) ---
    # reuse use_llm computed above

    # Prefer strong threads; if none, fall back to weak candidates
    token_threads = strong_threads[:3] if strong_threads else weak_threads[:3]

    # Build twitter snippets map by symbol (from radar examples)
    tw_map: Dict[str, List[str]] = {}
    for it in radar_items[:20]:
        dex = (it.get("dex") or {})
        sym = (dex.get("baseSymbol") or "").upper().strip()
        if not sym:
            continue
        examples = it.get("examples") or []
        if examples and isinstance(examples, list):
            txt = (examples[0].get("text") if isinstance(examples[0], dict) else str(examples[0])) or ""
            txt = txt.replace("\n", " ").strip()[:160]
            if txt:
                tw_map.setdefault(sym, []).append(txt)

    llm_threads: List[Dict[str, Any]] = []

    # 稳态优先：token LLM 仅在强信号时触发，并且合并为 1 次调用（最多3个token）
    should_llm_tokens = bool(use_llm and token_threads and strong_threads and (not _over_budget(65.0)))

    if should_llm_tokens:
        batch_in: List[Dict[str, Any]] = []
        for th in token_threads[:3]:
            sym = th.get("sym") or ""
            msgs = th.get("_msgs") or []
            dexm = th.get("_dex") or {}
            metrics = {
                "marketCap": dexm.get("marketCap") or dexm.get("fdv"),
                "vol24h": dexm.get("vol24h"),
                "liquidityUsd": dexm.get("liquidityUsd"),
                "chg1h": dexm.get("chg1h"),
                "chg24h": dexm.get("chg24h"),
                "chainId": dexm.get("chainId"),
                "dexId": dexm.get("dexId"),
            }
            batch_in.append({
                "token": sym,
                "metrics": metrics,
                "telegram": msgs[:20],
                "twitter": (tw_map.get(sym) or [])[:5],
            })

        try:
            bj = summarize_token_threads_batch(items=batch_in)
            outs = bj.get("items") if isinstance(bj, dict) else None
            out_map: Dict[str, Dict[str, Any]] = {}
            if isinstance(outs, list):
                for it in outs:
                    if isinstance(it, dict) and it.get("token"):
                        out_map[str(it.get("token") or "").upper()] = it

            for th in token_threads[:3]:
                sym = (th.get("sym") or "").upper().strip()
                s = out_map.get(sym) or {}
                llm_threads.append({
                    "title": th.get("title"),
                    "stance": s.get("stance") or th.get("stance"),
                    "count": th.get("count"),
                    "sym": sym,
                    "thesis": s.get("thesis") or "",
                    "drivers": "; ".join(s.get("drivers") or []) if isinstance(s.get("drivers"), list) else (s.get("drivers") or ""),
                    "risks": "; ".join(s.get("risks") or []) if isinstance(s.get("risks"), list) else (s.get("risks") or ""),
                    "trade_implication": s.get("trade_implication") or "",
                    "points": th.get("points") or [],
                })
        except Exception as e:
            errors.append(f"llm_token_batch_failed:{e}")
            llm_threads = []

    # Decide what to render as viewpoint threads
    # If no token LLM, fall back to rule-based threads including weak (heat>=1)
    base_threads = (strong_threads or []) + (weak_threads or [])
    base_threads.sort(key=lambda x: -int(x.get("count") or 0))
    threads = llm_threads if llm_threads else base_threads

    tg_syms = [t.get("sym") for t in threads if t.get("sym")]
    overlap = sorted(set(tg_syms) & set(radar_syms))

    # --- A) improve narrative asset linking (best-effort inference) ---
    # If LLM couldn't pin related_assets, infer 1-2 candidates by keyword overlap
    # between the narrative text and token contexts (TG thread msgs + Twitter snippets).
    # Render will label these as 推断.

    # Candidate universe MUST come from Telegram only (do not mix with Twitter radar)
    candidates: List[str] = []
    seen = set()
    for x in tg_syms:
        if not x:
            continue
        x = str(x).upper().strip()
        if x in seen:
            continue
        seen.add(x)
        candidates.append(x)

    # Build per-symbol context text from Telegram thread messages only
    sym_ctx: Dict[str, str] = {}
    for th in (token_threads or []):
        s = (th.get("sym") or "").upper().strip()
        if not s:
            continue
        msgs = th.get("_msgs") or []
        sym_ctx[s] = " ".join([str(x) for x in msgs[:20]])

    def _kw(s: str) -> List[str]:
        import re
        s = (s or "").lower()
        # extract latin tokens and simple cjk bigrams
        latin = re.findall(r"[a-z0-9_]{3,}", s)
        cjk = re.findall(r"[\u4e00-\u9fff]{2,}", s)
        cjk2: List[str] = []
        for w in cjk:
            w = w.strip()
            for i in range(0, min(len(w) - 1, 6)):
                cjk2.append(w[i : i + 2])
        out = latin + cjk2
        # drop too-common
        stop = {"市场", "项目", "代币", "价格", "今天", "现在", "小时", "社区", "交易", "流动性"}
        out2 = []
        seen2 = set()
        for x in out:
            if x in stop or len(x) < 2:
                continue
            if x in seen2:
                continue
            seen2.add(x)
            out2.append(x)
        return out2[:30]

    def _is_probable_ticker(x: str) -> bool:
        import re
        x = (x or "").strip()
        return bool(re.fullmatch(r"[A-Z0-9]{2,10}", x))

    def _score(nar: Dict[str, Any], sym: str) -> int:
        k = _kw(f"{nar.get('one_liner','')} {nar.get('triggers','')}")
        if not k:
            return 0
        ctx = (sym_ctx.get(sym) or "").lower()
        if not ctx:
            return 0
        s = 0
        for w in k:
            if w and w in ctx:
                s += 1
        return s

    import re

    # Helper: attempt to pin a narrative to a token mentioned in text (even if lowercase), then
    # optionally resolve CA from TG messages and validate via DexScreener.
    def _extract_token_hints(nar: Dict[str, Any]) -> List[str]:
        s = f"{nar.get('one_liner','')} {nar.get('triggers','')}".strip()
        if not s:
            return []
        # Prefer explicit $ticker
        hints = [x[1:] for x in re.findall(r"\$([A-Za-z0-9]{2,12})", s)]
        # Also allow lowercase/word tokens (e.g. fdog)
        hints += re.findall(r"\b([A-Za-z]{3,12})\b", s)
        out = []
        seenh = set()
        bad = {"bsc", "sol", "base", "eth", "btc", "usdt", "usdc", "dex", "alpha"}
        for h in hints:
            hu = h.upper()
            if hu.lower() in bad:
                continue
            if hu in seenh:
                continue
            seenh.add(hu)
            out.append(hu)
        return out[:3]

    def _find_addr_near_hint(hint: str) -> str | None:
        # Search TG messages for lines mentioning the hint and extract an address
        for t in human_texts:
            tl = t.lower()
            if hint.lower() in tl:
                # reuse extractor (handles base58 + 0x)
                _sy, _ad = extract_symbols_and_addrs(t)
                if _ad:
                    return _ad[0]
        return None

    def _pin_hint(hint: str) -> str | None:
        # Validate via DexScreener by symbol; if not found, try CA resolution
        d = enrich_symbol(hint)
        if d:
            return hint
        addr = _find_addr_near_hint(hint)
        if addr:
            rs = resolve_addr_symbol(addr)
            if rs:
                return rs
        return None

    for it in narratives_items:
        # 0) If narrative contains explicit token hints, try to pin them first.
        pinned: List[str] = []
        for h in _extract_token_hints(it):
            p = _pin_hint(h)
            if p and p not in pinned:
                pinned.append(p)
        if pinned:
            it["related_assets"] = pinned[:6]
            it["_inferred"] = False
            # If one_liner still says “某个代币/某个项目”, replace with the first pinned token to reduce vagueness
            one = str(it.get("one_liner") or "")
            if pinned and ("某个代币" in one or "某个项目" in one):
                it["one_liner"] = one.replace("某个代币", pinned[0]).replace("某个项目", pinned[0])
            continue

        # 1) Keep/normalize LLM-provided related_assets, but do NOT allow Twitter-only tickers.
        rel = it.get("related_assets")
        if not isinstance(rel, list):
            rel = []
        rel_norm: List[str] = []
        for x in rel:
            xs = str(x).strip()
            if not xs:
                continue
            up = xs.upper()
            # If it looks like a ticker, only keep it when it appeared in Telegram token threads.
            if _is_probable_ticker(up) and candidates and up not in candidates:
                continue
            rel_norm.append(up if _is_probable_ticker(up) else xs)
        if rel_norm:
            it["related_assets"] = rel_norm[:6]
            it["_inferred"] = False
            continue

        # 2) No explicit assets: infer from Telegram-only candidates via keyword overlap (score>=1)
        if not candidates:
            continue

        scored = [(c, _score(it, c)) for c in candidates]
        scored.sort(key=lambda x: (-x[1], x[0]))
        top = [f"{c}({sc})" for c, sc in scored if sc >= 1][:6]
        if not top:
            continue
        it["related_assets"] = top
        it["_inferred"] = True

    # Overall LLM summary to build sentiment + watch
    sentiment = "整体偏风险：观点源更偏短线轮动；缺少持续共识时更适合等结构确认/不追第一根。"
    watch: List[str] = []

    # --- Sentiment + Watch (稳态优先：本地规则，不再跑 overall) ---
    def _sent_score(s: str) -> int:
        if not s:
            return 0
        s = str(s).strip()
        if s == "偏多":
            return 1
        if s == "偏空":
            return -1
        if s == "分歧":
            return 0
        return 0

    # sentiment from TG热点 + Twitter热点
    sc = 0
    n = 0
    for it in (narratives_items or [])[:5]:
        sc += _sent_score(it.get("sentiment"))
        n += 1
    for it in (twitter_topics or [])[:5]:
        sc += _sent_score(it.get("sentiment"))
        n += 1
    if n:
        if sc >= 2:
            sentiment = "偏多"
        elif sc <= -2:
            sentiment = "偏空"
        elif abs(sc) <= 1:
            sentiment = "分歧"

    # watchlist preference: OI first, then token threads, then pinned assets from TG热点/Twitter热点
    watch = []
    for ln in oi_lines[:5]:
        # pattern: "- XXX OI ..."
        import re
        m = re.search(r"-\s*([A-Z0-9]{3,15})\s+OI", ln)
        if m:
            watch.append(m.group(1))
    for s in (tg_syms or [])[:5]:
        if s and s not in watch:
            watch.append(s)
    for it in (narratives_items or [])[:5]:
        rel = it.get("related_assets")
        if isinstance(rel, list):
            for x in rel[:3]:
                xs = str(x).strip()
                if xs and xs not in watch:
                    watch.append(xs)
    for it in (twitter_topics or [])[:5]:
        rel = it.get("related_assets")
        if isinstance(rel, list):
            for x in rel[:3]:
                xs = str(x).strip()
                if xs and xs not in watch:
                    watch.append(xs)

    watch = watch[:3]

    if not watch:
        # Prefer Telegram-side watch; do not auto-add Twitter-only tickers here
        if tg_syms:
            watch.extend([x for x in tg_syms[:3] if x])

    title = f"{now_sh.strftime('%H')}:00 二级山寨+链上meme"
    summary_whatsapp = build_summary(
        title=title,
        oi_lines=oi_lines,
        plans=oi_plans,
        narratives=narratives_items,
        threads=threads,
        weak_threads=weak_threads,
        twitter_lines=twitter_topics,
        overlap_syms=None,
        sentiment=sentiment,
        watch=watch,
        whatsapp=True,
    )
    summary_markdown = build_summary(
        title=title,
        oi_lines=oi_lines,
        plans=oi_plans,
        narratives=narratives_items,
        threads=threads,
        weak_threads=weak_threads,
        twitter_lines=twitter_topics,
        overlap_syms=None,
        sentiment=sentiment,
        watch=watch,
        whatsapp=False,
    )

    tmp_md = "/tmp/clawdbot_hourly_summary.md"
    try:
        with open(tmp_md, "w", encoding="utf-8") as f:
            f.write(summary_markdown)
    except Exception:
        tmp_md = ""

    hour_key = now_sh.strftime("%Y-%m-%d %H:00")
    summary_hash = _sha1(summary_whatsapp + "\n---\n" + summary_markdown)

    out = {
        "since": since,
        "until": until,
        "hourKey": hour_key,
        "summaryHash": summary_hash,
        "summary_whatsapp": summary_whatsapp,
        "summary_markdown": summary_markdown,
        "summary_markdown_path": tmp_md,
        "errors": errors,
    }

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Hourly market summary pipeline.

This module contains the deterministic pipeline used by scripts/hourly_market_summary.py.
It is intentionally *not* a generic framework; it is the production pipeline.

Key guarantees:
- Uses repo-root-relative paths for all repo artifacts.
- Deadline-based time budgeting.
- Always returns a JSON-serializable dict (caller prints to stdout).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from repo_paths import memory_path, scripts_path

from hourly.bots import load_bot_sender_ids
from hourly.dex import enrich_addr, enrich_symbol, resolve_addr_symbol
from hourly.embed_cluster import greedy_cluster
from hourly.filters import extract_symbols_and_addrs, is_botish_text
from hourly.kline_fetcher import run_kline_json
from hourly.llm_openai import (
    embeddings,
    load_openai_api_key,
    summarize_narratives,
    summarize_oi_trading_plans,
    summarize_token_threads_batch,
    summarize_twitter_ca_viewpoints,
)
from hourly.oi import parse_oi_signals
from hourly.oi_plan_pipeline import build_oi_items, build_oi_plans
from hourly.render import build_summary
from hourly.tg_client import TgClient, msg_text, sender_id
from hourly.topic_pipeline import build_topics
from hourly.viewpoints import extract_viewpoint_threads


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
    # Viewpoint sources (expanded)
    "1000X GEM NFT Group": "2335179695",
    "1000xGem Group": "1956264308",
    "A’s alpha": "2243200666",
    "Pickle Cat's Den 🥒": "2408369357",
    "Legandary 牛市卷王版本": "3219058398",
}

VIEWPOINT_CHAT_IDS = {
    int(TG_CHANNELS["1000X GEM NFT Group"]),
    int(TG_CHANNELS["1000xGem Group"]),
    int(TG_CHANNELS["特训组"]),
    int(TG_CHANNELS["特训组(同名备用)"]),
    int(TG_CHANNELS["A’s alpha"]),
    int(TG_CHANNELS["推特AI分析"]),
    int(TG_CHANNELS["Pickle Cat's Den 🥒"]),
    int(TG_CHANNELS["Legandary 牛市卷王版本"]),
    int(TG_CHANNELS["AU Trading Journal 🩵😈"]),
}


@dataclass(frozen=True)
class TimeBudget:
    """Deadline-based budget (monotonic)."""

    start_s: float
    deadline_s: float

    @classmethod
    def start(cls, *, total_s: float) -> "TimeBudget":
        now = time.perf_counter()
        return cls(start_s=now, deadline_s=now + float(total_s))

    def elapsed_s(self) -> float:
        return max(0.0, time.perf_counter() - self.start_s)

    def remaining_s(self) -> float:
        return max(0.0, self.deadline_s - time.perf_counter())

    def over(self, *, reserve_s: float = 0.0) -> bool:
        return time.perf_counter() >= (self.deadline_s - float(reserve_s))


@dataclass
class PipelineContext:
    now_sh: dt.datetime
    now_utc: dt.datetime
    since: str
    until: str
    hour_key: str
    use_llm: bool

    client: TgClient
    budget: TimeBudget

    errors: List[str] = field(default_factory=list)
    perf: Dict[str, float] = field(default_factory=dict)

    # intermediate
    messages_by_chat: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    human_texts: List[str] = field(default_factory=list)

    oi_lines: List[str] = field(default_factory=list)
    oi_items: List[Dict[str, Any]] = field(default_factory=list)
    oi_plans: List[Dict[str, Any]] = field(default_factory=list)

    strong_threads: List[Dict[str, Any]] = field(default_factory=list)
    weak_threads: List[Dict[str, Any]] = field(default_factory=list)

    narratives: List[Dict[str, Any]] = field(default_factory=list)

    radar: Dict[str, Any] = field(default_factory=dict)
    radar_items: List[Dict[str, Any]] = field(default_factory=list)

    twitter_topics: List[Dict[str, Any]] = field(default_factory=list)

    threads: List[Dict[str, Any]] = field(default_factory=list)

    sentiment: str = ""
    watch: List[str] = field(default_factory=list)


def _sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _iso_z(t: dt.datetime) -> str:
    return t.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _measure(perf: Dict[str, float], name: str) -> Callable[[], None]:
    t0 = time.perf_counter()

    def done() -> None:
        perf[name] = round(time.perf_counter() - t0, 3)

    return done


def build_context(*, total_budget_s: float = 240.0) -> PipelineContext:
    now_sh = dt.datetime.now(SH_TZ)
    now_utc = now_sh.astimezone(UTC)

    since_utc = now_utc - dt.timedelta(minutes=60)
    since = _iso_z(since_utc)
    until = _iso_z(now_utc)

    use_llm = bool(load_openai_api_key())

    return PipelineContext(
        now_sh=now_sh,
        now_utc=now_utc,
        since=since,
        until=until,
        hour_key=now_sh.strftime("%Y-%m-%d %H:00"),
        use_llm=use_llm,
        client=TgClient(),
        budget=TimeBudget.start(total_s=total_budget_s),
    )


def _meme_radar_cmd() -> List[str]:
    return [
        "python3",
        str(scripts_path("meme_radar.py")),
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


def spawn_meme_radar(ctx: PipelineContext) -> Optional[subprocess.Popen[str]]:
    try:
        return subprocess.Popen(
            _meme_radar_cmd(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except Exception as e:
        ctx.errors.append(f"meme_radar_spawn_failed:{e}")
        return None


def _load_meme_radar_output(ctx: PipelineContext) -> Dict[str, Any]:
    path = memory_path("meme", "last_candidates.json")
    try:
        if not path.exists():
            ctx.errors.append("meme_radar_empty:no_output_file")
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        ctx.errors.append(f"meme_radar_read_failed:{e}")
        return {}


def wait_meme_radar(ctx: PipelineContext, proc: Optional[subprocess.Popen[str]]) -> None:
    done = _measure(ctx.perf, "meme_radar")
    try:
        if proc is not None:
            # Keep headroom for rendering / JSON output.
            timeout_s = min(170.0, max(5.0, ctx.budget.remaining_s() - 8.0))
            try:
                proc.wait(timeout=timeout_s)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                ctx.errors.append("meme_radar_timeout")
    finally:
        ctx.radar = _load_meme_radar_output(ctx)
        ctx.radar_items = list(ctx.radar.get("items") or [])
        done()


def require_tg_health(ctx: PipelineContext) -> None:
    if not ctx.client.health_ok():
        raise RuntimeError("TG service not healthy")


def fetch_tg_messages(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "tg_fetch_and_replay")

    since = ctx.since
    until = ctx.until

    # formula feed
    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    formula_msgs = ctx.client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    if not formula_msgs:
        try:
            ctx.client.replay(int(formula_id), limit=400, since=since, until=until)
        except Exception as e:
            ctx.errors.append(f"formula_replay_failed:{e}")
        formula_msgs = ctx.client.fetch_messages(int(formula_id), limit=240, since=since, until=until)
    ctx.messages_by_chat[formula_id] = formula_msgs

    # viewpoint chats
    for cid in sorted(VIEWPOINT_CHAT_IDS):
        s = str(cid)
        rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until)
        if not rows:
            try:
                ctx.client.replay(cid, limit=300, since=since, until=until)
            except Exception:
                pass
            rows = ctx.client.fetch_messages(cid, limit=260, since=since, until=until)
        ctx.messages_by_chat[s] = rows

    done()


def build_human_texts(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "human_texts")

    bot_ids = load_bot_sender_ids()
    out: List[str] = []

    for cid in VIEWPOINT_CHAT_IDS:
        for m in ctx.messages_by_chat.get(str(cid), []):
            sid = sender_id(m)
            if sid is not None and sid in bot_ids:
                continue
            t = msg_text(m)
            if not t or is_botish_text(t):
                continue
            out.append(t[:260])

    ctx.human_texts = out
    ctx.perf["viewpoint_threads_msgs_in"] = float(len(out))

    done()


def build_oi(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "oi_items")

    formula_id = TG_CHANNELS["方程式-OI&Price异动（抓庄神器）"]
    oi_signals = parse_oi_signals(ctx.messages_by_chat.get(formula_id, []))

    # Deterministic flow labels
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

    ctx.oi_items = build_oi_items(oi_signals=oi_signals, kline_fetcher=run_kline_json, top_n=5)

    def _fmt_pct(x: Any) -> str:
        return "?" if x is None else f"{float(x):+.1f}%"

    def _fmt_num(x: Any) -> str:
        if x is None:
            return "?"
        try:
            return f"{float(x):.4g}"
        except Exception:
            return str(x)

    lines: List[str] = []
    for it in ctx.oi_items[:5]:
        sym = it.get("symbol")
        px_now = it.get("price_now")
        oi24 = it.get("oi_24h")
        px24 = it.get("price_24h")
        lines.append(f"- {sym} 现价{_fmt_num(px_now)}；24h价{_fmt_pct(px24)}；24h OI{_fmt_pct(oi24)}")

    ctx.oi_lines = lines
    done()


def build_oi_plans_step(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "oi_plans")

    def time_budget_ok(reserve_s: float) -> bool:
        return not ctx.budget.over(reserve_s=reserve_s)

    ctx.oi_plans = build_oi_plans(
        use_llm=ctx.use_llm,
        oi_items=ctx.oi_items,
        llm_fn=summarize_oi_trading_plans,
        time_budget_ok=time_budget_ok,
        budget_s=45.0,
        top_n=3,
        errors=ctx.errors,
        tag="oi_plan",
    )

    done()


def build_viewpoint_threads(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "viewpoint_threads")
    t0 = time.perf_counter()
    vp = extract_viewpoint_threads(ctx.human_texts, min_heat=3, weak_heat=1)
    ctx.perf["viewpoint_threads_extract"] = round(time.perf_counter() - t0, 3)
    ctx.strong_threads = list(vp.get("strong") or [])
    ctx.weak_threads = list(vp.get("weak") or [])
    done()


def build_tg_topics(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "tg_topics_pipeline")

    def _tg_topic_postfilter(it: Dict[str, Any]) -> bool:
        one = str(it.get("one_liner") or "")
        if not one.strip():
            return False
        bad = ["某个", "某些", "一些", "不明", "有人", "群友", "大家", "市场参与者", "投资者", "用户"]
        return not any(x in one for x in bad)

    items: List[Dict[str, Any]] = []
    if ctx.use_llm and (not ctx.budget.over(reserve_s=85.0)):
        topics = build_topics(
            texts=ctx.human_texts,
            embeddings_fn=embeddings,
            cluster_fn=greedy_cluster,
            llm_summarizer=summarize_narratives,
            llm_items_key="items",
            prefilter=None,
            postfilter=_tg_topic_postfilter,
            max_clusters=10,
            threshold=0.82,
            embed_timeout=30,
            time_budget_ok=lambda lim: (not ctx.budget.over(reserve_s=lim)),
            budget_embed_s=55.0,
            budget_llm_s=65.0,
            llm_arg_name="tg_messages",
            errors=ctx.errors,
            tag="tg_topics",
        )

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
            items.append(
                {
                    "one_liner": str(one).strip(),
                    "sentiment": str(sen).strip(),
                    "triggers": str(tri).strip(),
                    "related_assets": [str(x) for x in rel[:6]],
                    "_inferred": False,
                }
            )

    # Replace contract addresses with resolved symbols when possible.
    if items:
        import re

        addr_re = re.compile(r"\b0x[a-fA-F0-9]{40}\b|\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
        cache: Dict[str, Optional[str]] = {}

        def _sub(text: str) -> str:
            if not text:
                return text

            def repl(m: re.Match[str]) -> str:
                a = m.group(0)
                if a in cache:
                    s = cache[a]
                else:
                    s = resolve_addr_symbol(a)
                    cache[a] = s
                return s or ""

            t2 = addr_re.sub(repl, text)
            t2 = re.sub(r"\s{2,}", " ", t2).strip()
            return t2

        for it in items:
            try:
                it["one_liner"] = _sub(str(it.get("one_liner") or ""))
                it["triggers"] = _sub(str(it.get("triggers") or ""))
            except Exception:
                pass

    ctx.narratives = items
    done()


def merge_tg_addr_candidates_into_radar(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "tg_addr_to_radar")
    import re

    evm_re = re.compile(r"\b0x[a-fA-F0-9]{40}\b")
    sol_re = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")

    addr_counts: Dict[str, int] = {}
    addr_examples: Dict[str, str] = {}

    for t in ctx.human_texts[:500]:
        if not t:
            continue
        for a in evm_re.findall(t):
            addr_counts[a] = addr_counts.get(a, 0) + 1
            addr_examples.setdefault(a, t[:220])
        for a in sol_re.findall(t):
            if not any(ch.isdigit() for ch in a):
                continue
            addr_counts[a] = addr_counts.get(a, 0) + 1
            addr_examples.setdefault(a, t[:220])

    tg_addr_items: List[Dict[str, Any]] = []
    for addr, cnt in sorted(addr_counts.items(), key=lambda kv: kv[1], reverse=True)[:12]:
        dexm = enrich_addr(addr)
        if not dexm:
            continue
        tg_addr_items.append(
            {
                "addr": addr,
                "mentions": cnt,
                "tickers": [dexm.get("baseSymbol")] if dexm.get("baseSymbol") else [],
                "examples": [{"handle": "TG", "text": addr_examples.get(addr, "")[:220]}],
                "dex": dexm,
                "sourceKey": f"TG:{addr}",
            }
        )

    seen_addr = {str(it.get("addr") or "") for it in ctx.radar_items}
    for it in tg_addr_items:
        a = str(it.get("addr") or "")
        if a and a not in seen_addr:
            ctx.radar_items.append(it)
            seen_addr.add(a)

    done()


def build_twitter_ca_topics(ctx: PipelineContext) -> None:
    """Twitter section: ONLY CA+$SYMBOL evidence for meme candidates."""

    done = _measure(ctx.perf, "twitter_ca_topics")

    ca_evidence_items: List[Dict[str, Any]] = []
    seen_key: set[str] = set()

    for it in ctx.radar_items[:25]:
        try:
            dex = it.get("dex") or {}
            sym = str(dex.get("baseSymbol") or "").upper().strip()
            ca = str(it.get("addr") or "").strip()
            ev = it.get("twitter_evidence") or {}
            snippets = (ev.get("snippets") or [])[:6]
            if not sym or not snippets:
                continue

            key = f"{sym}|{ca[:12]}" if ca else f"{sym}|-"
            if key in seen_key:
                continue
            seen_key.add(key)

            pack: Dict[str, Any] = {"sym": sym, "evidence": {"snippets": snippets}}
            if ca:
                pack["ca"] = ca
            ca_evidence_items.append(pack)
            if len(ca_evidence_items) >= 8:
                break
        except Exception:
            continue

    if not ca_evidence_items:
        ctx.twitter_topics = []
        done()
        return

    def _rule_one_liner(snips: List[str], *, sym: str) -> str:
        import re

        text = "\n".join([(s or "")[:240] for s in (snips or [])]).lower()
        text = re.sub(r"https?://\S+", " ", text)
        text = re.sub(r"\$\d+(?:\.\d+)?(?:[mk])?\b", " ", text)

        if any(k in text for k in ["rug", "scam", "hacked", "hack", "exploit"]):
            return f"{sym}: 有人质疑安全/诈骗风险，争论点集中在是否RUG/被黑"[:120]
        if any(k in text for k in ["rebrand", "rename", "changed name"]):
            return f"{sym}: 讨论集中在改名/品牌重塑，市场在评估是否利好注意力"[:120]
        if any(k in text for k in ["launch", "live", "listing", "binance", "alpha"]):
            return f"{sym}: 讨论集中在上线/上所/活动预期，情绪偏事件驱动"[:120]
        if any(k in text for k in ["lp", "liquidity", "add liquidity", "pool"]):
            return f"{sym}: 讨论集中在加池/流动性变化与短线拉砸博弈"[:120]
        if any(k in text for k in ["buy", "sell", "pump", "dump", "moon"]):
            return f"{sym}: 讨论以情绪/短线交易为主（追涨/砸盘分歧），缺少统一叙事"[:120]
        return f"{sym}: 社交讨论分散，未形成可复述的一致观点"[:120]

    def _rule_tags(snips: List[str], *, sym: str) -> List[str]:
        import re
        from collections import Counter

        txt = " ".join([(s or "")[:180] for s in (snips or [])])
        low = txt.lower()
        low = re.sub(r"https?://\S+", " ", low)
        low = re.sub(r"\$\d+(?:\.\d+)?(?:[mk])?\b", " ", low)

        tags: List[str] = []
        sym_u = (sym or "").upper().lstrip("$")
        if sym_u:
            tags.append(f"${sym_u}")

        kws = [
            ("binance alpha", "Binance Alpha"),
            ("cto", "CTO"),
            ("airdrop", "Airdrop"),
            ("rug", "RUG"),
            ("scam", "SCAM"),
            ("hack", "Hack"),
            ("exploit", "Exploit"),
            ("lp", "LP"),
            ("liquidity", "LP"),
            ("pump.fun", "pump.fun"),
            ("raydium", "Raydium"),
            ("uniswap", "Uniswap"),
        ]
        for k, v in kws:
            if k in low and v not in tags:
                tags.append(v)

        words = re.findall(r"[a-z]{3,}", low)
        stop = {
            "this",
            "that",
            "with",
            "from",
            "they",
            "them",
            "have",
            "just",
            "like",
            "will",
            "your",
            "youre",
            "dont",
            "does",
            "about",
            "what",
            "when",
            "then",
            "into",
            "over",
            "been",
            "much",
            "more",
            "very",
            "only",
            "still",
            "than",
            "also",
            "here",
            "there",
            "bull",
            "bear",
            "long",
            "short",
            "buy",
            "sell",
            "pump",
            "dump",
        }
        c = Counter([w for w in words if w not in stop])
        for w, _ in c.most_common(6):
            if w not in tags:
                tags.append(w)
            if len(tags) >= 6:
                break

        return tags[:6]

    def _rule_sentiment(tags: List[str]) -> str:
        bear = any(t in tags for t in ["RUG", "SCAM", "Hack", "Exploit"])  # type: ignore[truthy-bool]
        bull = any(t in tags for t in ["Binance Alpha", "Airdrop", "LP", "pump.fun"])  # type: ignore[truthy-bool]
        if bull and bear:
            return "分歧"
        if bull:
            return "偏多"
        if bear:
            return "偏空"
        return "中性"

    topics: List[Dict[str, Any]] = []
    for x in ca_evidence_items[:5]:
        sym = str(x.get("sym") or "").upper().strip()
        ca = str(x.get("ca") or "").strip()
        snips = ((x.get("evidence") or {}).get("snippets") or [])
        tags = _rule_tags(snips, sym=sym)
        sen = _rule_sentiment(tags)
        one = _rule_one_liner(snips, sym=sym)
        sig = "; ".join(tags[:8])
        if ca:
            sig = (sig + ("; " if sig else "") + f"CA:{ca[:6]}…")
        topics.append({"one_liner": one[:120], "sentiment": sen, "signals": sig[:160], "related_assets": []})

    # Optional LLM upgrade (replace one-liners/signals), within remaining budget.
    if ctx.use_llm and (not ctx.budget.over(reserve_s=120.0)):
        try:
            out = summarize_twitter_ca_viewpoints(items=ca_evidence_items)
            its = out.get("items") if isinstance(out, dict) else None
            if isinstance(its, list) and its:
                by_sym: Dict[str, Dict[str, Any]] = {
                    str(it.get("sym") or "").upper().strip(): it
                    for it in its
                    if isinstance(it, dict) and it.get("sym")
                }
                upgraded: List[Dict[str, Any]] = []
                for base_it in topics[:5]:
                    # base one_liner already contains 'SYM: ...'
                    base_one = str(base_it.get("one_liner") or "")
                    sym = base_one.split(":", 1)[0].strip().upper() if ":" in base_one else ""
                    it = by_sym.get(sym)
                    if not it:
                        upgraded.append(base_it)
                        continue
                    one2 = str(it.get("one_liner") or "").strip()
                    sen2 = str(it.get("sentiment") or "").strip() or str(base_it.get("sentiment") or "")
                    sig = it.get("signals")
                    if isinstance(sig, list):
                        sig2 = "; ".join([str(x) for x in sig[:8]])
                    else:
                        sig2 = str(sig or base_it.get("signals") or "")
                    upgraded.append(
                        {
                            "one_liner": f"{sym}: {one2}"[:120] if sym else one2[:120],
                            "sentiment": sen2,
                            "signals": sig2[:160],
                            "related_assets": [],
                        }
                    )
                topics = upgraded
            else:
                ctx.errors.append("tw_ca_viewpoints_llm_empty")
        except Exception as e:
            ctx.errors.append(f"tw_ca_viewpoints_llm_failed:{e}")

    ctx.twitter_topics = topics[:5]
    done()


def build_token_thread_summaries(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "token_thread_llm")

    strong = ctx.strong_threads or []
    weak = ctx.weak_threads or []

    token_threads = (strong[:3] if strong else weak[:3])

    llm_threads: List[Dict[str, Any]] = []

    should_llm = bool(ctx.use_llm and token_threads and strong and (not ctx.budget.over(reserve_s=70.0)))
    if should_llm:
        batch_in: List[Dict[str, Any]] = []
        for th in token_threads[:3]:
            sym = str(th.get("sym") or "").upper().strip()
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
            batch_in.append({"token": sym, "metrics": metrics, "telegram": msgs[:20], "twitter": []})

        try:
            bj = summarize_token_threads_batch(items=batch_in)
            outs = bj.get("items") if isinstance(bj, dict) else None
            out_map: Dict[str, Dict[str, Any]] = {}
            if isinstance(outs, list):
                for it in outs:
                    if isinstance(it, dict) and it.get("token"):
                        out_map[str(it.get("token") or "").upper()] = it

            for th in token_threads[:3]:
                sym = str(th.get("sym") or "").upper().strip()
                s = out_map.get(sym) or {}
                llm_threads.append(
                    {
                        "title": th.get("title"),
                        "stance": s.get("stance") or th.get("stance"),
                        "count": th.get("count"),
                        "sym": sym,
                        "thesis": s.get("thesis") or "",
                        "drivers": "; ".join(s.get("drivers") or []) if isinstance(s.get("drivers"), list) else (s.get("drivers") or ""),
                        "risks": "; ".join(s.get("risks") or []) if isinstance(s.get("risks"), list) else (s.get("risks") or ""),
                        "trade_implication": s.get("trade_implication") or "",
                        "points": th.get("points") or [],
                    }
                )
        except Exception as e:
            ctx.errors.append(f"llm_token_batch_failed:{e}")

    base_threads = (strong or []) + (weak or [])
    base_threads.sort(key=lambda x: -int(x.get("count") or 0))
    ctx.threads = llm_threads if llm_threads else base_threads

    done()


def infer_narrative_assets_from_tg(ctx: PipelineContext) -> None:
    """Best-effort asset linking for TG narratives, using TG-only token contexts."""

    done = _measure(ctx.perf, "narrative_asset_infer")

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


def compute_sentiment_and_watch(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "sentiment_watch")

    def _sent_score(s: Any) -> int:
        s2 = str(s or "").strip()
        if s2 == "偏多":
            return 1
        if s2 == "偏空":
            return -1
        return 0

    sc = 0
    n = 0
    for it in (ctx.narratives or [])[:5]:
        sc += _sent_score(it.get("sentiment"))
        n += 1
    for it in (ctx.twitter_topics or [])[:5]:
        sc += _sent_score(it.get("sentiment"))
        n += 1

    sentiment = "分歧"
    if n:
        if sc >= 2:
            sentiment = "偏多"
        elif sc <= -2:
            sentiment = "偏空"
        else:
            sentiment = "分歧"

    ctx.sentiment = sentiment

    watch: List[str] = []

    # OI first
    for ln in ctx.oi_lines[:5]:
        # format: "- SYMBOL ..."
        s = (ln or "").lstrip("- ").split(" ", 1)[0].strip().upper()
        if s and s not in watch:
            watch.append(s)

    # Then TG token threads
    for s in [str(t.get("sym") or "").upper().strip() for t in (ctx.threads or []) if t.get("sym")][:6]:
        if s and s not in watch:
            watch.append(s)

    # Then pinned assets from narratives
    for it in (ctx.narratives or [])[:5]:
        rel = it.get("related_assets")
        if isinstance(rel, list):
            for x in rel[:3]:
                xs = str(x).strip()
                if xs and xs not in watch:
                    watch.append(xs)

    ctx.watch = [x for x in watch if x][:3]
    done()


def render(ctx: PipelineContext) -> Dict[str, Any]:
    done = _measure(ctx.perf, "render")

    title = f"{ctx.now_sh.strftime('%H')}:00 二级山寨+链上meme"

    summary_whatsapp = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        twitter_lines=ctx.twitter_topics,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        whatsapp=True,
    )

    summary_markdown = build_summary(
        title=title,
        oi_lines=ctx.oi_lines,
        plans=ctx.oi_plans,
        narratives=ctx.narratives,
        threads=ctx.threads,
        weak_threads=ctx.weak_threads,
        twitter_lines=ctx.twitter_topics,
        overlap_syms=None,
        sentiment=ctx.sentiment,
        watch=ctx.watch,
        whatsapp=False,
    )

    tmp_md_path: str = ""
    try:
        tmp = Path("/tmp/clawdbot_hourly_summary.md")
        tmp.write_text(summary_markdown, encoding="utf-8")
        tmp_md_path = str(tmp)
    except Exception:
        tmp_md_path = ""

    summary_hash = _sha1(summary_whatsapp + "\n---\n" + summary_markdown)

    done()

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "summaryHash": summary_hash,
        "summary_whatsapp": summary_whatsapp,
        "summary_markdown": summary_markdown,
        "summary_markdown_path": tmp_md_path,
        "errors": ctx.errors,
        "elapsed_s": round(ctx.budget.elapsed_s(), 2),
        "perf": ctx.perf,
        "use_llm": bool(ctx.use_llm),
    }


def run_pipeline(*, total_budget_s: float = 240.0) -> Dict[str, Any]:
    ctx = build_context(total_budget_s=total_budget_s)

    meme_proc: Optional[subprocess.Popen[str]] = None
    try:
        require_tg_health(ctx)

        meme_proc = spawn_meme_radar(ctx)

        fetch_tg_messages(ctx)
        build_human_texts(ctx)
        build_oi(ctx)
        build_oi_plans_step(ctx)
        build_viewpoint_threads(ctx)
        build_tg_topics(ctx)

        wait_meme_radar(ctx, meme_proc)
        merge_tg_addr_candidates_into_radar(ctx)
        build_twitter_ca_topics(ctx)

        build_token_thread_summaries(ctx)
        infer_narrative_assets_from_tg(ctx)
        compute_sentiment_and_watch(ctx)

        return render(ctx)
    except Exception as e:
        # Ensure valid JSON even on fatal errors.
        try:
            if meme_proc is not None:
                meme_proc.kill()
        except Exception:
            pass

        ctx.errors.append(f"fatal:{type(e).__name__}:{e}")
        # Try to render something minimal; if render also fails, return a minimal object.
        try:
            if not ctx.sentiment:
                ctx.sentiment = "分歧"
            return render(ctx)
        except Exception as e2:
            return {
                "since": ctx.since,
                "until": ctx.until,
                "hourKey": ctx.hour_key,
                "summaryHash": "",
                "summary_whatsapp": "",
                "summary_markdown": "",
                "summary_markdown_path": "",
                "errors": ctx.errors + [f"fatal_render:{type(e2).__name__}:{e2}"],
                "elapsed_s": round(ctx.budget.elapsed_s(), 2),
                "perf": ctx.perf,
                "use_llm": bool(ctx.use_llm),
            }

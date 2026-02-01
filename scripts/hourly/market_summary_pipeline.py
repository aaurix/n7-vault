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
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from repo_paths import state_path, scripts_path

from hourly.bots import load_bot_sender_ids
from hourly.dexscreener import enrich_addr, enrich_symbol, resolve_addr_symbol
from hourly.filters import extract_symbols_and_addrs, is_botish_text, stance_from_texts
from hourly.kline_fetcher import run_kline_json
from hourly.perp_dashboard import build_perp_dash_inputs
from hourly.llm_openai import (
    load_chat_api_key,
    summarize_oi_trading_plans,
    summarize_token_threads_batch,
    summarize_tg_actionables,
    summarize_twitter_actionables,
)
from hourly.oi import parse_oi_signals
from hourly.oi_plan_pipeline import build_oi_items, build_oi_plans
from hourly.render import build_summary, split_whatsapp_text
from hourly.tg_client import TgClient, msg_text, sender_id
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
    llm_failures: List[str] = field(default_factory=list)
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
    tg_actionables_attempted: bool = False

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

    use_llm = bool(load_chat_api_key())

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
    path = state_path("meme", "last_candidates.json")
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
            out.append(t[:360])

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


_PII_RE = re.compile(r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|\+?\d[\d\-\s()]{7,}\d)")
_NOISE_RE = re.compile(
    r"(airdrop|giveaway|join\s+telegram|vip|signal|paid\s+group|link\s+in\s+bio|邀请码|私信|\bdm\b|抽奖|返佣)",
    re.IGNORECASE,
)


def _strip_pii(text: str) -> str:
    return _PII_RE.sub(" ", text or "")


def _clean_evidence_snippet(text: str, *, max_len: int = 80) -> str:
    t = _clean_snippet_text(text)
    if not t:
        return ""
    t = _strip_pii(t)
    t = _NOISE_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) < 6:
        return ""
    if len(t) > max_len:
        t = t[:max_len]
    return t


def _clean_snippet_text(text: str) -> str:
    t = re.sub(r"https?://\S+", " ", text or "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _prep_tg_snippets(texts: List[str], *, limit: int = 120) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for t in texts[:800]:
        t = _clean_snippet_text(t)
        if not t:
            continue
        syms, addrs = extract_symbols_and_addrs(t)
        anchor = ""
        if syms:
            anchor = syms[0]
        elif addrs:
            a = addrs[0]
            anchor = (a[:6] + "…" + a[-4:]) if len(a) >= 12 else a
        if anchor and not t.startswith(anchor):
            t = f"{anchor} | {t}"
        if len(t) > 220:
            t = t[:220]
        k = t.lower()[:120]
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _prep_twitter_snippets(items: List[Dict[str, Any]], *, limit: int = 120) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for it in items[:40]:
        ev = it.get("twitter_evidence") or {}
        snippets = ev.get("snippets") or []
        dex = it.get("dex") or {}
        sym = str(dex.get("baseSymbol") or it.get("symbol") or it.get("sym") or "").upper().strip()
        addr = str(it.get("addr") or "").strip()
        anchor = sym
        if not anchor and addr:
            anchor = (addr[:6] + "…" + addr[-4:]) if len(addr) >= 12 else addr
        for s in snippets[:6]:
            t = _clean_snippet_text(str(s))
            if not t:
                continue
            if anchor and not t.startswith(anchor):
                t = f"{anchor} | {t}"
            if len(t) > 220:
                t = t[:220]
            k = t.lower()[:120]
            if k in seen:
                continue
            seen.add(k)
            out.append(t)
            if len(out) >= limit:
                break
        if len(out) >= limit:
            break
    return out


def _sentiment_from_actionable(*, why_buy: str, why_not: str) -> str:
    if why_buy and why_not:
        return "分歧"
    if why_buy:
        return "偏多"
    if why_not:
        return "偏空"
    return "中性"


def _normalize_actionables(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _norm_text(val: Any, n: int) -> str:
        s = str(val or "")
        s = re.sub(r"\s+", " ", s).strip()
        return s[:n] if len(s) > n else s

    def _norm_evidence(ev: Any) -> List[str]:
        if isinstance(ev, str):
            ev_list = [x.strip() for x in re.split(r"[;；\n]", ev) if x.strip()]
        elif isinstance(ev, list):
            ev_list = [str(x).strip() for x in ev if str(x).strip()]
        else:
            ev_list = []
        cleaned: List[str] = []
        seen_ev: set[str] = set()
        for x in ev_list:
            t = _clean_evidence_snippet(x, max_len=80)
            if not t:
                continue
            k = t.lower()[:80]
            if k in seen_ev:
                continue
            seen_ev.add(k)
            cleaned.append(t)
            if len(cleaned) >= 2:
                break
        return cleaned

    for it in raw_items:
        if not isinstance(it, dict):
            continue
        asset = _norm_text(
            it.get("asset_name") or it.get("asset") or it.get("symbol") or it.get("token") or "",
            18,
        )
        why_buy = _norm_text(it.get("why_buy") or it.get("buy") or "", 42)
        why_not = _norm_text(it.get("why_not_buy") or it.get("why_not") or it.get("not_buy") or "", 42)
        trigger = _norm_text(it.get("trigger") or it.get("triggers") or "", 42)
        risk = _norm_text(it.get("risk") or it.get("risks") or "", 42)

        ev = it.get("evidence_snippets") or it.get("evidence") or it.get("snippets") or []
        ev_list = _norm_evidence(ev)

        if not asset and ev_list:
            syms, _addrs = extract_symbols_and_addrs(ev_list[0])
            if syms:
                asset = syms[0]

        asset = asset.lstrip("$").strip()
        if not asset:
            continue
        if len(asset) > 18:
            asset = asset[:18]
        if asset in seen:
            continue
        seen.add(asset)

        out.append(
            {
                "asset_name": asset,
                "why_buy": why_buy,
                "why_not_buy": why_not,
                "trigger": trigger,
                "risk": risk,
                "evidence_snippets": ev_list,
                "sentiment": _sentiment_from_actionable(why_buy=why_buy, why_not=why_not),
                "related_assets": [asset],
            }
        )

    return out


def self_check_actionables() -> Dict[str, Any]:
    """Lightweight self-check for actionable normalization (no LLM)."""

    sample_raw = [
        {
            "asset_name": "TESTCOINLONGNAMEEXCEED",
            "why_buy": "价格突破前高，资金净流入明显，交易所新增交易对，走势强势" * 2,
            "why_not_buy": "有解锁压力，社群分歧较大" * 2,
            "trigger": "突破前高并回踩确认",
            "risk": "消息噪音/情绪盘",
            "evidence_snippets": [
                "Testcoin to the moon! contact me at alpha@example.com",
                "Join telegram airdrop now!!!",
                "TEST 上所传闻升温，成交量放大",
            ],
        },
        {
            "asset": "DEMO",
            "buy": "资金关注",
            "not_buy": "",
            "trigger": "",
            "risk": "",
            "snippets": "DEMO 讨论升温；telegram群拉人",
        },
    ]

    normalized = _normalize_actionables(sample_raw)

    ok = True
    for it in normalized:
        if len(str(it.get("asset_name") or "")) > 18:
            ok = False
        for k in ["why_buy", "why_not_buy", "trigger", "risk"]:
            if len(str(it.get(k) or "")) > 42:
                ok = False
        ev = it.get("evidence_snippets") or []
        if len(ev) > 2 or any(len(str(x)) > 80 for x in ev):
            ok = False

    return {"ok": ok, "items": normalized}


def _fallback_actionables_from_texts(texts: List[str], *, limit: int = 5) -> List[Dict[str, Any]]:
    sym_hits: Dict[str, int] = {}
    sym_samples: Dict[str, List[str]] = {}

    for t in texts[:800]:
        syms, _addrs = extract_symbols_and_addrs(t)
        for s in syms[:2]:
            sym_hits[s] = sym_hits.get(s, 0) + 1
            sym_samples.setdefault(s, []).append(t)

    items: List[Dict[str, Any]] = []
    for sym, _cnt in sorted(sym_hits.items(), key=lambda kv: kv[1], reverse=True)[: max(1, limit)]:
        samples = sym_samples.get(sym, [])[:6]
        stance = stance_from_texts(samples)
        why_buy = "聊天偏多" if stance == "偏多" else ("多空分歧" if stance == "分歧" else "")
        why_not = "聊天偏空" if stance == "偏空" else ""
        ev = [_clean_evidence_snippet(s, max_len=80) for s in samples]
        ev = [x for x in ev if x]
        items.append(
            {
                "asset_name": sym,
                "why_buy": why_buy,
                "why_not_buy": why_not,
                "trigger": "关注关键位/催化",
                "risk": "消息噪音/情绪盘",
                "evidence_snippets": ev[:2],
                "sentiment": stance,
                "related_assets": [sym],
            }
        )
    return items[:limit]


def _fallback_actionables_from_radar(items: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for it in items[:25]:
        dex = it.get("dex") or {}
        sym = str(dex.get("baseSymbol") or it.get("symbol") or it.get("sym") or "").upper().strip()
        addr = str(it.get("addr") or "").strip()
        asset = sym
        if not asset and addr:
            asset = (addr[:6] + "…" + addr[-4:]) if len(addr) >= 12 else addr
        if not asset or asset in seen:
            continue
        ev = (it.get("twitter_evidence") or {}).get("snippets") or []
        ev2 = [_clean_evidence_snippet(str(s), max_len=80) for s in ev]
        ev2 = [x for x in ev2 if x][:2]
        if not ev2:
            continue
        out.append(
            {
                "asset_name": asset,
                "why_buy": "",
                "why_not_buy": "",
                "trigger": "",
                "risk": "",
                "evidence_snippets": ev2,
                "sentiment": "中性",
                "related_assets": [asset],
            }
        )
        seen.add(asset)
        if len(out) >= limit:
            break
    return out


def _log_llm_failure(ctx: PipelineContext, tag: str, *, raw: str = "", exc: Optional[BaseException] = None) -> None:
    ctx.errors.append(tag)
    detail = tag
    if exc is not None:
        detail += f":{type(exc).__name__}:{exc}"
    if raw:
        detail += f":raw_len={len(raw)}:raw_sha1={_sha1(raw)[:10]}"
    ctx.llm_failures.append(detail)


def build_tg_topics(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "tg_topics_pipeline")

    items: List[Dict[str, Any]] = []
    snippets = _prep_tg_snippets(ctx.human_texts, limit=120)
    ctx.perf["tg_snippets"] = float(len(snippets))

    if ctx.use_llm and snippets and (not ctx.budget.over(reserve_s=70.0)):
        ctx.tg_actionables_attempted = True
        try:
            out = summarize_tg_actionables(tg_snippets=snippets)
            raw_items = out.get("items") if isinstance(out, dict) else None
            parse_failed = bool(isinstance(out, dict) and out.get("_parse_failed"))
            raw = str(out.get("raw") or "") if isinstance(out, dict) else ""
            if parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_parse_failed", raw=raw)
            if isinstance(raw_items, list):
                items = _normalize_actionables(raw_items)
            elif isinstance(out, dict) and not parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_schema_invalid", raw=raw)
            if not items and not parse_failed:
                _log_llm_failure(ctx, "tg_actionables_llm_empty", raw=raw)
        except Exception as e:
            _log_llm_failure(ctx, "tg_actionables_llm_failed", exc=e)

    if not items:
        items = _fallback_actionables_from_texts(ctx.human_texts, limit=5)

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
    """Twitter actionables (aux supplement)."""

    done = _measure(ctx.perf, "twitter_ca_topics")

    items: List[Dict[str, Any]] = []
    snippets = _prep_twitter_snippets(ctx.radar_items, limit=120)
    ctx.perf["twitter_snippets"] = float(len(snippets))

    if ctx.use_llm and snippets and (not ctx.budget.over(reserve_s=95.0)):
        try:
            out = summarize_twitter_actionables(twitter_snippets=snippets)
            raw_items = out.get("items") if isinstance(out, dict) else None
            parse_failed = bool(isinstance(out, dict) and out.get("_parse_failed"))
            raw = str(out.get("raw") or "") if isinstance(out, dict) else ""
            if parse_failed:
                _log_llm_failure(ctx, "twitter_actionables_llm_parse_failed", raw=raw)
            if isinstance(raw_items, list):
                items = _normalize_actionables(raw_items)
            elif isinstance(out, dict) and not parse_failed:
                _log_llm_failure(ctx, "twitter_actionables_llm_schema_invalid", raw=raw)
            if not items and not parse_failed:
                _log_llm_failure(ctx, "twitter_actionables_llm_empty", raw=raw)
        except Exception as e:
            _log_llm_failure(ctx, "twitter_actionables_llm_failed", exc=e)

    if not items:
        items = _fallback_actionables_from_radar(ctx.radar_items, limit=5)

    ctx.twitter_topics = items[:5]
    done()


def build_token_thread_summaries(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "token_thread_llm")

    strong = ctx.strong_threads or []
    weak = ctx.weak_threads or []

    token_threads = (strong[:3] if strong else weak[:3])

    llm_threads: List[Dict[str, Any]] = []

    actionable_mode = bool(
        ctx.tg_actionables_attempted
        or (ctx.narratives and any(isinstance(it, dict) and it.get("asset_name") for it in ctx.narratives))
    )
    should_llm = bool(
        ctx.use_llm and token_threads and strong and (not ctx.budget.over(reserve_s=70.0)) and (not actionable_mode)
    )
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


def compute_sentiment_and_watch(ctx: PipelineContext) -> None:
    done = _measure(ctx.perf, "sentiment_watch")

    def _sent_score(s: Any) -> int:
        s2 = str(s or "").strip()
        if s2 == "偏多":
            return 1
        if s2 == "偏空":
            return -1
        return 0

    def _item_score(it: Any) -> int:
        if not isinstance(it, dict):
            return 0
        s = str(it.get("sentiment") or "").strip()
        if s:
            return _sent_score(s)
        buy = str(it.get("why_buy") or "").strip()
        not_buy = str(it.get("why_not_buy") or "").strip()
        return _sent_score(_sentiment_from_actionable(why_buy=buy, why_not=not_buy))

    sc = 0
    n = 0
    for it in (ctx.narratives or [])[:5]:
        sc += _item_score(it)
        n += 1
    for it in (ctx.twitter_topics or [])[:5]:
        sc += _item_score(it)
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
        asset = str(it.get("asset_name") or "").strip()
        if asset and asset not in watch:
            watch.append(asset)
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

    perp_dash_inputs: List[Dict[str, Any]] = []
    try:
        perp_dash_inputs = build_perp_dash_inputs(oi_items=ctx.oi_items, max_n=3)
    except Exception:
        perp_dash_inputs = []

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
        perp_dash_inputs=perp_dash_inputs,
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
        perp_dash_inputs=perp_dash_inputs,
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
    summary_whatsapp_chunks = split_whatsapp_text(summary_whatsapp, max_chars=950)

    done()

    return {
        "since": ctx.since,
        "until": ctx.until,
        "hourKey": ctx.hour_key,
        "summaryHash": summary_hash,
        "summary_whatsapp": summary_whatsapp,
        "summary_whatsapp_chunks": summary_whatsapp_chunks,
        "summary_markdown": summary_markdown,
        "summary_markdown_path": tmp_md_path,
        "errors": ctx.errors,
        "llm_failures": ctx.llm_failures,
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
                "summary_whatsapp_chunks": [],
                "summary_markdown": "",
                "summary_markdown_path": "",
                "errors": ctx.errors + [f"fatal_render:{type(e2).__name__}:{e2}"],
                "llm_failures": ctx.llm_failures,
                "elapsed_s": round(ctx.budget.elapsed_s(), 2),
                "perf": ctx.perf,
                "use_llm": bool(ctx.use_llm),
            }

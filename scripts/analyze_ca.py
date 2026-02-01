#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""On-demand contract address (CA) analysis.

Usage:
  python3 scripts/analyze_ca.py <CA>
  python3 scripts/analyze_ca.py <CA> --json

Design:
- Deterministic first: DexScreener metrics + basic TG/Twitter search counts.
- Optional 1 LLM call to summarize into trader-usable bullets (no raw quotes).
- Uses local Telegram MCP (hawkfi-telegram) via mcporter when available.

Notes:
- This script is for *on-demand* chat use. It does not affect cron.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ""))

from hourly.dexscreener import resolve_addr_symbol
from hourly.dexscreener import dexscreener_search, best_pair, pair_metrics
from hourly.llm_openai import load_openai_api_key, chat_json
from hourly.twitter_context import twitter_evidence_for_ca


EVM_CA_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOL_CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _dex_by_addr(addr: str) -> Optional[Dict[str, Any]]:
    pairs = dexscreener_search(addr)
    best = best_pair(pairs)
    if not best:
        return None
    return pair_metrics(best)


def _mcporter_search(q: str, *, limit: int = 80) -> List[Dict[str, Any]]:
    """Search local Telegram storage via hawkfi-telegram MCP.

    Returns list of TelegramMessage dicts when available, else [].
    """

    cmd = [
        "mcporter",
        "call",
        "hawkfi-telegram.search",
        "--json",
        f"q={q}",
        f"limit={limit}",
    ]
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=25)
        if p.returncode != 0:
            return []
        data = json.loads(p.stdout or "[]")
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _twitter_snips_for_ca(addr: str, sym: str) -> List[str]:
    ev = twitter_evidence_for_ca(addr, sym, intent="catalyst", window_hours=24, limit=12)
    snips = ev.get("snippets") if isinstance(ev, dict) else []
    return snips if isinstance(snips, list) else []


def render_text(report: Dict[str, Any]) -> str:
    ca = report.get("address") or ""
    sym = report.get("symbol") or ""
    dex = report.get("dex") or {}

    lines = [f"*CA 分析*", f"- 地址：{ca}"]
    if sym:
        lines.append(f"- Symbol：{sym}")

    if dex:
        lines.append(
            "- DEX：{chain}/{dex} | liq {liq} | vol24 {vol} | MC {mc} | FDV {fdv}".format(
                chain=dex.get("chainId") or "?",
                dex=dex.get("dexId") or "?",
                liq=dex.get("liquidityUsd") or "?",
                vol=dex.get("vol24h") or "?",
                mc=dex.get("marketCap") or "?",
                fdv=dex.get("fdv") or "?",
            )
        )
        if dex.get("url"):
            lines.append(f"- DexScreener：{dex.get('url')}")

    tg = report.get("telegram") or {}
    if tg:
        lines.append(f"- Telegram：命中 {tg.get('hits')} 条（本地库）")

    tw = report.get("twitter") or {}
    if tw:
        lines.append(f"- Twitter：抓取 {tw.get('count')} 条（搜索片段）")

    s = (report.get("summary") or "").strip()
    if s:
        lines.append("*总结*")
        lines.append(s)

    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("address")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    addr = args.address.strip()
    report: Dict[str, Any] = {"address": addr}

    sym = resolve_addr_symbol(addr) or ""
    report["symbol"] = sym

    dex = _dex_by_addr(addr) or {}
    report["dex"] = dex

    # Telegram MCP search (CA + symbol)
    tg_hits = []
    tg_hits = _mcporter_search(addr, limit=120)
    if sym:
        tg_hits2 = _mcporter_search(sym, limit=60)
        # merge by (chat_id,message_id)
        seen = set()
        merged: List[Dict[str, Any]] = []
        for m in (tg_hits + tg_hits2):
            k = (m.get("chat_id"), m.get("message_id"))
            if k in seen:
                continue
            seen.add(k)
            merged.append(m)
        tg_hits = merged

    report["telegram"] = {"hits": len(tg_hits)}

    # Twitter search (unified rule for meme): CA + $SYMBOL
    tw_snips = _twitter_snips_for_ca(addr, sym)
    report["twitter"] = {"count": len(tw_snips)}

    # Optional LLM summary
    if load_openai_api_key():
        try:
            system = (
                "你是加密交易员助手。输入是一个链上token的合约地址信息 + DexScreener指标 + Telegram本地库命中数量 + Twitter片段。\n"
                "请输出简短中文总结（<=8条要点），不要引用原话，不要输出链接，重点：叙事/风险/可交易性。"
            )
            user = {
                "address": addr,
                "symbol": sym,
                "dex": dex,
                "telegram_hits": len(tg_hits),
                "twitter_snippets": tw_snips[:8],
                "requirements": {"language": "zh", "no_quotes": True, "max_bullets": 8},
            }
            out = chat_json(system=system, user=json.dumps(user, ensure_ascii=False), max_tokens=360, timeout=25)
            report["summary"] = (out.get("summary") if isinstance(out, dict) else None) or json.dumps(out, ensure_ascii=False)
        except Exception:
            pass

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        print(render_text(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

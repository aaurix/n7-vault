from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional

from market_ops.adapters.dexscreener import best_pair, dexscreener_search, pair_metrics, resolve_addr_symbol
from market_ops.llm_openai import chat_json, load_chat_api_key
from market_ops.twitter_context import twitter_evidence_for_ca


EVM_CA_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
SOL_CA_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _dex_by_addr(addr: str) -> Optional[Dict[str, Any]]:
    pairs = dexscreener_search(addr)
    best = best_pair(pairs)
    if not best:
        return None
    return pair_metrics(best)


def _mcporter_search(q: str, *, limit: int = 80) -> List[Dict[str, Any]]:
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


def _render_text(report: Dict[str, Any]) -> str:
    ca = report.get("address") or ""
    sym = report.get("symbol") or ""
    dex = report.get("dex") or {}

    lines = ["*CA 分析*", f"- 地址：{ca}"]
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


def analyze_ca(address: str, allow_llm: bool = True) -> Dict[str, Any]:
    addr = (address or "").strip()
    errors: List[str] = []

    report: Dict[str, Any] = {"address": addr}

    sym = resolve_addr_symbol(addr) or ""
    report["symbol"] = sym

    dex = _dex_by_addr(addr) or {}
    report["dex"] = dex

    tg_hits = _mcporter_search(addr, limit=120)
    if sym:
        tg_hits2 = _mcporter_search(sym, limit=60)
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

    tw_snips = _twitter_snips_for_ca(addr, sym)
    report["twitter"] = {"count": len(tw_snips)}

    llm_used = False
    if allow_llm and load_chat_api_key():
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
            llm_used = True
        except Exception as e:
            errors.append(f"llm:{type(e).__name__}:{e}")

    text = _render_text(report)

    return {
        "data": report,
        "summary": text.strip(),
        "errors": errors,
        "use_llm": llm_used,
    }


__all__ = ["analyze_ca"]

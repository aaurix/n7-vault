#!/usr/bin/env python3
"""meme_radar.py

Goal: help 小E produce a meme shortlist by combining:
- Twitter (bird) mentions (cas/contract addresses, tickers)
- DexScreener token metrics (liq/vol/price change)
- (Optional) GMGN.ai links for further manual confirmation

This is an MVP: it does NOT scrape GMGN (site can change); it emits GMGN links.

Usage:
  python3 scripts/meme_radar.py --hours 12 --chains solana bsc base --limit 15

Outputs:
  - stdout: concise report
  - memory/meme/last_candidates.json: raw candidates
"""

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from zoneinfo import ZoneInfo

try:
    import urllib.request as urlreq
except Exception:  # pragma: no cover
    urlreq = None


SH_TZ = ZoneInfo("Asia/Shanghai")

# very simple patterns
EVM_CA_RE = re.compile(r"0x[a-fA-F0-9]{40}")
# Solana base58: 32-44 chars, exclude common words by requiring at least one digit
SOL_CA_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")
TICKER_RE = re.compile(r"\$[A-Za-z]{2,10}")

# exclude majors and common false positives from ticker-only search
TICKER_EXCLUDE = {
    "BTC","ETH","SOL","BNB","USDC","USDT","USD","DXY","CPI","PPI","FOMC","ETF",
}


def run(cmd: List[str]) -> str:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=35)
    if p.returncode != 0:
        # bird prints warnings to stderr; keep going unless hard fail
        # if stdout empty and returncode nonzero, bubble up
        if not p.stdout.strip():
            raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stderr}")
    return p.stdout


def parse_bird_time(s: str) -> Optional[dt.datetime]:
    if not s:
        return None
    # example: "Wed Jan 24 13:37:22 +0000 2024"
    try:
        return dt.datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except Exception:
        pass
    try:
        return dt.datetime.fromisoformat(s)
    except Exception:
        return None


def extract_twitter(hours: int, n: int) -> List[Dict[str, Any]]:
    # following timeline; JSON is easier to parse
    # bird occasionally returns truncated JSON for large n; retry with smaller n.
    # bird JSON can truncate for larger timelines; progressively reduce.
    tries = [n, max(80, n // 2), 80, 60, 40]
    obj = None
    last_err = None
    def _salvage_json(s: str):
        s = (s or "").strip()
        if not s:
            raise ValueError("empty")
        # bird may prepend/append warnings or truncate; attempt to salvage by trimming
        # to the first JSON bracket and the last closing bracket.
        start = min([i for i in [s.find("{"), s.find("[")] if i != -1] or [0])
        tail = max(s.rfind("}"), s.rfind("]"))
        if tail != -1:
            s2 = s[start : tail + 1]
        else:
            s2 = s[start:]
        return json.loads(s2)

    for nn in tries:
        out = run(["bird", "home", "--following", "-n", str(nn), "--json", "--quote-depth", "1"])
        try:
            obj = json.loads(out)
            break
        except Exception:
            try:
                obj = _salvage_json(out)
                break
            except Exception as e:
                last_err = e
                obj = None
    if obj is None:
        raise RuntimeError(f"Failed to parse bird JSON (last error: {last_err})")

    # heuristically locate list
    tweets = None
    if isinstance(obj, dict):
        for k in ["tweets", "data", "items", "results", "timeline", "entries"]:
            if k in obj and isinstance(obj[k], list):
                tweets = obj[k]
                break
    if tweets is None and isinstance(obj, list):
        tweets = obj
    tweets = tweets or []

    now = dt.datetime.now(SH_TZ)
    cut = now - dt.timedelta(hours=hours)

    rows = []
    for t in tweets:
        if not isinstance(t, dict):
            continue
        created = parse_bird_time(t.get("created_at") or t.get("createdAt") or t.get("time") or "")
        if not created:
            continue
        created_sh = created.astimezone(SH_TZ)
        if created_sh < cut:
            continue
        user = t.get("user") if isinstance(t.get("user"), dict) else {}
        handle = (user.get("screen_name") or user.get("username") or "").strip()
        text = (t.get("full_text") or t.get("text") or "").strip()
        rows.append(
            {
                "createdAt": created_sh.isoformat(),
                "handle": handle,
                "text": text,
                "id": str(t.get("id") or t.get("tweet_id") or ""),
            }
        )

    return rows


def detect_candidates(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Return dict keyed by address OR ticker placeholder.

    Keys can be:
      - "0x..." (EVM)
      - base58 (Solana)
      - "TICKER:<SYM>" when only $SYM is present
    """
    out: Dict[str, Dict[str, Any]] = {}

    for r in rows:
        text = r["text"]

        evms = EVM_CA_RE.findall(text)
        sols = [x for x in SOL_CA_RE.findall(text) if any(ch.isdigit() for ch in x)]
        tickers = [m[1:].upper() for m in TICKER_RE.findall(text)]

        if evms or sols:
            for ca in evms:
                key = ca.lower()
                out.setdefault(key, {"kind": "address", "chainHint": "evm", "mentions": 0, "examples": [], "tickers": []})
                out[key]["mentions"] += 1
                out[key]["examples"].append({"handle": r["handle"], "text": text[:220]})
                out[key]["tickers"] = sorted(set(out[key]["tickers"] + tickers))

            for ca in sols:
                key = ca
                out.setdefault(key, {"kind": "address", "chainHint": "solana", "mentions": 0, "examples": [], "tickers": []})
                out[key]["mentions"] += 1
                out[key]["examples"].append({"handle": r["handle"], "text": text[:220]})
                out[key]["tickers"] = sorted(set(out[key]["tickers"] + tickers))
        else:
            # ticker-only candidates
            for sym in tickers:
                if sym in TICKER_EXCLUDE:
                    continue
                key = f"TICKER:{sym}"
                out.setdefault(key, {"kind": "ticker", "symbol": sym, "mentions": 0, "examples": []})
                out[key]["mentions"] += 1
                out[key]["examples"].append({"handle": r["handle"], "text": text[:220]})

    for v in out.values():
        v["examples"] = v["examples"][:4]

    return out


def http_json(url: str) -> Any:
    req = urlreq.Request(url, headers={"User-Agent": "clawdbot-meme-radar/1.0"})
    with urlreq.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _best_pair(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not pairs:
        return None
    def liq(p):
        return (p.get("liquidity") or {}).get("usd") or 0
    # prefer higher liquidity, then higher volume
    return sorted(pairs, key=lambda p: (liq(p), (p.get("volume") or {}).get("h24") or 0), reverse=True)[0]


def _pair_to_metrics(best: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "chainId": best.get("chainId"),
        "dexId": best.get("dexId"),
        "pairAddress": best.get("pairAddress"),
        "url": best.get("url"),
        "baseSymbol": (best.get("baseToken") or {}).get("symbol"),
        "baseAddress": (best.get("baseToken") or {}).get("address"),
        "quoteSymbol": (best.get("quoteToken") or {}).get("symbol"),
        "liquidityUsd": (best.get("liquidity") or {}).get("usd"),
        "fdv": best.get("fdv"),
        "mcap": best.get("marketCap"),
        "priceUsd": best.get("priceUsd"),
        "vol24h": (best.get("volume") or {}).get("h24"),
        "txns24h": (best.get("txns") or {}).get("h24"),
        "chg1h": (best.get("priceChange") or {}).get("h1"),
        "chg24h": (best.get("priceChange") or {}).get("h24"),
    }


def dexscreener_token(addr: str) -> Optional[Dict[str, Any]]:
    """Fetch token page and return best-pair metrics."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
    try:
        data = http_json(url)
    except Exception:
        return None
    pairs = data.get("pairs") or []
    best = _best_pair(pairs)
    return _pair_to_metrics(best) if best else None


def dexscreener_search(symbol: str) -> List[Dict[str, Any]]:
    """Search by query (e.g., ticker). Returns list of pair metrics."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    try:
        data = http_json(url)
    except Exception:
        return []
    pairs = data.get("pairs") or []
    # map each pair
    out = []
    for p in pairs:
        try:
            out.append(_pair_to_metrics(p))
        except Exception:
            continue
    return out


def gmgn_link(chain: str, addr: str) -> str:
    # GMGN path patterns change; emit a best-effort generic link
    # User can paste addr into gmgn search if direct path fails.
    return f"https://gmgn.ai/?q={addr}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--chains", nargs="+", default=["solana", "bsc", "base"])
    ap.add_argument("--tweet-limit", type=int, default=250)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    rows = extract_twitter(hours=args.hours, n=args.tweet_limit)
    cands = detect_candidates(rows)

    chain_allow = [c.lower() for c in args.chains]

    enriched = []
    # process address candidates first (cheap)
    for key, meta in list(cands.items()):
        if meta.get("kind") == "address":
            addr = key
            d = dexscreener_token(addr)
            if not d:
                continue
            chain = (d.get("chainId") or "").lower()
            if chain and chain not in chain_allow:
                continue
            enriched.append({"addr": addr, "mentions": meta["mentions"], "tickers": meta.get("tickers", []), "examples": meta["examples"], "dex": d, "sourceKey": key})

    # ticker-only candidates can be numerous; cap API calls
    ticker_items = [(k, v) for k, v in cands.items() if v.get("kind") == "ticker"]
    ticker_items.sort(key=lambda kv: kv[1].get("mentions", 0), reverse=True)
    max_ticker_queries = 8
    for key, meta in ticker_items[:max_ticker_queries]:
        sym = meta.get("symbol")
        if not sym:
            continue
        pairs = dexscreener_search(sym)
        # Filter to allowed chains and try to avoid obvious false positives by matching baseSymbol
        pairs = [p for p in pairs if (p.get("chainId") or "").lower() in chain_allow]
        pairs = [p for p in pairs if (p.get("baseSymbol") or "").upper() == sym]
        if not pairs:
            continue
        best = sorted(pairs, key=lambda p: ((p.get("liquidityUsd") or 0), (p.get("vol24h") or 0)), reverse=True)[0]
        addr = best.get("baseAddress")
        if not addr:
            continue
        enriched.append({"addr": addr, "mentions": meta["mentions"], "tickers": [sym], "examples": meta["examples"], "dex": best, "sourceKey": key})

    # rank: mentions then liquidity then vol
    def score(x):
        liq = x["dex"].get("liquidityUsd") or 0
        vol = x["dex"].get("vol24h") or 0
        return (x["mentions"], liq, vol)

    enriched.sort(key=score, reverse=True)
    enriched = enriched[: args.limit]

    os.makedirs("memory/meme", exist_ok=True)
    open("memory/meme/last_candidates.json", "w").write(json.dumps({"generatedAt": dt.datetime.now(SH_TZ).isoformat(), "hours": args.hours, "items": enriched}, ensure_ascii=False, indent=2))

    print(f"链上Meme雷达（过去{args.hours}小时，来源：Following提及 → DexScreener验证）")
    if not enriched:
        print("- 本轮未抓到带合约地址/可被DexScreener识别的候选。")
        return 0

    for i, it in enumerate(enriched, 1):
        d = it["dex"]
        sym = d.get("baseSymbol") or "?"
        chain = d.get("chainId")
        liq = d.get("liquidityUsd")
        vol = d.get("vol24h")
        chg1h = d.get("chg1h")
        chg24h = d.get("chg24h")
        url = d.get("url")
        addr = it["addr"]

        print(f"\n{i}) {sym}  ({chain})")
        print(f"   CA: {addr}")
        print(f"   Dex: liq=${liq:.0f} vol24h=${vol:.0f} chg1h={chg1h}% chg24h={chg24h}%" if isinstance(liq,(int,float)) and isinstance(vol,(int,float)) else f"   Dex: {url}")
        if url:
            print(f"   DexScreener: {url}")
        print(f"   GMGN: {gmgn_link(chain or '', addr)}")
        if it["tickers"]:
            print(f"   Tickers: {', '.join(it['tickers'][:8])}")
        ex = it["examples"][0] if it["examples"] else None
        if ex:
            h = ex.get("handle") or ""
            tx = ex.get("text") or ""
            print(f"   引用: @{h} {tx[:140]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

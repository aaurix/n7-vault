#!/usr/bin/env python3
"""token_intel.py

Unified token analysis for 小E.

- If user provides an on-chain contract address (0x... or Solana base58), fetch DexScreener metrics,
  build GMGN link, and pull Twitter sentiment via bird search.
- If user provides an exchange-listed ticker (e.g., BTC, ETH, or CEX alt), the intended design is
  to fetch futures OI/funding/basis from Coinglass, plus Twitter sentiment.
  (Coinglass integration is left as a stub because it typically requires an API key and/or brittle scraping.)

Usage:
  python3 scripts/token_intel.py "潜龙勿用" --chain bsc
  python3 scripts/token_intel.py "0x2e591b13d3cAf27adf1dB47D75278315D0754444"

Outputs JSON to stdout.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request

EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")


def http_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={"User-Agent": "clawdbot-token-intel/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def dexscreener_search(q: str):
    url = "https://api.dexscreener.com/latest/dex/search?q=" + urllib.parse.quote(q)
    return http_json(url)


def dexscreener_token(addr: str):
    url = "https://api.dexscreener.com/latest/dex/tokens/" + addr
    return http_json(url)


def best_pair(pairs):
    if not pairs:
        return None

    def liq(p):
        return (p.get("liquidity") or {}).get("usd") or 0

    def vol(p):
        return (p.get("volume") or {}).get("h24") or 0

    return sorted(pairs, key=lambda p: (liq(p), vol(p)), reverse=True)[0]


def pair_metrics(p):
    return {
        "chainId": p.get("chainId"),
        "dexId": p.get("dexId"),
        "pairAddress": p.get("pairAddress"),
        "url": p.get("url"),
        "base": p.get("baseToken"),
        "quote": p.get("quoteToken"),
        "priceUsd": p.get("priceUsd"),
        "liquidityUsd": (p.get("liquidity") or {}).get("usd"),
        "fdv": p.get("fdv"),
        "marketCap": p.get("marketCap"),
        "volume24h": (p.get("volume") or {}).get("h24"),
        "txns24h": (p.get("txns") or {}).get("h24"),
        "priceChange": p.get("priceChange"),
        "pairCreatedAt": p.get("pairCreatedAt"),
        "info": p.get("info"),
    }


def bird_search(q: str, n: int = 30):
    try:
        out = subprocess.run(["bird", "search", q, "-n", str(n), "--plain"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return {"ok": out.returncode == 0, "stdout": out.stdout.strip(), "stderr": out.stderr.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def gmgn_link(addr: str):
    return f"https://gmgn.ai/?q={addr}"


def coinglass_stub(ticker: str):
    return {
        "supported": False,
        "reason": "Coinglass integration not configured. Typically requires API key or scraping.",
        "ticker": ticker,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", help="token name/ticker or contract address")
    ap.add_argument("--chain", default=None, help="hint: bsc/solana/base etc")
    ap.add_argument("--tweets", type=int, default=30)
    args = ap.parse_args()

    q = args.query.strip()

    result = {"query": q, "mode": None}

    # If it's a direct EVM contract address
    if EVM_RE.match(q):
        result["mode"] = "onchain"
        data = dexscreener_token(q)
        pairs = data.get("pairs") or []
        bp = best_pair(pairs)
        result["dex"] = pair_metrics(bp) if bp else None
        result["gmgn"] = gmgn_link(q)
        result["twitter"] = {
            "search": bird_search(q, n=args.tweets),
            "search_name": bird_search(result["dex"]["base"].get("name") if result.get("dex") else q, n=args.tweets),
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Otherwise try DexScreener search by name
    ds = dexscreener_search(q)
    pairs = ds.get("pairs") or []
    if args.chain:
        pairs = [p for p in pairs if (p.get("chainId") or "").lower() == args.chain.lower()]

    bp = best_pair(pairs)
    if bp:
        result["mode"] = "onchain"
        addr = (bp.get("baseToken") or {}).get("address")
        result["contract"] = addr
        result["dex"] = pair_metrics(bp)
        result["gmgn"] = gmgn_link(addr) if addr else None
        result["twitter"] = {
            "search": bird_search(q, n=args.tweets),
            "search_addr": bird_search(addr, n=args.tweets) if addr else None,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # Fallback: treat as CEX ticker
    result["mode"] = "cex"
    result["coinglass"] = coinglass_stub(q.upper())
    result["twitter"] = {"search": bird_search(q, n=args.tweets)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

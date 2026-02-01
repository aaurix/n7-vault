#!/usr/bin/env python3
"""meme_radar.py

Goal: help 小E produce a meme shortlist by combining:
- Twitter (bird) mentions (cas/contract addresses, tickers)
- DexScreener token metrics (liq/vol/price change)
- Standardized Twitter evidence for meme tokens: CA + $SYMBOL (via market_hourly.twitter_context)
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
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from repo_paths import state_path
from market_hourly.twitter_context import twitter_evidence_for_ca

from zoneinfo import ZoneInfo

import urllib.request as urlreq


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

# Resolve repo paths so cron CWD does not affect file IO.
_MEME_DIR: Path = state_path("meme")
DEX_CACHE_PATH: Path = _MEME_DIR / "dex_cache.json"
OUTPUT_PATH: Path = _MEME_DIR / "last_candidates.json"


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


# DEX_CACHE_PATH defined near top (absolute; cwd-independent)


def _load_dex_cache() -> Dict[str, Any]:
    try:
        if DEX_CACHE_PATH.exists():
            return json.loads(DEX_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"version": 1, "items": {}}


def _save_dex_cache(cache: Dict[str, Any]) -> None:
    try:
        DEX_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        DEX_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def http_json(url: str, *, cache: Optional[Dict[str, Any]] = None, ttl_s: int = 24 * 3600) -> Any:
    """HTTP JSON with basic retry/backoff + local cache.

    - DexScreener can rate-limit; cache results to reduce repeated calls.
    - Cache key is the full URL.
    """

    import time

    is_dex = "api.dexscreener.com" in (url or "")
    now = time.time()

    if is_dex and cache is not None:
        it = (cache.get("items") or {}).get(url)
        if isinstance(it, dict):
            ts = float(it.get("ts") or 0)
            if ts and (now - ts) <= ttl_s and "data" in it:
                return it.get("data")

    last_err = None
    for i in range(4):
        try:
            req = urlreq.Request(url, headers={"User-Agent": "clawdbot-meme-radar/1.0"})
            with urlreq.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if is_dex and cache is not None:
                cache.setdefault("items", {})
                cache["items"][url] = {"ts": now, "data": data}
            return data
        except Exception as e:
            last_err = e
            time.sleep(0.4 * (2**i))

    raise last_err


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


def dexscreener_token(addr: str, *, dex_cache: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Fetch token page and return best-pair metrics."""
    url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
    try:
        data = http_json(url, cache=dex_cache)
    except Exception:
        return None
    pairs = data.get("pairs") or []
    best = _best_pair(pairs)
    return _pair_to_metrics(best) if best else None


def dexscreener_search(symbol: str, *, dex_cache: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Search by query (e.g., ticker). Returns list of pair metrics."""
    url = f"https://api.dexscreener.com/latest/dex/search?q={symbol}"
    try:
        data = http_json(url, cache=dex_cache)
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
    import time
    perf = {}
    _t0 = time.perf_counter()

    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=12)
    ap.add_argument("--chains", nargs="+", default=["solana", "bsc", "base"])
    ap.add_argument("--tweet-limit", type=int, default=250)
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    dex_cache = _load_dex_cache()

    _t = time.perf_counter()
    rows = extract_twitter(hours=args.hours, n=args.tweet_limit)
    perf["extract_twitter"] = round(time.perf_counter() - _t, 3)

    _t = time.perf_counter()
    cands = detect_candidates(rows)
    perf["detect_candidates"] = round(time.perf_counter() - _t, 3)

    chain_allow = [c.lower() for c in args.chains]

    enriched = []

    # process address candidates first (parallelize dexscreener calls)
    addr_items = [(k, v) for k, v in cands.items() if v.get("kind") == "address"]
    _t = time.perf_counter()
    if addr_items:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_addr(kv):
            key, meta = kv
            addr = key
            d = dexscreener_token(addr, dex_cache=dex_cache)
            return (addr, meta, d, key)

        # DexScreener rate-limits: keep concurrency low.
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(_fetch_addr, kv) for kv in addr_items]
            for fu in as_completed(futs):
                try:
                    addr, meta, d, key = fu.result()
                except Exception:
                    continue
                if not d:
                    continue
                chain = (d.get("chainId") or "").lower()
                if chain and chain not in chain_allow:
                    continue
                enriched.append({"addr": addr, "mentions": meta.get("mentions", 0), "tickers": meta.get("tickers", []), "examples": meta.get("examples", []), "dex": d, "sourceKey": key})
    perf["dex_by_addr"] = round(time.perf_counter() - _t, 3)

    # ticker-only candidates can be numerous; cap API calls
    ticker_items = [(k, v) for k, v in cands.items() if v.get("kind") == "ticker"]
    ticker_items.sort(key=lambda kv: kv[1].get("mentions", 0), reverse=True)
    max_ticker_queries = 8
    _t = time.perf_counter()
    if ticker_items[:max_ticker_queries]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _fetch_sym(kv):
            key, meta = kv
            sym = meta.get("symbol")
            if not sym:
                return None
            pairs = dexscreener_search(sym, dex_cache=dex_cache)
            return (key, meta, sym, pairs)

        # DexScreener rate-limits: keep concurrency low.
        with ThreadPoolExecutor(max_workers=3) as ex:
            futs = [ex.submit(_fetch_sym, kv) for kv in ticker_items[:max_ticker_queries]]
            for fu in as_completed(futs):
                r = None
                try:
                    r = fu.result()
                except Exception:
                    continue
                if not r:
                    continue
                key, meta, sym, pairs = r
                pairs = pairs or []
                pairs = [p for p in pairs if (p.get("chainId") or "").lower() in chain_allow]
                pairs = [p for p in pairs if (p.get("baseSymbol") or "").upper() == sym]
                if not pairs:
                    continue
                best = sorted(pairs, key=lambda p: ((p.get("liquidityUsd") or 0), (p.get("vol24h") or 0)), reverse=True)[0]
                addr = best.get("baseAddress")
                if not addr:
                    continue
                enriched.append({"addr": addr, "mentions": meta.get("mentions", 0), "tickers": [sym], "examples": meta.get("examples", []), "dex": best, "sourceKey": key})
    perf["dex_by_symbol"] = round(time.perf_counter() - _t, 3)

    # rank: mentions then liquidity then vol
    def score(x):
        liq = x["dex"].get("liquidityUsd") or 0
        vol = x["dex"].get("vol24h") or 0
        return (x["mentions"], liq, vol)

    enriched.sort(key=score, reverse=True)
    enriched = enriched[: args.limit]

    # Attach standardized Twitter evidence for memes (parallel): CA + $SYMBOL
    _t = time.perf_counter()
    if twitter_evidence_for_ca is not None and enriched:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _ev_pack(it):
            d = it.get("dex") or {}
            sym = (d.get("baseSymbol") or "").upper().strip()
            addr = str(it.get("addr") or "").strip()
            if not sym or not addr:
                return (it, None)
            ev = twitter_evidence_for_ca(addr, sym, intent="catalyst", window_hours=24, limit=6)
            return (it, ev)

        # Twitter evidence is cheaper than Dex but still keep moderate concurrency.
        with ThreadPoolExecutor(max_workers=6) as ex:
            futs = [ex.submit(_ev_pack, it) for it in enriched[:10]]
            for fu in as_completed(futs):
                try:
                    it, ev = fu.result()
                except Exception:
                    continue
                if not ev:
                    continue
                it["twitter_evidence"] = {
                    "total": ev.get("total"),
                    "kept": ev.get("kept"),
                    "snippets": ev.get("snippets"),
                }
    perf["twitter_evidence"] = round(time.perf_counter() - _t, 3)

    _MEME_DIR.mkdir(parents=True, exist_ok=True)
    # Persist cache + output
    _save_dex_cache(dex_cache)

    open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8",
    ).write(
        json.dumps(
            {
                "generatedAt": dt.datetime.now(SH_TZ).isoformat(),
                "hours": args.hours,
                "items": enriched,
                "perf": perf,
                "elapsed_s": round(time.perf_counter() - _t0, 3),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

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

        tev = it.get("twitter_evidence") if isinstance(it, dict) else None
        if isinstance(tev, dict):
            kept = tev.get("kept")
            total = tev.get("total")
            if kept is not None or total is not None:
                print(f"   Twitter证据: {kept}/{total} (CA+$SYMBOL)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

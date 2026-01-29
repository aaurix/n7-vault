#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Text filters + entity extraction for TG viewpoints."""

from __future__ import annotations

import re
from typing import List, Tuple, Set


TICKER_DOLLAR_RE = re.compile(r"\$[A-Za-z]{2,10}")
TICKER_UPPER_RE = re.compile(r"\b[A-Z]{2,10}\b")
BASE58_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,}\b")
EVM_ADDR_RE = re.compile(r"\b0x[a-fA-F0-9]{40}\b")

TICKER_EXCLUDE = {
    "BTC",
    "ETH",
    "SOL",
    "BNB",
    "BSC",
    "BASE",
    "USDT",
    "USDC",
    "USD",
    "FDV",
    "MCAP",
    "DEX",
    "GMGN",
    "OI",
    "CA",
    "LP",
    "ATH",
    "ATL",
}

GENERIC_TOKENS = {"AI", "NFT", "CA", "MC", "FDV", "SOL", "ETH", "BTC", "BNB", "BSC", "BASE"}


def is_botish_text(s: str) -> bool:
    """Heuristic filter to drop bot spam/auto alerts.

    NOTE: do not reject short CA-only messages; those can be human.
    """

    if not s:
        return True
    s2 = s.strip()

    # Very long templated alerts
    if len(s2) > 260:
        return True

    # Box drawing / template markers
    if any(ch in s2 for ch in ["├", "└", "│", "┌", "┐", "┘", "┴"]):
        return True

    # Obvious stat blocks / bot commerce copy
    if any(x in s2 for x in ["📊", "📈", "Stats", "交易信息", "开盘时间", "MC", "FDV", "LP", "Vol", "ATH", "Sup", "DEX Paid"]):
        return True

    # CA dumps can be human too
    if BASE58_RE.search(s2) or EVM_ADDR_RE.search(s2):
        if len(s2) <= 90:
            return False
        return True

    # Links: short human messages may include 1 link
    if re.search(r"https?://", s2):
        if len(s2) <= 140:
            return False
        return True

    # Bot footer
    if any(x in s2 for x in ["dexscreener", "geckoterminal", "solscan", "defined.fi", "axiom.trade", "photon-sol", "trojan"]):
        return True

    return False


def extract_symbols_and_addrs(text: str) -> Tuple[List[str], List[str]]:
    """Extract tickers and base58 addresses from a message."""

    syms = [x[1:].upper() for x in TICKER_DOLLAR_RE.findall(text)]

    # If no $TICKER, fall back to uppercase sequences even inside CJK.
    # IMPORTANT: to avoid false positives (e.g. usernames like "ed"), require length>=3 here.
    # 2-letter symbols are only accepted when explicitly written as $XX.
    if not syms and len(text) <= 260:
        syms = [x.upper() for x in re.findall(r"[A-Z]{3,10}", text)]

    syms = [
        s
        for s in syms
        if s not in TICKER_EXCLUDE and s not in GENERIC_TOKENS and 2 <= len(s) <= 10
    ]
    addrs = BASE58_RE.findall(text) + EVM_ADDR_RE.findall(text)
    return syms, addrs


_SENT_POS = ["看好", "要起飞", "上车", "冲", "突破", "强", "继续拉", "做多", "买入", "梭哈", "all in", "bull"]
_SENT_NEG = ["看空", "别买", "别追", "风险", "砸", "骗", "rug", "跑路", "割", "出货", "做空", "bear"]


def stance_from_texts(texts: List[str]) -> str:
    pos = sum(1 for x in texts if any(k in x or k in x.lower() for k in _SENT_POS))
    neg = sum(1 for x in texts if any(k in x or k in x.lower() for k in _SENT_NEG))
    if pos >= 2 and pos > neg * 1.2:
        return "偏多"
    if neg >= 2 and neg > pos * 1.2:
        return "偏空"
    if pos or neg:
        return "分歧"
    return "中性"

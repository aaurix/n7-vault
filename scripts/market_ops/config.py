#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Hourly pipeline configuration (constants only)."""

from __future__ import annotations

from typing import Dict, Set
from zoneinfo import ZoneInfo


SH_TZ = ZoneInfo("Asia/Shanghai")
UTC = ZoneInfo("UTC")

DEFAULT_TOTAL_BUDGET_S = 240.0

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

VIEWPOINT_CHAT_IDS: Set[int] = {
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

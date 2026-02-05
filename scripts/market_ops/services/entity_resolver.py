#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Shared entity resolver for TG symbols + CA resolution."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from ..filters import extract_symbols_and_addrs
from scripts.market_data import DexBatcher, get_shared_dex_batcher


_EVM_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_BASE58_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def _allow_addr(addr: str, *, require_sol_digit: bool) -> bool:
    a = (addr or "").strip()
    if not a:
        return False
    if _EVM_RE.match(a):
        return True
    if _BASE58_RE.match(a):
        if not require_sol_digit:
            return True
        return any(ch.isdigit() for ch in a)
    return False


class EntityResolver:
    def __init__(self, dex: Optional[DexBatcher] = None) -> None:
        self.dex = dex or get_shared_dex_batcher()
        self._addr_cache: Dict[str, Optional[str]] = {}

    def extract_symbols_and_addrs(
        self,
        text: str,
        *,
        require_sol_digit: bool = False,
    ) -> Tuple[List[str], List[str]]:
        syms, addrs = extract_symbols_and_addrs(text)
        if require_sol_digit:
            addrs = [a for a in addrs if _allow_addr(a, require_sol_digit=True)]
        return syms, addrs

    def resolve_addr_symbol(self, addr: str) -> Optional[str]:
        key = (addr or "").strip()
        if not key:
            return None
        if key in self._addr_cache:
            return self._addr_cache[key]
        sym = self.dex.resolve_addr_symbol(key)
        self._addr_cache[key] = sym
        return sym

    def resolve_symbols_from_text(
        self,
        text: str,
        *,
        max_addrs: int = 2,
        require_sol_digit: bool = False,
    ) -> Tuple[List[str], List[str]]:
        syms, addrs = self.extract_symbols_and_addrs(text, require_sol_digit=require_sol_digit)
        resolved: List[str] = []
        for addr in addrs[:max_addrs]:
            rs = self.resolve_addr_symbol(addr)
            if rs:
                resolved.append(rs)
        return syms + resolved, addrs


_SHARED_RESOLVER: Optional[EntityResolver] = None


def get_shared_entity_resolver(dex: Optional[DexBatcher] = None) -> EntityResolver:
    global _SHARED_RESOLVER
    if _SHARED_RESOLVER is None:
        _SHARED_RESOLVER = EntityResolver(dex=dex)
    return _SHARED_RESOLVER


__all__ = ["EntityResolver", "get_shared_entity_resolver"]

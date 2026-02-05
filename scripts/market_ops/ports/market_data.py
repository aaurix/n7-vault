from market_ops.adapters.dexscreener import get_shared_dexscreener_client


def fetch_dex_market(addr: str, sym: str, dex=None) -> dict:
    dex = dex or get_shared_dexscreener_client()
    if addr:
        return dex.enrich_addr(addr) or {}
    if sym:
        return dex.enrich_symbol(sym) or {}
    return {}

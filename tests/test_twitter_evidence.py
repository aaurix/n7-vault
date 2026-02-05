from __future__ import annotations

from market_ops.services.twitter_evidence import _alias_hit, _build_queries, _is_relevant, TwitterQuerySpec


def test_alias_hit_contract_address() -> None:
    ca = "0x" + "a" * 40
    text = f"new ca {ca} just launched"
    assert _alias_hit(text, aliases=[ca], base="") is True


def test_is_relevant_for_ambiguous_ticker_requires_context() -> None:
    base = "PUMP"
    assert _is_relevant("pump is everywhere", aliases=[base], base=base) is False
    assert _is_relevant("watch $PUMP on perp chart", aliases=["$PUMP"], base=base) is True


def test_build_queries_drop_ambiguous_base() -> None:
    spec = TwitterQuerySpec(topic="alpha", aliases=["PUMP", "$PUMP", "PUMPUSDT"], intent="plan")
    queries = _build_queries(spec)
    assert any("$PUMP" in q for q in queries)
    assert all(" OR PUMP " not in q for q in queries)

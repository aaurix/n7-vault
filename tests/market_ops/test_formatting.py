from market_ops.core.formatting import fmt_pct, fmt_usd


def test_fmt_pct():
    assert fmt_pct(1.234) == "+1.2%"


def test_fmt_usd():
    assert fmt_usd(1500) == "$1.5K"

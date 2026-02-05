from scripts.market_ops.core.indicators import flow_label
from scripts.market_ops import perp_dashboard


def test_flow_label_up_up():
    assert flow_label(px_chg=2, oi_chg=6).startswith("多头加仓")


def test_flow_label_shared():
    assert perp_dashboard.flow_label is flow_label

from scripts.market_data.utils.kline_fetcher import summarize_klines


def test_summarize_klines_basic():
    kl = [
        [0, "1", "2", "1", "1", "10"],
        [1, "1", "3", "1", "2", "20"],
        [2, "2", "4", "2", "3", "30"],
        [3, "3", "5", "3", "4", "40"],
    ]
    out = summarize_klines(kl, interval="1h")
    assert out["interval"] == "1h"
    assert out["last"] == 4.0

from scripts.market_data import get_shared_exchange_batcher
from scripts.market_data.exchange.batcher import ExchangeBatcher
from scripts.market_data.onchain.batcher import DexBatcher
from scripts.market_data.social.batcher import SocialBatcher


def test_exchange_batcher_prefers_ccxt(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_ccxt.fetch_ohlcv",
        lambda *a, **k: [[1, 1, 1, 1, 1, 1]],
    )
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_binance.get_klines",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("binance used")),
    )
    b = ExchangeBatcher()
    rows = b.ohlcv("BTCUSDT", "1h", 2)
    assert rows


def test_exchange_batcher_oi_changes_uses_provider(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_binance.oi_changes",
        lambda s: {"oi_now": 1.0},
    )
    b = ExchangeBatcher()
    out = b.oi_changes("BTCUSDT")
    assert out["oi_now"] == 1.0


def test_exchange_batcher_price_changes_uses_provider(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_binance.price_changes",
        lambda s: {"px_now": 2.0},
    )
    b = ExchangeBatcher()
    out = b.price_changes("BTCUSDT")
    assert out["px_now"] == 2.0


def test_exchange_batcher_ticker_last_uses_ccxt(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_ccxt.fetch_ticker_last",
        lambda s, **k: 12.5,
    )
    b = ExchangeBatcher()
    out = b.ticker_last("BTCUSDT")
    assert out == 12.5


def test_exchange_batcher_mark_price_uses_binance(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.exchange.provider_binance.get_mark_price",
        lambda s: 99.0,
    )
    b = ExchangeBatcher()
    out = b.mark_price("BTCUSDT")
    assert out == 99.0


def test_dex_batcher_search_uses_provider(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.onchain.provider_dexscreener.dexscreener_search",
        lambda q, **k: [{"id": q}],
    )
    b = DexBatcher()
    rows = b.search("demo")
    assert rows == [{"id": "demo"}]


def test_dex_batcher_market_cap(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.onchain.provider_coingecko.get_market_cap_fdv",
        lambda sym: {"market_cap": 123},
    )
    b = DexBatcher()
    out = b.market_cap_fdv("SOL")
    assert out["market_cap"] == 123


def test_dex_batcher_resolve_addr_symbol(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.onchain.provider_dexscreener.resolve_addr_symbol",
        lambda addr: "ABC",
    )
    b = DexBatcher()
    assert b.resolve_addr_symbol("0x1") == "ABC"


def test_social_batcher_tg_client():
    b = SocialBatcher()
    client = b.tg_client()
    assert client is not None


def test_social_batcher_bird_search(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.social.provider_bird.bird_search",
        lambda q, **k: [{"text": q}],
    )
    b = SocialBatcher()
    out = b.bird_search("demo")
    assert out[0]["text"] == "demo"


def test_shared_exchange_batcher_singleton():
    a = get_shared_exchange_batcher()
    b = get_shared_exchange_batcher()
    assert a is b

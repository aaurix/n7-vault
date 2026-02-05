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


def test_dex_batcher_search_uses_provider(monkeypatch):
    monkeypatch.setattr(
        "scripts.market_data.onchain.provider_dexscreener.dexscreener_search",
        lambda q, **k: [{"id": q}],
    )
    b = DexBatcher()
    rows = b.search("demo")
    assert rows == [{"id": "demo"}]


def test_social_batcher_tg_client():
    b = SocialBatcher()
    client = b.tg_client()
    assert client is not None


def test_shared_exchange_batcher_singleton():
    a = get_shared_exchange_batcher()
    b = get_shared_exchange_batcher()
    assert a is b

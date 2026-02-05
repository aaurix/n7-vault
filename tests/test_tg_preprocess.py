from __future__ import annotations

from scripts.market_ops.services.tg_preprocess import prefilter_tg_topic_text, score_tg_cluster


def test_prefilter_accepts_event_and_symbol() -> None:
    text = "$ABC 解锁500万，需关注"
    assert prefilter_tg_topic_text(text) is True


def test_prefilter_rejects_noise() -> None:
    text = "今天天气不错，随便聊聊"
    assert prefilter_tg_topic_text(text) is False


def test_score_tg_cluster_rewards_size() -> None:
    base = {"text": "$XYZ 上所传闻升温", "_cluster_size": 1}
    larger = {"text": "$XYZ 上所传闻升温", "_cluster_size": 4}
    assert score_tg_cluster(larger) > score_tg_cluster(base)

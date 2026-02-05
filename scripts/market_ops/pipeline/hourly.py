from market_ops.pipeline.runner import PipelineRunner
from market_ops.pipeline.steps import (
    health_check,
    meme_spawn,
    tg_fetch,
    human_texts,
    oi_items,
    oi_plans,
    viewpoint_threads,
    tg_topics,
    twitter_following,
    meme_wait,
    tg_addr_merge,
    twitter_ca_topics,
    token_threads,
    narrative_assets,
    social_cards,
    sentiment_watch,
)


def run_hourly(ctx):
    steps = [
        ("health_check", health_check.step),
        ("meme_spawn", meme_spawn.step),
        ("tg_fetch", tg_fetch.step),
        ("human_texts", human_texts.step),
        ("oi_items", oi_items.step),
        ("oi_plans", oi_plans.step),
        ("viewpoint_threads", viewpoint_threads.step),
        ("tg_topics", tg_topics.step),
        ("twitter_following", twitter_following.step),
        ("meme_wait", meme_wait.step),
        ("tg_addr_merge", tg_addr_merge.step),
        ("twitter_ca_topics", twitter_ca_topics.step),
        ("token_threads", token_threads.step),
        ("narrative_assets", narrative_assets.step),
        ("social_cards", social_cards.step),
        ("sentiment_watch", sentiment_watch.step),
    ]
    PipelineRunner(ctx=ctx, steps=steps, continue_on_error=True).run()

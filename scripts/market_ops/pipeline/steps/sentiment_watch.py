from ...services.sentiment_watch import compute_sentiment_and_watch


def step(ctx):
    compute_sentiment_and_watch(ctx)

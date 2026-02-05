from ...features.topics.twitter import build_twitter_ca_topics


def step(ctx):
    build_twitter_ca_topics(ctx)

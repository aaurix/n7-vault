from ...features.meme_radar.service import wait_meme_radar


def step(ctx):
    wait_meme_radar(ctx, ctx.runtime.get("meme_proc"))

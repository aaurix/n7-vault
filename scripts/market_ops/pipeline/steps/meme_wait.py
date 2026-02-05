from ...services.meme_radar import wait_meme_radar


def step(ctx):
    wait_meme_radar(ctx, ctx.runtime.get("meme_proc"))

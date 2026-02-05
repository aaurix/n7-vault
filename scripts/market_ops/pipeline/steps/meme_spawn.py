from ...services.meme_radar import spawn_meme_radar


def step(ctx):
    ctx.runtime["meme_proc"] = spawn_meme_radar(ctx)

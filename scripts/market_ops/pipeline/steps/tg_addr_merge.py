from ...features.meme_radar.service import merge_tg_addr_candidates_into_radar


def step(ctx):
    merge_tg_addr_candidates_into_radar(ctx)

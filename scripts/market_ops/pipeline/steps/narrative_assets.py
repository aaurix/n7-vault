from ...services.narrative_assets import infer_narrative_assets_from_tg


def step(ctx):
    infer_narrative_assets_from_tg(ctx)

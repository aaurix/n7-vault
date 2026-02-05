from ...services.telegram_service import build_viewpoint_threads


def step(ctx):
    build_viewpoint_threads(ctx)

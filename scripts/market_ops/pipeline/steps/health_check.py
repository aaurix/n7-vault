from ...services.telegram_service import require_tg_health


def step(ctx):
    require_tg_health(ctx)

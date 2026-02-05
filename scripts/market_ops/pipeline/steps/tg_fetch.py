from ...services.telegram_service import fetch_tg_messages


def step(ctx):
    fetch_tg_messages(ctx)

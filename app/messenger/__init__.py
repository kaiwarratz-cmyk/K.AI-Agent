from app.messenger.discord import healthcheck as discord_healthcheck
from app.messenger.telegram import healthcheck as telegram_healthcheck

__all__ = ["telegram_healthcheck", "discord_healthcheck"]

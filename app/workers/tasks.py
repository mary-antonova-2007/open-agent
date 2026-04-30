from __future__ import annotations

import dramatiq
from dramatiq.brokers.redis import RedisBroker

from app.core.config import get_settings

redis_broker = RedisBroker(url=get_settings().redis_url)
dramatiq.set_broker(redis_broker)


@dramatiq.actor
def send_telegram_reminder(reminder_id: int) -> None:
    # Worker placeholder. The real implementation loads reminder, sends Telegram
    # notification, and updates delivery status.
    _ = reminder_id

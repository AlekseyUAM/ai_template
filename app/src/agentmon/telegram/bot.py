"""Long-poll цикл Telegram-бота."""
import asyncio
import logging

logger = logging.getLogger(__name__)


class TelegramBot:
    def __init__(self, client, handlers):
        self._client = client
        self._handlers = handlers
        self._offset = None

    async def poll_once(self) -> None:
        updates = await self._client.get_updates(offset=self._offset, timeout=25)
        for update in updates:
            try:
                await self._handlers.handle_update(update)
            except Exception:
                logger.exception("ошибка обработки апдейта %s", update.get("update_id"))
            self._offset = update["update_id"] + 1

    async def run(self, stop_event) -> None:
        last_error = None
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as exc:
                signature = (type(exc), str(exc))
                if signature != last_error:
                    logger.exception("цикл бота упал")
                    last_error = signature
                await asyncio.sleep(3.0)         # бэкофф на сетевых сбоях
            else:
                last_error = None

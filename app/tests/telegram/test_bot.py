import pytest
from agentmon.telegram.bot import TelegramBot


class _Client:
    def __init__(self, batches):
        self._batches = list(batches)
        self.offsets = []

    async def get_updates(self, offset=None, timeout=25):
        self.offsets.append(offset)
        return self._batches.pop(0) if self._batches else []


class _Handlers:
    def __init__(self):
        self.seen = []

    async def handle_update(self, update):
        self.seen.append(update)


@pytest.mark.asyncio
async def test_poll_once_advances_offset():
    client = _Client([[{"update_id": 5, "message": {}}, {"update_id": 6, "message": {}}]])
    handlers = _Handlers()
    bot = TelegramBot(client, handlers)
    await bot.poll_once()
    assert len(handlers.seen) == 2
    await bot.poll_once()                       # второй вызов — offset = 7
    assert client.offsets[1] == 7

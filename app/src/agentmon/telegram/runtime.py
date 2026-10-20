"""Сборка Telegram-компонентов и обёртки REST/отправки."""
import httpx

from agentmon import config
from agentmon.store.projects import ProjectRepo
from agentmon.telegram.client import BotClient
from agentmon.telegram.bot import TelegramBot
from agentmon.telegram.handlers import Handlers
from agentmon.telegram.notifier import TelegramNotifier


def notifier_send(client):
    async def _send(chat_id, text, reply_markup=None):
        await client.send_message(chat_id, text, reply_markup=reply_markup)
    return _send


def _api_poster():
    base = config.local_base_url()

    async def _post(path, json=None):
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(base + path, json=json or {})
            resp.raise_for_status()
            return resp.json()
    return _post


def build_bot(db, store, registry=None):
    if not config.TG_TOKEN:
        return None
    client = BotClient(config.TG_TOKEN, config.TG_API_BASE)
    projects = ProjectRepo(db)

    async def _send(chat_id, text, reply_markup=None):
        await client.send_message(chat_id, text, reply_markup=reply_markup)

    async def _answer(cq_id, text=None):
        await client.answer_callback(cq_id, text=text)

    def _base_path_of(project_id):
        p = projects.get(project_id)
        return p["path"] if p else None

    handlers = Handlers(db, _send, _answer, _api_poster(), config.TG_CHAT_IDS, _base_path_of)
    bot = TelegramBot(client, handlers)
    notifier = TelegramNotifier(db, notifier_send(client), config.TG_CHAT_IDS)
    return client, bot, notifier

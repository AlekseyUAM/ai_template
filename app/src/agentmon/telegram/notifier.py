"""Поллер-диффер статусов задач/стеков → уведомления в Telegram."""
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.telegram_store import NotifyStateRepo

logger = logging.getLogger(__name__)

TASK_EVENTS = {"running", "done", "failed", "awaiting_user"}
STACK_EVENTS = {"running", "idle", "completed"}

_TASK_LABEL = {
    "running": "▶️ Задача «{name}» запущена",
    "done": "✅ Задача «{name}» завершена",
    "failed": "❌ Задача «{name}» провалена",
    "awaiting_user": "⏸ Задача «{name}» ждёт пользователя (гейт)",
}
_STACK_LABEL = {
    "running": "▶️ Стек «{name}» запущен",
    "idle": "⏹ Стек «{name}» остановлен",
    "completed": "✅ Стек «{name}» выполнен",
}


class TelegramNotifier:
    def __init__(self, db, send, chat_ids):
        self._db = db
        self._send = send
        self._chat_ids = chat_ids
        self._state = NotifyStateRepo(db)
        self._tasks = TaskRepo(db)
        self._stacks = StackRepo(db)

    async def tick(self) -> None:
        await self._diff_tasks()
        await self._diff_stacks()

    async def _diff_tasks(self) -> None:
        for task in self._tasks.list():
            await self._handle("task", task["id"], task["status"],
                               TASK_EVENTS, _TASK_LABEL, {"name": task["name"]})

    async def _diff_stacks(self) -> None:
        for stack in self._stacks.list():
            status = self._stack_status(stack)
            await self._handle("stack", stack["id"], status,
                               STACK_EVENTS, _STACK_LABEL, {"name": stack["name"]})

    def _stack_status(self, stack) -> str:
        items = self._stacks.items(stack["id"])
        if items:
            done = all(self._tasks.get(i["task_id"]) and
                       self._tasks.get(i["task_id"])["status"] == "done" for i in items)
            if done:
                return "completed"
        return stack["status"]

    async def _handle(self, scope, ref_id, status, events, labels, fmt) -> None:
        prev = self._state.get(scope, ref_id)
        if prev is None:                         # baseline — молчим
            self._state.set(scope, ref_id, status)
            return
        if status == prev or status not in events:
            if status != prev:
                self._state.set(scope, ref_id, status)
            return
        text = labels[status].format(**fmt)
        if await self._emit(text):
            self._state.set(scope, ref_id, status)

    async def _emit(self, text: str) -> bool:
        ok = True
        for chat_id in self._chat_ids:
            try:
                await self._send(chat_id, text)
            except Exception:
                logger.exception("не удалось отправить уведомление в чат %s", chat_id)
                ok = False
        return ok

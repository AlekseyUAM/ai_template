"""Поллер-диффер статусов задач/стеков → уведомления в Telegram."""
import json
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.telegram_store import NotifyStateRepo
from agentmon.telegram.client import inline_keyboard

logger = logging.getLogger(__name__)


def gate_stage_name(task: dict):
    """Имя гейт-этапа, на котором задача ждёт пользователя.

    Повторяет условие `awaiting_user` из task_model.overall_status: первый
    включённый гейтированный этап в статусе done, ещё не approved, после
    которого есть включённый pending-этап. Нет такого — None.
    """
    try:
        stages = json.loads(task.get("stages_json") or "[]")
    except (ValueError, TypeError):
        return None
    enabled = [s for s in stages if s.get("enabled")]
    for i, stage in enumerate(enabled):
        if stage.get("gate") and stage.get("status") == "done" and not stage.get("approved"):
            if any(later.get("status") == "pending" for later in enabled[i + 1:]):
                return stage.get("name")
    return None


def _gate_keyboard(task_id, stage: str):
    # callback_data разбирает Handlers._route_callback (kind 'gate'): gate:<act>:<id>:<stage>
    return inline_keyboard([[
        ("✅ Одобрить", f"gate:ok:{task_id}:{stage}"),
        ("✍️ Замечание", f"gate:note:{task_id}:{stage}"),
    ]])

TASK_EVENTS = {"running", "done", "failed", "awaiting_user"}
STACK_EVENTS = {"running", "stopped", "completed", "idle"}

_TASK_LABEL = {
    "running": "▶️ Задача «{name}» запущена",
    "done": "✅ Задача «{name}» завершена",
    "failed": "❌ Задача «{name}» провалена",
    "awaiting_user": "⏸ Задача «{name}» ждёт пользователя (гейт)",
}
_STACK_LABEL = {
    "running": "▶️ Стек «{name}» запущен",
    "stopped": "⏹ Стек «{name}» остановлен",
    "completed": "✅ Стек «{name}» выполнен",
    "idle": "🏁 Стек «{name}» завершён",
}


class TelegramNotifier:
    def __init__(self, db, send, chat_ids):
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
            markup = None
            if task["status"] == "awaiting_user":
                stage = gate_stage_name(task)
                if stage:
                    markup = _gate_keyboard(task["id"], stage)
            await self._handle("task", task["id"], task["status"],
                               TASK_EVENTS, _TASK_LABEL, {"name": task["name"]},
                               reply_markup=markup)

    async def _diff_stacks(self) -> None:
        for stack in self._stacks.list():
            status = self._stack_status(stack)
            await self._handle("stack", stack["id"], status,
                               STACK_EVENTS, _STACK_LABEL, {"name": stack["name"]})

    def _stack_status(self, stack) -> str:
        items = self._stacks.items(stack["id"])
        if items:
            done = all(
                (task := self._tasks.get(i["task_id"])) and task["status"] == "done"
                for i in items
            )
            if done:
                return "completed"
        return stack["status"]

    async def _handle(self, scope, ref_id, status, events, labels, fmt,
                      reply_markup=None) -> None:
        prev = self._state.get(scope, ref_id)
        if prev is None:                         # baseline — молчим
            self._state.set(scope, ref_id, status)
            return
        if status == prev or status not in events:
            if status != prev:
                self._state.set(scope, ref_id, status)
            return
        text = labels[status].format(**fmt)
        if await self._emit(text, reply_markup):
            self._state.set(scope, ref_id, status)

    async def _emit(self, text: str, reply_markup=None) -> bool:
        ok = True
        for chat_id in self._chat_ids:
            try:
                await self._send(chat_id, text, reply_markup=reply_markup)
            except Exception:
                logger.exception("не удалось отправить уведомление в чат %s", chat_id)
                ok = False
        return ok

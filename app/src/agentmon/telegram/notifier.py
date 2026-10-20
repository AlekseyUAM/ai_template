"""Поллер-диффер статусов задач/стеков → уведомления в Telegram."""
import json
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.projects import ProjectRepo
from agentmon.store.telegram_store import NotifyStateRepo
from agentmon.telegram.client import inline_keyboard
from agentmon.telegram import reports as rep

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
        self._projects = ProjectRepo(db)

    async def tick(self) -> None:
        await self._diff_tasks()
        await self._diff_stacks()

    async def _diff_tasks(self) -> None:
        for task in self._tasks.list():
            messages = None
            if task["status"] == "awaiting_user":
                messages = self._gate_messages(task)
            await self._handle("task", task["id"], task["status"],
                               TASK_EVENTS, _TASK_LABEL, {"name": task["name"]},
                               messages=messages)

    def _gate_messages(self, task) -> list:
        """Сообщения гейта: содержимое артефакта этапа (нарезка по лимиту) +
        последним — prompt с кнопками [Одобрить]/[Замечание]."""
        prompt = _TASK_LABEL["awaiting_user"].format(name=task["name"])
        stage = gate_stage_name(task)
        if not stage:
            return [(prompt, None)]
        messages = []
        report = self._read_report(task, stage)
        if report:
            messages.append((f"📄 Отчёт этапа «{stage}»:", None))
            for part in rep.chunk(report):
                messages.append((part, None))
        messages.append((prompt, _gate_keyboard(task["id"], stage)))
        return messages

    def _read_report(self, task, stage: str):
        project = self._projects.get(task["project_id"])
        if project is None:
            return None
        try:
            return rep.read_report(project["path"], task, stage)
        except OSError:
            return None

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
                      messages=None) -> None:
        prev = self._state.get(scope, ref_id)
        if prev is None:                         # baseline — молчим
            self._state.set(scope, ref_id, status)
            return
        if status == prev or status not in events:
            if status != prev:
                self._state.set(scope, ref_id, status)
            return
        # messages: список (текст, клавиатура). По умолчанию — одно сообщение
        # из метки статуса без клавиатуры.
        msgs = messages if messages is not None else [(labels[status].format(**fmt), None)]
        if await self._emit(msgs):
            self._state.set(scope, ref_id, status)

    async def _emit(self, messages) -> bool:
        ok = True
        for chat_id in self._chat_ids:
            for text, reply_markup in messages:
                try:
                    await self._send(chat_id, text, reply_markup=reply_markup)
                except Exception:
                    logger.exception("не удалось отправить уведомление в чат %s", chat_id)
                    ok = False
        return ok

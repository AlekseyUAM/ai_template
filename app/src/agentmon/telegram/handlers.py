"""Разбор апдейтов Telegram: команды и callback-кнопки."""
import logging

from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.store.projects import ProjectRepo
from agentmon.telegram import reports as rep
from agentmon.telegram.client import inline_keyboard
from agentmon.telegram.feedback import save_feedback

logger = logging.getLogger(__name__)


class Handlers:
    def __init__(self, db, send, answer, api_post, chat_ids, base_path_of):
        self._db = db
        self._send = send
        self._answer = answer
        self._api_post = api_post            # async (path, json=None) -> dict
        self._chat_ids = set(str(c) for c in chat_ids)
        self._base_path_of = base_path_of
        self._tasks = TaskRepo(db)
        self._stacks = StackRepo(db)
        self._projects = ProjectRepo(db)
        self._pending_feedback = {}          # chat_id(str) -> (task_id, stage)

    def _authorized(self, chat_id) -> bool:
        return str(chat_id) in self._chat_ids

    async def handle_update(self, update: dict) -> None:
        if "callback_query" in update:
            await self._on_callback(update["callback_query"])
        elif "message" in update:
            await self._on_message(update["message"])

    # --- сообщения/команды ---

    async def _on_message(self, msg: dict) -> None:
        chat_id = str(msg.get("chat", {}).get("id"))
        if not self._authorized(chat_id):
            return
        text = (msg.get("text") or "").strip()

        if chat_id in self._pending_feedback:          # ждём текст замечания
            task_id, stage = self._pending_feedback.pop(chat_id)
            await self._accept_feedback(chat_id, task_id, stage, text)
            return

        if text.startswith("/start"):
            await self._send(chat_id, "AgentMon на связи. Команды: /projects /tasks /stacks")
        elif text.startswith("/projects"):
            await self._list_projects(chat_id)
        elif text.startswith("/tasks"):
            await self._list_tasks(chat_id)
        elif text.startswith("/stacks"):
            await self._list_stacks(chat_id)

    async def _list_projects(self, chat_id) -> None:
        lines = [f"#{p['id']} {p['name']} — {p['path']}" for p in self._projects.list()]
        await self._send(chat_id, "\n".join(lines) or "Проектов нет")

    async def _list_tasks(self, chat_id) -> None:
        for t in self._tasks.list():
            kb = inline_keyboard([[("📄 Отчёты", f"tsk:report:{t['id']}")]])
            await self._send(chat_id,
                             f"#{t['id']} {t['name']} — {t['status']} / {t.get('stage') or '—'}",
                             reply_markup=kb)

    async def _list_stacks(self, chat_id) -> None:
        for s in self._stacks.list():
            buttons = [("▶️ Запустить/Продолжить", f"stk:start:{s['id']}"),
                       ("⏹ Остановить", f"stk:stop:{s['id']}")]
            await self._send(chat_id, f"Стек «{s['name']}» — {s['status']}",
                             reply_markup=inline_keyboard([buttons]))

    # --- callback-кнопки ---

    async def _on_callback(self, cq: dict) -> None:
        chat_id = str(cq.get("message", {}).get("chat", {}).get("id"))
        cq_id = cq.get("id")
        if not self._authorized(chat_id):
            return
        data = cq.get("data") or ""
        try:
            await self._route_callback(chat_id, data)
        finally:
            await self._answer(cq_id)

    async def _route_callback(self, chat_id, data: str) -> None:
        parts = data.split(":")
        kind = parts[0]
        if kind == "stk":
            if len(parts) != 3:
                await self._send(chat_id, "неизвестная команда")
                return
            _, action, sid = parts
            if action == "start":
                await self._api_post(f"/api/env/stacks/{sid}/start")
                await self._send(chat_id, f"Стек {sid}: запуск/продолжение")
            elif action == "stop":
                await self._api_post(f"/api/env/stacks/{sid}/stop")
                await self._send(chat_id, f"Стек {sid}: остановлен")
        elif kind == "tsk":
            if len(parts) != 3 or parts[1] != "report":
                await self._send(chat_id, "неизвестная команда")
                return
            await self._report_menu(chat_id, int(parts[2]))
        elif kind == "rep":
            if len(parts) != 3:
                await self._send(chat_id, "неизвестная команда")
                return
            await self._show_report(chat_id, int(parts[1]), parts[2])
        elif kind == "gate":
            if len(parts) != 4:
                await self._send(chat_id, "неизвестная команда")
                return
            action, task_id, stage = parts[1], int(parts[2]), parts[3]
            if action == "ok":
                await self._api_post(f"/api/env/tasks/{task_id}/approve", json={"stage": stage})
                await self._send(chat_id, "Гейт одобрен")
            elif action == "note":
                self._pending_feedback[chat_id] = (task_id, stage)
                await self._send(chat_id, "Пришлите текст замечания одним сообщением")
        else:
            await self._send(chat_id, "неизвестная команда")

    async def _report_menu(self, chat_id, task_id: int) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            await self._send(chat_id, "Задача не найдена")
            return
        rows = [[(s["name"], f"rep:{task_id}:{s['name']}")] for s in rep.enabled_stages(task)]
        await self._send(chat_id, f"Отчёты задачи #{task_id}:",
                         reply_markup=inline_keyboard(rows or [[("нет этапов", "noop")]]))

    async def _show_report(self, chat_id, task_id: int, stage: str) -> None:
        task = self._tasks.get(task_id)
        path = self._base_path_of(task["project_id"]) if task else None
        text = rep.read_report(path, task, stage) if (task and path) else None
        if not text:
            await self._send(chat_id, "Артефакт этапа пуст или отсутствует")
            return
        for part in rep.chunk(text):
            await self._send(chat_id, part)

    async def _accept_feedback(self, chat_id, task_id: int, stage: str, text: str) -> None:
        task = self._tasks.get(task_id)
        path = self._base_path_of(task["project_id"]) if task else None
        if not (task and path):
            await self._send(chat_id, "Задача не найдена")
            return
        save_feedback(self._db, path, task, chat_id, text)
        await self._api_post(f"/api/env/tasks/{task_id}/approve", json={"stage": stage})
        await self._send(chat_id, "Замечание сохранено, гейт одобрен")

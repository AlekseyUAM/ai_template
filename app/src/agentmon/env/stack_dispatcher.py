"""Стек-раннер: обходит running-стеки и последовательно запускает их задачи.

Параллельность между стеками обеспечивается тиком (несколько стеков двигаются
одновременно); внутри стека задачи выполняются строго последовательно.

Project-lock: задачи одного проекта не выполняются параллельно. Если для
проекта уже есть живой прогон (monitor.is_alive), текущий стек пропускается
до следующего тика.
"""

import logging
import sys
import time
from types import SimpleNamespace

from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.env import task_schema

logger = logging.getLogger(__name__)

# статусы, считающиеся завершёнными для задачи
_DONE_STATUSES = {"done", "failed"}


def _build_proj(project_row) -> SimpleNamespace:
    """Строит лёгкий объект проекта из словаря ProjectRepo.get()."""
    return SimpleNamespace(
        id=project_row["id"],
        path=project_row["path"],
        name=project_row["name"],
        # ключ для бэкенда — формат local||<path>
        key="local||" + project_row["path"],
        backend="local",
        claude_cmd=None,
    )


class StackDispatcher:
    """Тикающий раннер стеков выполнения.

    Параметры
    ---------
    store : Db
        Адаптер БД (agentmon.store.db.Db); используется для создания репозиториев.
    monitor : Monitor-подобный объект
        Должен поддерживать start(project, prompt, task_id, cmd), is_alive(project),
        task_status(task_id).
    now_fn : callable, опционально
        Функция, возвращающая текущее время (по умолчанию time.time). Используется
        для совместимости с тестами, требующими детерминированного времени.
    """

    def __init__(self, store, monitor, now_fn=time.time):
        self._store = store
        self._monitor = monitor
        self._now_fn = now_fn

    def tick(self) -> None:
        """Один проход по всем running-стекам.

        Для каждого стека:
        - ищет первую незавершённую задачу (статус не в {done, failed});
        - если таких нет — переводит стек в idle;
        - если проект задачи занят другим живым прогоном — пропускает стек;
        - если задача planned/queued — запускает через monitor;
        - если задача running — проверяет monitor.task_status и при необходимости
          обновляет статус задачи.
        """
        sr = StackRepo(self._store)
        tr = TaskRepo(self._store)
        pr = ProjectRepo(self._store)

        # перебираем только running-стеки
        for stack in sr.list():
            if stack["status"] != "running":
                continue
            try:
                self._tick_stack(stack, sr, tr, pr)
            except Exception:
                logger.exception("ошибка тика стека id=%s", stack["id"])

    def _tick_stack(self, stack, sr, tr, pr) -> None:
        """Обрабатывает один running-стек (итеративно, без рекурсии)."""
        stack_id = stack["id"]

        while True:
            items = sr.items(stack_id)  # отсортированы по position

            # ищем первую незавершённую задачу
            active_item = None
            active_task = None
            for item in items:
                task = tr.get(item["task_id"])
                if task is None:
                    continue
                if task["status"] not in _DONE_STATUSES:
                    active_item = item
                    active_task = task
                    break

            # все задачи стека завершены → стек становится idle
            if active_task is None:
                sr.set_status(stack_id, "idle")
                logger.debug("стек id=%s завершён → idle", stack_id)
                return

            # получаем проект задачи
            project_row = pr.get(active_task["project_id"])
            if project_row is None:
                logger.warning("проект id=%s не найден, пропускаем стек id=%s",
                               active_task["project_id"], stack_id)
                return
            proj = _build_proj(project_row)

            task_id = active_task["id"]
            status = active_task["status"]

            if status in {"planned", "queued"}:
                # project-lock: если для этого проекта уже есть живой прогон — ждём
                if self._monitor.is_alive(proj):
                    logger.debug(
                        "project-lock: проект %s занят, стек id=%s ждёт",
                        proj.id, stack_id,
                    )
                    return
                # запускаем задачу и выходим — один старт за тик
                self._start_task(proj, active_task, tr)
                return

            else:  # running
                # Жёсткий таймаут: прогон дольше max_minutes снимается и
                # помечается failed, стек двигается к следующей задаче.
                max_minutes = active_task.get("max_minutes") or 0
                if max_minutes and self._monitor.enforce_timeout(task_id, max_minutes):
                    tr.set_status(task_id, "failed")
                    logger.info("задача id=%s прервана по таймауту (%s мин)",
                                task_id, max_minutes)
                    continue
                # задача запущена — проверяем, не завершилась ли
                run_status = self._monitor.task_status(task_id)
                if run_status == "done":
                    tr.set_status(task_id, "done")
                    logger.debug("задача id=%s помечена done", task_id)
                    # продолжаем цикл — сдвигаемся к следующей задаче в этом же тике
                    continue
                elif run_status == "failed":
                    tr.set_status(task_id, "failed")
                    logger.debug("задача id=%s помечена failed", task_id)
                    # продолжаем цикл — сдвигаемся к следующей задаче в этом же тике
                    continue
                else:
                    # задача ещё выполняется — ждём следующего тика
                    return

    def _start_task(self, proj, task, tr) -> None:
        """Запускает задачу через monitor и обновляет её статус."""
        task_id = task["id"]
        kind = task.get("kind", "real")

        if kind == "test":
            # тестовая задача — sleep-заглушка
            cmd = [sys.executable, "-c", "import time; time.sleep(60)"]
            self._monitor.start(proj, cmd=cmd, task_id=task_id)
        else:
            # реальная задача — промпт оркестрации (каталог по идентификатору)
            prompt = task_schema.orchestration_prompt(task_id, task.get("identifier"))
            self._monitor.start(proj, prompt, task_id=task_id)

        tr.set_status(task_id, "running")
        logger.debug("задача id=%s запущена (kind=%s)", task_id, kind)

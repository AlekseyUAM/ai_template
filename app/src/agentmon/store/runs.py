"""Репозиторий прогонов поверх адаптера Db.

Переносит семантику RunStore (run_store.py) на новый адаптер: add/running/finish/get/latest_for_task.
"""
import time


class RunRepo:
    """CRUD-обёртка над таблицей runs."""

    def __init__(self, db, clock=time.time):
        # сохраняем ссылку на адаптер БД
        self._db = db
        # clock для подстановки времени; по умолчанию time.time — записываем реальное время
        self._clock = clock

    def add(
        self,
        project_id: int,
        pid: int,
        *,
        task_id=None,
        log_file=None,
        exit_file=None,
        now=None,
    ) -> int:
        """Создаёт запись о прогоне со статусом 'running', возвращает run_id.

        now=None — берём значение из clock (если задан) или не пишем время.
        """
        # определяем время старта: явный аргумент, затем clock, затем None
        started_at = now if now is not None else (
            self._clock() if self._clock is not None else None
        )
        return self._db.returning_id(
            "runs",
            ["project_id", "task_id", "pid", "log_file", "exit_file",
             "status", "started_at"],
            [project_id, task_id, pid, log_file, exit_file,
             "running", started_at],
        )

    def running(self, project_id=None) -> list[dict]:
        """Возвращает все прогоны со статусом 'running'.

        project_id=None — все проекты.
        """
        if project_id is None:
            return self._db.query("SELECT * FROM runs WHERE status='running'")
        return self._db.query(
            "SELECT * FROM runs WHERE status='running' AND project_id=?",
            [project_id],
        )

    def finish(self, run_id: int, status: str, exit_code=None, now=None) -> None:
        """Завершает прогон: обновляет статус и exit_code.

        Идемпотентен: AND status='running' гарантирует, что повторный вызов
        не изменит уже завершённый прогон.
        now=None — берём значение из clock (если задан) или не пишем время.
        """
        finished_at = now if now is not None else (
            self._clock() if self._clock is not None else None
        )
        self._db.execute(
            "UPDATE runs SET status=?, exit_code=?, finished_at=? "
            "WHERE id=? AND status='running'",
            [status, exit_code, finished_at, run_id],
        )

    def get(self, run_id: int) -> dict | None:
        """Возвращает прогон по id или None."""
        return self._db.one("SELECT * FROM runs WHERE id=?", [run_id])

    def latest_for_task(self, task_id: int) -> dict | None:
        """Возвращает последний (самый свежий по id) прогон задачи или None."""
        return self._db.one(
            "SELECT * FROM runs WHERE task_id=? ORDER BY id DESC LIMIT 1",
            [task_id],
        )

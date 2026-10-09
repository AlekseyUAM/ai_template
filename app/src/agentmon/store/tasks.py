"""Репозиторий задач поверх адаптера Db."""


class TaskRepo:
    """CRUD-обёртка над таблицей tasks."""

    def __init__(self, db):
        # сохраняем ссылку на адаптер БД
        self._db = db

    def add(
        self,
        *,
        project_id: int,
        name: str,
        identifier: str = "",
        goal: str = "",
        plan: str = "",
        constraints: str = "",
        tests: str = "",
        stages_json: str = "[]",
        status: str = "planned",
        stage=None,
        now=None,
        kind: str = "real",
        update_db: int = 0,
        max_minutes: int = 60,
        interactive: int = 0,
        mark_changes: int = 0,
    ) -> int:
        """Создаёт задачу, возвращает её id.

        now=None — не записываем время (детерминизм тестов).
        kind — тип задачи: 'real' (по умолчанию) или 'test'.
        update_db — обновлять ли базу данных и расширения перед выполнением (0/1).
        max_minutes — максимальная длительность выполнения в минутах.
        interactive — интерактивный режим выполнения (0/1).
        mark_changes — выделять ли изменения в коде идентификаторами (0/1).
        """
        columns = [
            "project_id", "name", "identifier", "goal", "plan", "constraints", "tests",
            "stages_json", "status", "stage", "created_at", "kind",
            "update_db", "max_minutes", "interactive", "mark_changes",
        ]
        params = [
            project_id, name, identifier, goal, plan, constraints, tests,
            stages_json, status, stage, now, kind,
            int(update_db), int(max_minutes), int(interactive), int(mark_changes),
        ]
        return self._db.returning_id("tasks", columns, params)

    def get(self, id) -> dict | None:
        """Возвращает задачу по первичному ключу или None."""
        return self._db.one("SELECT * FROM tasks WHERE id=?", [id])

    def list(self, project_id=None) -> list[dict]:
        """Возвращает все задачи (или только для указанного проекта), упорядоченные по id."""
        if project_id is None:
            # все задачи без фильтра
            return self._db.query("SELECT * FROM tasks ORDER BY id")
        return self._db.query(
            "SELECT * FROM tasks WHERE project_id=? ORDER BY id", [project_id]
        )

    def update(self, id, **fields) -> None:
        """Обновляет переданные поля задачи.

        Строит SET col=? список только из переданных kwargs.
        """
        if not fields:
            return
        # формируем SET-часть динамически по ключам
        set_clause = ", ".join(f"{col}=?" for col in fields)
        params = list(fields.values()) + [id]
        self._db.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", params)

    def set_status(self, id, status: str, stage=None) -> None:
        """Меняет статус задачи; если stage передан — обновляет и его."""
        if stage is not None:
            self._db.execute(
                "UPDATE tasks SET status=?, stage=? WHERE id=?",
                [status, stage, id],
            )
        else:
            # stage не передан — обновляем только статус, stage остаётся прежним
            self._db.execute(
                "UPDATE tasks SET status=? WHERE id=?",
                [status, id],
            )

    def delete(self, id) -> None:
        """Удаляет задачу и её зависимые строки одной транзакцией.

        FK-ограничений нет — каскад явный: сначала runs (runs.task_id) и
        stack_items (stack_items.task_id) задачи, затем сама задача. Всё в одной
        транзакции, чтобы не осталось сирот при частичном сбое.
        """
        with self._db.transaction():
            self._db.execute("DELETE FROM runs WHERE task_id=?", [id])
            self._db.execute("DELETE FROM stack_items WHERE task_id=?", [id])
            self._db.execute("DELETE FROM tasks WHERE id=?", [id])

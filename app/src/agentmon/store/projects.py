"""Репозиторий проектов поверх адаптера Db."""


class ProjectRepo:
    """CRUD-обёртка над таблицей projects."""

    def __init__(self, db):
        # сохраняем ссылку на адаптер БД
        self._db = db

    def add(
        self,
        *,
        name: str,
        path: str,
        identifier: str = "",
        email: str = "",
        platform_dir: str = "",
        platform_version: str = "",
        db_kind: str = "file",
        db_connection: str = "",
        web_publication: str = "",
        env_version: str = "",
        now=None,
    ) -> int:
        """Создаёт проект, возвращает его id.

        now=None — не записываем время (детерминизм тестов).
        """
        columns = [
            "name", "path", "identifier", "email",
            "platform_dir", "platform_version",
            "db_kind", "db_connection", "web_publication",
            "env_version", "created_at",
        ]
        params = [
            name, path, identifier, email,
            platform_dir, platform_version,
            db_kind, db_connection, web_publication,
            env_version, now,
        ]
        return self._db.returning_id("projects", columns, params)

    def get(self, id) -> dict | None:
        """Возвращает проект по первичному ключу или None."""
        return self._db.one("SELECT * FROM projects WHERE id=?", [id])

    def by_name(self, name: str) -> dict | None:
        """Возвращает проект по уникальному имени или None."""
        return self._db.one("SELECT * FROM projects WHERE name=?", [name])

    def list(self) -> list[dict]:
        """Возвращает все проекты, упорядоченные по id."""
        return self._db.query("SELECT * FROM projects ORDER BY id")

    def update(self, id, **fields) -> None:
        """Обновляет переданные поля проекта.

        Строит SET col=? список только из переданных kwargs.
        """
        if not fields:
            return
        # формируем SET-часть динамически по ключам
        set_clause = ", ".join(f"{col}=?" for col in fields)
        params = list(fields.values()) + [id]
        self._db.execute(
            f"UPDATE projects SET {set_clause} WHERE id=?", params
        )

    def delete(self, id) -> None:
        """Удаляет проект и все зависимые строки одной транзакцией.

        FK-ограничений в схеме нет, поэтому каскад делаем явно: сначала чистим
        stack_items и runs задач проекта, затем сами задачи, runs и связи
        project_mcp проекта, и лишь потом сам проект. Всё в одной транзакции —
        частичное удаление не должно оставить сирот.
        """
        with self._db.transaction():
            # элементы стеков для задач проекта (stack_items.task_id)
            self._db.execute(
                "DELETE FROM stack_items WHERE task_id IN "
                "(SELECT id FROM tasks WHERE project_id=?)", [id]
            )
            # прогоны проекта (runs.project_id покрывает и прогоны его задач)
            self._db.execute("DELETE FROM runs WHERE project_id=?", [id])
            # задачи проекта
            self._db.execute("DELETE FROM tasks WHERE project_id=?", [id])
            # привязки MCP к проекту
            self._db.execute("DELETE FROM project_mcp WHERE project_id=?", [id])
            # сам проект
            self._db.execute("DELETE FROM projects WHERE id=?", [id])

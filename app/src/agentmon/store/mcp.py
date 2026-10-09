"""Репозиторий MCP-серверов и их привязки к проектам поверх адаптера Db."""


class McpRepo:
    """CRUD-обёртка над таблицей mcp_servers + управление project_mcp."""

    def __init__(self, db):
        # сохраняем ссылку на адаптер БД
        self._db = db

    def add(
        self,
        *,
        name: str,
        purpose: str = "",
        kind: str = "custom",
        standard_key=None,
        connection_json=None,
        port=None,
        token_env=None,
        mcp_name=None,
        url=None,
        db_name=None,
        catalog_dir=None,
        platform_path=None,
        now=None,
    ) -> int:
        """Создаёт запись MCP-сервера, возвращает id.

        now=None — не записываем время (детерминизм тестов).
        """
        columns = [
            "name", "purpose", "kind",
            "standard_key", "connection_json", "port", "token_env",
            "mcp_name", "url", "db_name", "catalog_dir", "platform_path",
            "created_at",
        ]
        params = [
            name, purpose, kind,
            standard_key, connection_json, port, token_env,
            mcp_name, url, db_name, catalog_dir, platform_path,
            now,
        ]
        return self._db.returning_id("mcp_servers", columns, params)

    def get(self, id) -> dict | None:
        """Возвращает MCP-сервер по id или None."""
        return self._db.one("SELECT * FROM mcp_servers WHERE id=?", [id])

    def by_name(self, name: str) -> dict | None:
        """Возвращает MCP-сервер по уникальному имени или None."""
        return self._db.one("SELECT * FROM mcp_servers WHERE name=?", [name])

    def list(self) -> list[dict]:
        """Возвращает все MCP-серверы, упорядоченные по id."""
        return self._db.query("SELECT * FROM mcp_servers ORDER BY id")

    def update(self, id, **fields) -> None:
        """Обновляет переданные поля MCP-сервера.

        Строит SET col=? список только из переданных kwargs.
        """
        if not fields:
            return
        # динамически формируем SET-часть по ключам kwargs
        set_clause = ", ".join(f"{col}=?" for col in fields)
        params = list(fields.values()) + [id]
        self._db.execute(
            f"UPDATE mcp_servers SET {set_clause} WHERE id=?", params
        )

    def delete(self, id) -> None:
        """Удаляет MCP-сервер и его привязки к проектам одной транзакцией.

        FK-ограничений нет — чистим project_mcp (project_mcp.mcp_id) явно, затем
        сам сервер. Транзакция не оставляет сиротских строк project_mcp.
        """
        with self._db.transaction():
            self._db.execute("DELETE FROM project_mcp WHERE mcp_id=?", [id])
            self._db.execute("DELETE FROM mcp_servers WHERE id=?", [id])

    def set_for_project(self, project_id: int, mcp_ids: list[int]) -> None:
        """Атомарно перезаписывает набор MCP для проекта: delete + insert.

        Выполняется в одной транзакции: сначала удаляем все существующие
        строки project_mcp для project_id, затем вставляем переданные mcp_ids.
        Сбой на любом шаге откатывает всю операцию целиком.
        """
        with self._db.transaction():
            # удаляем текущие связи проекта
            self._db.execute(
                "DELETE FROM project_mcp WHERE project_id=?", [project_id]
            )
            # вставляем новые связи
            for mcp_id in mcp_ids:
                self._db.returning_id(
                    "project_mcp",
                    ["project_id", "mcp_id"],
                    [project_id, mcp_id],
                )

    def for_project(self, project_id: int) -> list[dict]:
        """Возвращает полные строки mcp_servers для заданного проекта."""
        return self._db.query(
            """SELECT ms.*
               FROM mcp_servers ms
               JOIN project_mcp pm ON pm.mcp_id = ms.id
               WHERE pm.project_id=?
               ORDER BY ms.id""",
            [project_id],
        )

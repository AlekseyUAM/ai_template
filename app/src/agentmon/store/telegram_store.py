"""Репозитории Telegram-интеграции: состояние уведомлений и замечания."""


class NotifyStateRepo:
    """Последнее уведомлённое состояние задач/стеков (scope+ref_id)."""

    def __init__(self, db):
        self._db = db

    def get(self, scope: str, ref_id: int) -> str | None:
        row = self._db.one(
            "SELECT last_status FROM tg_notify_state WHERE scope=? AND ref_id=?",
            [scope, ref_id],
        )
        return row["last_status"] if row else None

    def set(self, scope: str, ref_id: int, status: str) -> None:
        # upsert без диалект-специфики: UPDATE, затем INSERT при отсутствии строки.
        changed = self._db.execute_rowcount(
            "UPDATE tg_notify_state SET last_status=? WHERE scope=? AND ref_id=?",
            [status, scope, ref_id],
        )
        if not changed:
            self._db.returning_id(
                "tg_notify_state", ["scope", "ref_id", "last_status"],
                [scope, ref_id, status],
            )


class FeedbackRepo:
    """Пользовательские замечания к задаче."""

    def __init__(self, db):
        self._db = db

    def add(self, task_id: int, chat_id: str, text: str, now=None) -> int:
        return self._db.returning_id(
            "task_feedback", ["task_id", "chat_id", "text", "created_at"],
            [task_id, chat_id, text, now],
        )

    def list_for_task(self, task_id: int) -> list[dict]:
        return self._db.query(
            "SELECT * FROM task_feedback WHERE task_id=? ORDER BY id", [task_id],
        )

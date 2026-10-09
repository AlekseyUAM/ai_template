import time

from .models import Task


class TaskQueue:
    """Очередь задач по проектам. Схемой владеет registry.open_db."""

    def __init__(self, conn):
        self.conn = conn

    def _row_to_task(self, row) -> Task:
        return Task(
            id=row["id"], project_id=row["project_id"], text=row["text"],
            status=row["status"], created_at=row["created_at"],
            started_at=row["started_at"], finished_at=row["finished_at"],
            session_id=row["session_id"],
        )

    def enqueue(self, project_id, text) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks (project_id, text, status, created_at) "
            "VALUES (?, ?, 'queued', ?)",
            (project_id, text, time.time()),
        )
        self.conn.commit()
        return cur.lastrowid

    def list(self, project_id=None) -> list[Task]:
        if project_id is None:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE project_id IS NOT NULL ORDER BY id"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM tasks WHERE project_id = ? ORDER BY id", (project_id,)
            ).fetchall()
        return [self._row_to_task(r) for r in rows]

    def next(self, project_id) -> Task | None:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = 'queued' "
            "ORDER BY id LIMIT 1", (project_id,),
        ).fetchone()
        return self._row_to_task(row) if row else None

    def running_for(self, project_id) -> Task | None:
        row = self.conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = 'running' "
            "ORDER BY id LIMIT 1", (project_id,),
        ).fetchone()
        return self._row_to_task(row) if row else None

    def mark_running(self, task_id, session_id) -> bool:
        """Атомарно захватывает задачу: queued → running.

        UPDATE ... WHERE id=? AND status='queued' в одном операторе закрывает
        TOCTOU: два диспетчера не могут захватить одну задачу и запустить её
        дважды. Возвращает True, если строку обновили (захват удался), иначе
        False — задачу уже забрал другой, запускать агента не нужно.
        """
        cur = self.conn.execute(
            "UPDATE tasks SET status='running', started_at=?, session_id=? "
            "WHERE id=? AND status='queued'",
            (time.time(), session_id, task_id),
        )
        self.conn.commit()
        return cur.rowcount == 1

    def mark_done(self, task_id) -> None:
        self.conn.execute(
            "UPDATE tasks SET status='done', finished_at=? WHERE id=?",
            (time.time(), task_id),
        )
        self.conn.commit()

    def mark_failed(self, task_id) -> None:
        self.conn.execute(
            "UPDATE tasks SET status='failed', finished_at=? WHERE id=?",
            (time.time(), task_id),
        )
        self.conn.commit()

    def delete(self, task_id) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        self.conn.commit()

    def requeue(self, task_id) -> None:
        """Вернуть одну задачу в очередь — агент, которому её отдали, мёртв."""
        self.conn.execute(
            "UPDATE tasks SET status='queued', started_at=NULL, session_id=NULL "
            "WHERE id=?", (task_id,),
        )
        self.conn.commit()

    def requeue_running(self) -> int:
        """Вернуть зависшие running-задачи в очередь.

        Агенты живут внутри процесса монитора и не переживают его перезапуск,
        поэтому running-задача после старта заведомо никем не выполняется.
        Возвращаем в очередь, а не помечаем failed: задача могла вообще не
        начать выполняться, и потеря работы тут дешевле молчаливого пропуска.
        """
        cur = self.conn.execute(
            "UPDATE tasks SET status='queued', started_at=NULL, session_id=NULL "
            "WHERE status='running'"
        )
        self.conn.commit()
        return cur.rowcount

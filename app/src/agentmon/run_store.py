"""Реестр detached-прогонов (таблица runs). Переживает перезапуск монитора."""
import sqlite3
import time

_SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id INTEGER,
    pid INTEGER NOT NULL,
    log_file TEXT,
    exit_file TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    started_at REAL NOT NULL,
    finished_at REAL,
    exit_code INTEGER
)"""


class RunStore:
    def __init__(self, conn, clock=time.time):
        self.conn = conn
        self.clock = clock
        conn.row_factory = sqlite3.Row
        conn.execute(_SCHEMA)
        conn.commit()

    def add(self, project_id, pid, *, task_id=None, log_file=None, exit_file=None):
        cur = self.conn.execute(
            "INSERT INTO runs (project_id, task_id, pid, log_file, exit_file, "
            "status, started_at) VALUES (?,?,?,?,?,'running',?)",
            (project_id, task_id, pid, log_file, exit_file, self.clock()))
        self.conn.commit()
        return cur.lastrowid

    def running(self, project_id=None):
        if project_id is None:
            rows = self.conn.execute("SELECT * FROM runs WHERE status='running'").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE status='running' AND project_id=?",
                (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def finish(self, run_id, status, exit_code=None):
        self.conn.execute(
            "UPDATE runs SET status=?, exit_code=?, finished_at=? "
            "WHERE id=? AND status='running'",
            (status, exit_code, self.clock(), run_id))
        self.conn.commit()

    def get(self, run_id):
        r = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def latest_for_task(self, task_id):
        """Последний (самый свежий) прогон задачи или None."""
        r = self.conn.execute(
            "SELECT * FROM runs WHERE task_id=? ORDER BY id DESC LIMIT 1",
            (task_id,)).fetchone()
        return dict(r) if r else None

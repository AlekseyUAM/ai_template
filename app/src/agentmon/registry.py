import json
import sqlite3
import threading
import time

from .models import Project

SCHEMA_VERSION = 1
BACKENDS = ("local", "ssh")


class _Result:
    """Готовый результат одного execute: строки вычитаны под блокировкой.

    Держать курсор sqlite и дочитывать его позже нельзя — соединение делят
    несколько потоков, и чужой execute сдвинул бы состояние. Поэтому строки
    материализуются сразу, а объект лишь отдаёт их и метаданные курсора.
    """

    __slots__ = ("_rows", "lastrowid", "rowcount")

    def __init__(self, rows, lastrowid, rowcount):
        self._rows = rows
        self.lastrowid = lastrowid
        self.rowcount = rowcount

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _LockingConnection:
    """Потокобезопасная обёртка над sqlite3.Connection.

    check_same_thread=False позволяет делить соединение между потоками пула
    FastAPI и диспетчера, но sqlite3 не сериализует курсор/коммит сам — гонки
    приводят к порче состояния. Один RLock на всё соединение закрывает проблему;
    RLock (а не Lock) — чтобы вложенные вызовы (например, под BEGIN) не вставали
    в клинч. Каждый execute полностью вычитывает результат под блокировкой.
    """

    def __init__(self, conn):
        self._conn = conn
        self._lock = threading.RLock()

    @property
    def lock(self):
        return self._lock

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        with self._lock:
            self._conn.row_factory = value

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._conn.execute(sql, params)
            rows = cur.fetchall() if cur.description is not None else []
            return _Result(rows, cur.lastrowid, cur.rowcount)

    def commit(self):
        with self._lock:
            self._conn.commit()

    def rollback(self):
        with self._lock:
            self._conn.rollback()

    def close(self):
        with self._lock:
            self._conn.close()


def open_db(path):
    """Открыть БД и довести схему до актуальной версии."""
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # WAL + busy_timeout: мягкая параллельность чтения/записи и ожидание до 5с
    # вместо немедленного «database is locked» при короткой гонке за блокировку.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    wrapped = _LockingConnection(conn)
    _migrate(wrapped)
    return wrapped


def _migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    # Миграция целиком — одна транзакция. В режиме isolation_level по
    # умолчанию python sqlite3 открывает транзакцию сам, но только на первом
    # DML: если переносить нечего (старая tasks пуста), то CREATE TABLE
    # tasks_new выполняется в autocommit и фиксируется сам по себе. Падение
    # процесса сразу после него оставляло бы сиротскую tasks_new при
    # user_version = 0, и каждый следующий запуск падал бы на «table
    # tasks_new already exists» — приложение не стартовало бы никогда.
    # Явный BEGIN накрывает и DDL. Он ставится после раннего возврата:
    # иначе уже смигрированная БД оставалась бы с открытой транзакцией.
    conn.execute("BEGIN")
    try:
        _apply_v1(conn)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except Exception:
        conn.rollback()               # незавершённая миграция не должна осесть в БД
        raise
    conn.commit()


def _apply_v1(conn: sqlite3.Connection) -> None:
    """Шаги миграции до SCHEMA_VERSION = 1. Вызывается внутри транзакции."""
    conn.execute(
        """CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            session_id TEXT
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT NOT NULL,
            backend TEXT NOT NULL,
            conn TEXT,
            claude_cmd TEXT,
            key TEXT NOT NULL UNIQUE,
            created_at REAL NOT NULL
        )"""
    )
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(tasks)")}
    if "project_id" not in cols:
        conn.execute("ALTER TABLE tasks ADD COLUMN project_id INTEGER")

    # Перенос старых задач: каждый уникальный путь становится local-проектом.
    if "project" in cols:
        rows = conn.execute(
            "SELECT DISTINCT project FROM tasks "
            "WHERE project IS NOT NULL AND project_id IS NULL"
        ).fetchall()
        now = time.time()
        for row in rows:
            path = row["project"]
            key = f"local||{path}"
            conn.execute(
                "INSERT OR IGNORE INTO projects "
                "(name, path, backend, conn, claude_cmd, key, created_at) "
                "VALUES (?, ?, 'local', NULL, NULL, ?, ?)",
                (_basename(path), path, key, now),
            )
            pid = conn.execute(
                "SELECT id FROM projects WHERE key = ?", (key,)
            ).fetchone()["id"]
            conn.execute(
                "UPDATE tasks SET project_id = ? WHERE project = ? AND project_id IS NULL",
                (pid, path),
            )

    if _project_is_not_null(conn):
        _rebuild_tasks_without_not_null(conn)


def _project_is_not_null(conn: sqlite3.Connection) -> bool:
    """Осталось ли от старой схемы ограничение NOT NULL на tasks.project."""
    for row in conn.execute("PRAGMA table_info(tasks)"):
        if row["name"] == "project":
            return bool(row["notnull"])
    return False


def _rebuild_tasks_without_not_null(conn: sqlite3.Connection) -> None:
    """Пересоздать tasks, сняв NOT NULL с устаревшей колонки project.

    CREATE TABLE IF NOT EXISTS ничего не делает с уже существующей таблицей,
    поэтому ограничение старой схемы переживает миграцию, а новый enqueue
    project не пишет вовсе — каждая новая задача падала бы на IntegrityError.
    ALTER TABLE ... DROP COLUMN требует sqlite >= 3.35, которого на целевом
    Debian может не быть, поэтому таблица пересоздаётся целиком.
    AUTOINCREMENT сохраняем, чтобы id продолжили расти, а не переиспользовались.
    """
    high_water = _tasks_high_water(conn)
    # Сирота от оборвавшейся когда-то миграции: без этого CREATE TABLE падал
    # бы на «table tasks_new already exists», и БД не открывалась бы вовсе.
    conn.execute("DROP TABLE IF EXISTS tasks_new")
    conn.execute(
        """CREATE TABLE tasks_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            created_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            session_id TEXT,
            project_id INTEGER
        )"""
    )
    conn.execute(
        "INSERT INTO tasks_new "
        "(id, project, text, status, created_at, started_at, finished_at, "
        " session_id, project_id) "
        "SELECT id, project, text, status, created_at, started_at, finished_at, "
        "       session_id, project_id FROM tasks"
    )
    conn.execute("DROP TABLE tasks")
    conn.execute("ALTER TABLE tasks_new RENAME TO tasks")
    _restore_tasks_high_water(conn, high_water)


def _tasks_high_water(conn: sqlite3.Connection) -> int:
    """Достигнутый максимум счётчика AUTOINCREMENT таблицы tasks (0, если нет)."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'sqlite_sequence'"
    ).fetchone()
    if not exists:
        return 0
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'tasks'").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _restore_tasks_high_water(conn: sqlite3.Connection, high_water: int) -> None:
    """Вернуть счётчику пересозданной tasks прежний максимум.

    DROP TABLE уносит с собой строку из sqlite_sequence, и новая таблица
    начинает считать от наибольшего живого id. Тогда id удалённых задач
    выдавались бы заново — а на них ссылаются журналы и уже показанные
    пользователю ссылки. AUTOINCREMENT без своего максимума бессмыслен.
    """
    if high_water <= 0:
        return
    row = conn.execute(
        "SELECT seq FROM sqlite_sequence WHERE name = 'tasks'").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO sqlite_sequence (name, seq) VALUES ('tasks', ?)",
            (high_water,))
    elif int(row[0] or 0) < high_water:
        conn.execute(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = 'tasks'",
            (high_water,))


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or path


def _key_for(backend: str, conn: dict | None, path: str) -> str:
    host = (conn or {}).get("host") or ""
    return f"{backend}|{host}|{path}"


def _validate(backend: str, conn: dict | None) -> None:
    if backend not in BACKENDS:
        raise ValueError(f"неизвестный backend: {backend!r}")
    if backend == "ssh" and not (conn or {}).get("host"):
        raise ValueError("для backend=ssh требуется host в conn")


class ProjectRegistry:
    """Единственный источник правды о том, какие проекты существуют."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def _row_to_project(self, row) -> Project:
        return Project(
            id=row["id"], name=row["name"], path=row["path"],
            backend=row["backend"],
            conn=json.loads(row["conn"]) if row["conn"] else None,
            claude_cmd=row["claude_cmd"], created_at=row["created_at"],
        )

    def add(self, name, path, backend, conn=None, claude_cmd=None) -> Project:
        _validate(backend, conn)
        key = _key_for(backend, conn, path)
        if self.get_by_key(key) is not None:
            raise ValueError(f"проект уже есть в реестре: {key}")
        try:
            cur = self.conn.execute(
                "INSERT INTO projects (name, path, backend, conn, claude_cmd, key, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name or _basename(path), path, backend,
                 json.dumps(conn) if conn else None, claude_cmd, key, time.time()),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"проект уже есть в реестре: {key}")
        return self.get(cur.lastrowid)

    def list(self) -> list[Project]:
        rows = self.conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
        return [self._row_to_project(r) for r in rows]

    def get(self, project_id) -> Project | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_project(row) if row else None

    def get_by_key(self, key) -> Project | None:
        row = self.conn.execute(
            "SELECT * FROM projects WHERE key = ?", (key,)
        ).fetchone()
        return self._row_to_project(row) if row else None

    def update(self, project_id, **fields) -> Project:
        cur = self.get(project_id)
        if cur is None:
            raise ValueError(f"нет проекта с id={project_id}")
        allowed = ("name", "path", "backend", "conn", "claude_cmd")
        bad = set(fields) - set(allowed)
        if bad:
            raise ValueError(f"нельзя менять поля: {sorted(bad)}")
        name = fields.get("name", cur.name)
        path = fields.get("path", cur.path)
        backend = fields.get("backend", cur.backend)
        conn = fields.get("conn", cur.conn)
        claude_cmd = fields.get("claude_cmd", cur.claude_cmd)
        _validate(backend, conn)
        key = _key_for(backend, conn, path)
        other = self.get_by_key(key)
        if other is not None and other.id != project_id:
            raise ValueError(f"проект уже есть в реестре: {key}")
        try:
            self.conn.execute(
                "UPDATE projects SET name=?, path=?, backend=?, conn=?, claude_cmd=?, key=? "
                "WHERE id=?",
                (name, path, backend, json.dumps(conn) if conn else None,
                 claude_cmd, key, project_id),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"проект уже есть в реестре: {key}")
        return self.get(project_id)

    def delete(self, project_id) -> None:
        self.conn.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

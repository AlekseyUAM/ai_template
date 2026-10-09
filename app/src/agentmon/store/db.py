"""Адаптер БД: sqlite (тесты/дев) и postgresql (продукт).

SQL переносимый; различия диалектов — автоинкрементный PK (autopk) и трансляция
плейсхолдеров ?→%s (postgres). Параметры всегда пишем через `?`.

Соединение открывается с check_same_thread=False (sqlite) и разделяется между
потоками пула FastAPI и потоками диспетчера. sqlite3.Connection не потокобезопасен
на уровне курсора/коммита, поэтому все операции сериализуются одним RLock.
RLock (а не Lock) — чтобы вложенные вызовы внутри transaction() не вставали в клинч.
"""
import contextlib
import sqlite3
import threading


class Db:
    def __init__(self, conn, dialect, connector=None):
        self.conn = conn
        self.dialect = dialect
        # Как заново открыть соединение, если текущее умерло (только postgres).
        self._connector = connector
        self._autocommit = True
        # Сериализует доступ к соединению из нескольких потоков. RLock, чтобы
        # transaction() мог удерживать его на всю транзакцию, а вложенные
        # execute/query/returning_id внутри неё не блокировали сами себя.
        self._lock = threading.RLock()

    def _translate(self, sql: str) -> str:
        return sql if self.dialect == "sqlite" else sql.replace("?", "%s")

    def _reconnect(self):
        with contextlib.suppress(Exception):
            self.conn.close()
        self.conn = self._connector()

    def _run(self, work):
        """Выполняет work(cursor) под локом, прозрачно переподнимая умершее
        postgres-соединение.

        Одно долгоживущее соединение делится между потоками пула FastAPI и
        диспетчером. Сервер может его закрыть (idle-timeout, рестарт, обрыв
        сети), и тогда psycopg отдаёт OperationalError «the connection is
        closed» на каждый следующий запрос — до перезапуска процесса. Поэтому
        перед работой проверяем флаг closed, а если соединение умерло прямо в
        процессе — переподнимаем и повторяем один раз.

        Внутри transaction() (autocommit=False) не переподключаемся: молчаливый
        повтор порвал бы атомарность, ошибка должна дойти до rollback.
        """
        with self._lock:
            can_retry = self.dialect == "postgres" and self._autocommit \
                and self._connector is not None
            if can_retry and getattr(self.conn, "closed", 0):
                self._reconnect()
            try:
                return work(self.conn.cursor())
            except Exception:
                if not (can_retry and getattr(self.conn, "closed", 0)):
                    raise
                self._reconnect()
                return work(self.conn.cursor())

    def _maybe_commit(self):
        if self._autocommit:
            self.conn.commit()

    @contextlib.contextmanager
    def transaction(self):
        # Держим lock на всю транзакцию: вложенные операции берут тот же RLock
        # повторно (без блокировки), а параллельные потоки ждут снаружи.
        with self._lock:
            self._autocommit = False
            try:
                yield
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self._autocommit = True

    def execute(self, sql, params=()):
        def work(cur):
            cur.execute(self._translate(sql), tuple(params))
            self._maybe_commit()
            return cur
        return self._run(work)

    def query(self, sql, params=()):
        def work(cur):
            cur.execute(self._translate(sql), tuple(params))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        return self._run(work)

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute_rowcount(self, sql, params=()) -> int:
        """Выполняет DML и возвращает число затронутых строк (cur.rowcount).

        Нужно для атомарного захвата: UPDATE ... WHERE status='queued' и проверка,
        что строка действительно обновилась (ровно один захватил задачу).
        """
        def work(cur):
            cur.execute(self._translate(sql), tuple(params))
            self._maybe_commit()
            return cur.rowcount
        return self._run(work)

    def autopk(self) -> str:
        if self.dialect == "sqlite":
            return "INTEGER PRIMARY KEY AUTOINCREMENT"
        return "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"

    def returning_id(self, table, columns, params) -> int:
        collist = ",".join(columns)
        placeholders = ",".join("?" for _ in columns)
        sql = f"INSERT INTO {table} ({collist}) VALUES ({placeholders})"

        def work(cur):
            if self.dialect == "sqlite":
                cur.execute(sql, tuple(params))
                self._maybe_commit()
                return cur.lastrowid
            cur.execute(self._translate(sql + " RETURNING id"), tuple(params))
            rid = cur.fetchone()[0]
            self._maybe_commit()
            return rid
        return self._run(work)

    def close(self):
        with self._lock:
            self.conn.close()


def connect(dsn: str) -> Db:
    if dsn.startswith(("postgresql://", "postgres://")):
        import psycopg
        connector = lambda: psycopg.connect(dsn)  # noqa: E731
        return Db(connector(), "postgres", connector=connector)
    path = dsn[len("sqlite:///"):] if dsn.startswith("sqlite:///") else dsn
    conn = sqlite3.connect(path, check_same_thread=False)
    # WAL + busy_timeout: параллельные читатели/писатель не блокируют друг друга
    # жёстко, а короткие гонки за блокировку sqlite ждут до 5с вместо «database
    # is locked».
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return Db(conn, "sqlite")

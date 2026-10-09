from agentmon.store.db import connect


def test_sqlite_connect_and_crud(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    assert db.dialect == "sqlite"
    db.execute(f"CREATE TABLE t (id {db.autopk()}, name TEXT)")
    rid = db.returning_id("t", ["name"], ["alpha"])
    assert rid == 1
    rid2 = db.returning_id("t", ["name"], ["beta"])
    assert rid2 == 2
    assert db.one("SELECT name FROM t WHERE id=?", [rid])["name"] == "alpha"
    assert [r["name"] for r in db.query("SELECT name FROM t ORDER BY id")] == ["alpha", "beta"]
    db.execute("UPDATE t SET name=? WHERE id=?", ["gamma", rid])
    assert db.one("SELECT name FROM t WHERE id=?", [rid])["name"] == "gamma"
    db.close()


def test_sqlite_url_prefix(tmp_path):
    db = connect(f"sqlite:///{tmp_path / 'u.db'}")
    assert db.dialect == "sqlite"
    db.close()


def test_postgres_placeholder_translation():
    # без живого сервера: проверяем только определение диалекта и трансляцию
    from agentmon.store.db import Db
    db = Db.__new__(Db)
    db.dialect = "postgres"
    assert db._translate("SELECT ? , ?") == "SELECT %s , %s"


class _FakeCursor:
    description = [("name",)]

    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params):
        pass

    def fetchall(self):
        return list(self._rows)


class _FakeConn:
    """Имитирует psycopg-соединение: cursor() на закрытом падает, как psycopg."""

    def __init__(self, rows):
        self._rows = rows
        self.closed = 0

    def cursor(self):
        if self.closed:
            raise RuntimeError("the connection is closed")
        return _FakeCursor(self._rows)

    def commit(self):
        pass

    def close(self):
        self.closed = 1


def test_postgres_reconnects_when_connection_closed():
    """Мёртвое postgres-соединение переподнимается прозрачно (idle-timeout,
    рестарт сервера), а не валит каждый последующий запрос «connection is
    closed» до перезапуска процесса."""
    from agentmon.store.db import Db

    conns = [_FakeConn([("alpha",)]), _FakeConn([("beta",)])]
    made = []

    def connector():
        c = conns[len(made)]
        made.append(c)
        return c

    db = Db(connector(), "postgres", connector=connector)

    # первый запрос проходит на исходном соединении
    assert [r["name"] for r in db.query("SELECT name")] == ["alpha"]

    # сервер закрыл соединение
    made[0].closed = 1

    # запрос не падает, а переподнимает соединение и выполняется заново
    assert [r["name"] for r in db.query("SELECT name")] == ["beta"]
    assert len(made) == 2

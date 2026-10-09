import sqlite3

import pytest

from agentmon.queue import TaskQueue
from agentmon import registry as registry_module
from agentmon.registry import ProjectRegistry, open_db


def test_add_and_list(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    p = reg.add(name="demo", path="/srv/demo", backend="local")
    assert p.id is not None
    assert [x.path for x in reg.list()] == ["/srv/demo"]
    assert reg.get(p.id).name == "demo"


def test_conn_roundtrips_as_json(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    conn = {"host": "srv", "port": 2222, "user": "root", "key_path": "/k/id"}
    p = reg.add(name="r", path="/srv/r", backend="ssh", conn=conn)
    assert reg.get(p.id).conn == conn
    assert reg.get(p.id).key == "ssh|srv|/srv/r"


def test_duplicate_key_is_rejected(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    reg.add(name="a", path="/srv/x", backend="local")
    with pytest.raises(ValueError, match="уже есть"):
        reg.add(name="b", path="/srv/x", backend="local")


def test_same_path_on_different_hosts_is_allowed(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    reg.add(name="a", path="/srv/x", backend="ssh", conn={"host": "h1"})
    reg.add(name="b", path="/srv/x", backend="ssh", conn={"host": "h2"})
    assert len(reg.list()) == 2


def test_update_recomputes_key(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    p = reg.add(name="a", path="/srv/x", backend="local")
    upd = reg.update(p.id, path="/srv/y")
    assert upd.path == "/srv/y"
    assert upd.key == "local||/srv/y"


def test_delete(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    p = reg.add(name="a", path="/srv/x", backend="local")
    reg.delete(p.id)
    assert reg.list() == []
    assert reg.get(p.id) is None


def test_unknown_backend_rejected(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError, match="backend"):
        reg.add(name="a", path="/srv/x", backend="podman")


def test_ssh_requires_host(tmp_path):
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    with pytest.raises(ValueError, match="host"):
        reg.add(name="a", path="/srv/x", backend="ssh", conn={})


def test_integrity_error_on_duplicate_key_converted_to_value_error(tmp_path):
    """Гонка: предпроверка ничего не нашла, но INSERT упёрся в UNIQUE."""
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    reg.add(name="a", path="/srv/x", backend="local")
    # Имитируем гонку: предпроверка «не видит» уже существующий проект,
    # как это бывает, когда другой поток вставил строку после неё.
    reg.get_by_key = lambda key: None
    with pytest.raises(ValueError, match="уже есть"):
        reg.add(name="b", path="/srv/x", backend="local")


def test_integrity_error_on_update_duplicate_key_converted_to_value_error(tmp_path):
    """Гонка в UPDATE: предпроверка ничего не нашла, но UPDATE упёрся в UNIQUE."""
    reg = ProjectRegistry(open_db(tmp_path / "db.sqlite"))
    p1 = reg.add(name="a", path="/srv/x", backend="local")
    p2 = reg.add(name="b", path="/srv/y", backend="local")
    # Имитируем гонку: предпроверка «не видит» уже существующий проект.
    reg.get_by_key = lambda key: None
    with pytest.raises(ValueError, match="уже есть"):
        reg.update(p2.id, path="/srv/x")


def _write_legacy_db(path, with_tasks=True):
    """Дореформенная БД: tasks с project NOT NULL, без projects, user_version=0.

    with_tasks=False даёт пустую tasks — состояние настоящей пользовательской
    БД этого репозитория, на котором переносить нечего и ни одного DML в
    миграции не случается.
    """
    raw = sqlite3.connect(path)
    raw.execute(
        """CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
            text TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'queued',
            created_at REAL NOT NULL, started_at REAL, finished_at REAL,
            session_id TEXT)"""
    )
    if with_tasks:
        raw.execute("INSERT INTO tasks (project, text, created_at) VALUES ('/p/a','t1',1)")
        raw.execute("INSERT INTO tasks (project, text, created_at) VALUES ('/p/a','t2',2)")
        raw.execute("INSERT INTO tasks (project, text, created_at) VALUES ('/p/b','t3',3)")
    raw.commit()
    raw.close()
    return path


ORPHAN_TASKS_NEW = """CREATE TABLE tasks_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT, text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued', created_at REAL NOT NULL,
    started_at REAL, finished_at REAL, session_id TEXT, project_id INTEGER)"""


def _table_names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_migration_from_legacy_tasks_table(tmp_path):
    """Старая БД: tasks с текстовым project и без projects."""
    db = open_db(_write_legacy_db(tmp_path / "old.sqlite"))
    reg = ProjectRegistry(db)
    assert sorted(p.path for p in reg.list()) == ["/p/a", "/p/b"]
    assert all(p.backend == "local" for p in reg.list())
    rows = db.execute("SELECT text, project_id FROM tasks ORDER BY id").fetchall()
    by_path = {p.path: p.id for p in reg.list()}
    assert [(r["text"], r["project_id"]) for r in rows] == [
        ("t1", by_path["/p/a"]), ("t2", by_path["/p/a"]), ("t3", by_path["/p/b"])]


def test_migrated_db_accepts_new_tasks(tmp_path):
    """Главное в миграции — что в БД потом можно писать.

    Старая схема объявляла project NOT NULL, а новый enqueue эту колонку не
    заполняет: без снятия ограничения каждый POST /api/queue падал бы на
    IntegrityError навсегда.
    """
    path = _write_legacy_db(tmp_path / "old.sqlite")
    db = open_db(path)
    reg = ProjectRegistry(db)

    # Старые задачи пережили пересоздание таблицы вместе со связями.
    by_path = {p.path: p.id for p in reg.list()}
    rows = db.execute("SELECT id, text, project_id FROM tasks ORDER BY id").fetchall()
    assert [(r["id"], r["text"], r["project_id"]) for r in rows] == [
        (1, "t1", by_path["/p/a"]), (2, "t2", by_path["/p/a"]),
        (3, "t3", by_path["/p/b"])]

    queue = TaskQueue(db)
    task_id = queue.enqueue(by_path["/p/a"], "новая задача")
    assert task_id > 3                      # AUTOINCREMENT продолжил счёт
    texts = [t.text for t in queue.list(by_path["/p/a"])]
    assert texts == ["t1", "t2", "новая задача"]
    assert queue.next(by_path["/p/a"]).text == "t1"


def test_migration_keeps_new_schema_untouched(tmp_path):
    """На уже новой БД пересоздания tasks не происходит: нечего снимать."""
    path = tmp_path / "db.sqlite"
    db = open_db(path)
    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/srv/x", backend="local")
    TaskQueue(db).enqueue(p.id, "t")
    db.close()

    db2 = open_db(path)
    assert [t.text for t in TaskQueue(db2).list(p.id)] == ["t"]
    assert db2.execute("PRAGMA user_version").fetchone()[0] == 1


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "db.sqlite"
    db = open_db(path)
    ProjectRegistry(db).add(name="a", path="/srv/x", backend="local")
    db.close()
    db2 = open_db(path)
    assert [p.path for p in ProjectRegistry(db2).list()] == ["/srv/x"]
    assert db2.execute("PRAGMA user_version").fetchone()[0] == 1


# --- Оборвавшаяся миграция не должна хоронить БД (регрессия) ---


def test_migration_recovers_from_an_orphan_tasks_new(tmp_path):
    """Сирота от прошлого падения: БД обязана открыться, а не умереть навсегда.

    Пустая старая tasks — ровно тот случай, когда CREATE TABLE tasks_new
    фиксировался сам по себе: ни одного DML перед ним не выполнялось.
    """
    path = _write_legacy_db(tmp_path / "old.sqlite", with_tasks=False)
    raw = sqlite3.connect(path)
    raw.execute(ORPHAN_TASKS_NEW)
    raw.commit()
    raw.close()

    db = open_db(path)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    assert "tasks_new" not in _table_names(db)

    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/srv/a", backend="local")
    queue = TaskQueue(db)
    queue.enqueue(p.id, "новая задача")
    assert [t.text for t in queue.list(p.id)] == ["новая задача"]


def test_failed_migration_rolls_back_whole(tmp_path, monkeypatch):
    """Миграция — одна транзакция: либо вся, либо никакая."""
    path = _write_legacy_db(tmp_path / "old.sqlite", with_tasks=False)
    real_rebuild = registry_module._rebuild_tasks_without_not_null

    def crash(conn):
        real_rebuild(conn)            # tasks_new создана и переименована
        raise RuntimeError("питание выключили посреди миграции")

    monkeypatch.setattr(registry_module, "_rebuild_tasks_without_not_null", crash)
    with pytest.raises(RuntimeError):
        open_db(path)

    raw = sqlite3.connect(path)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    assert "tasks_new" not in _table_names(raw)
    assert "projects" not in _table_names(raw)
    raw.close()

    monkeypatch.undo()
    db = open_db(path)                # повтор проходит начисто
    assert db.execute("PRAGMA user_version").fetchone()[0] == 1
    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/srv/a", backend="local")
    TaskQueue(db).enqueue(p.id, "после повтора")
    assert [t.text for t in TaskQueue(db).list(p.id)] == ["после повтора"]


def test_migration_keeps_the_autoincrement_high_water(tmp_path):
    """Пересоздание tasks не должно возвращать в оборот id удалённых задач."""
    path = _write_legacy_db(tmp_path / "old.sqlite")
    raw = sqlite3.connect(path)
    raw.execute("UPDATE sqlite_sequence SET seq = 100 WHERE name = 'tasks'")
    raw.commit()
    raw.close()

    db = open_db(path)
    reg = ProjectRegistry(db)
    pid = {p.path: p.id for p in reg.list()}["/p/a"]
    task_id = TaskQueue(db).enqueue(pid, "новая задача")
    assert task_id == 101             # счёт продолжается, а не начинается с 4

"""Тесты упрочнения слоя БД: потокобезопасность, атомарный захват,
каскадные удаления, индексы, транзакции стеков.
"""
import threading

from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.mcp import McpRepo
from agentmon.store.projects import ProjectRepo
from agentmon.store.runs import RunRepo
from agentmon.store.schema import init_schema
from agentmon.store.stacks import StackRepo
from agentmon.store.tasks import TaskRepo


def _store(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    return db


# ── Item 1: потокобезопасное соединение ────────────────────────────────────

def test_store_db_has_reentrant_lock_held_in_transaction(tmp_path):
    db = _store(tmp_path)
    assert isinstance(db._lock, type(threading.RLock()))
    # RLock переходит в транзакцию без самоблокировки вложенных операций.
    with db.transaction():
        db.execute("INSERT INTO stacks (name, created_at) VALUES (?, ?)", ["s", None])
        assert db.query("SELECT COUNT(*) AS c FROM stacks")[0]["c"] == 1


def test_sqlite_pragmas_set_on_connect(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    mode = db.query("PRAGMA journal_mode")[0]
    assert str(list(mode.values())[0]).lower() == "wal"
    db.close()


def test_store_db_concurrent_inserts_no_race(tmp_path):
    db = _store(tmp_path)
    errors = []

    def worker(base):
        try:
            for i in range(50):
                db.returning_id("stacks", ["name", "created_at"],
                                [f"{base}-{i}", None])
        except Exception as exc:        # pragma: no cover — диагностика
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert db.query("SELECT COUNT(*) AS c FROM stacks")[0]["c"] == 200


def test_legacy_connection_concurrent_enqueue(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/proj/a", backend="local")
    errors = []

    def worker(base):
        try:
            q = TaskQueue(db)
            for i in range(50):
                q.enqueue(p.id, f"{base}-{i}")
        except Exception as exc:        # pragma: no cover — диагностика
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(TaskQueue(db).list(p.id)) == 200


# ── Item 2: атомарный захват очереди (TOCTOU) ──────────────────────────────

def test_mark_running_claims_atomically_only_once(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/proj/a", backend="local")
    q = TaskQueue(db)
    tid = q.enqueue(p.id, "do it")

    first = q.mark_running(tid, session_id="s1")
    second = q.mark_running(tid, session_id="s2")
    assert first is True
    assert second is False
    # статус выставлен ровно одним захватом
    assert q.running_for(p.id).session_id == "s1"


def test_two_dispatchers_claim_same_task_only_one_wins(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    p = reg.add(name="a", path="/proj/a", backend="local")
    tid = TaskQueue(db).enqueue(p.id, "race")

    results = []
    barrier = threading.Barrier(2)

    def claim(sid):
        q = TaskQueue(db)
        barrier.wait()
        results.append(q.mark_running(tid, session_id=sid))

    threads = [threading.Thread(target=claim, args=(s,)) for s in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, True]       # ровно один захват удался


# ── Item 3: каскадные удаления ─────────────────────────────────────────────

def test_project_delete_cascades(tmp_path):
    db = _store(tmp_path)
    projects, tasks = ProjectRepo(db), TaskRepo(db)
    mcp, runs, stacks = McpRepo(db), RunRepo(db, clock=None), StackRepo(db)

    pid = projects.add(name="p", path="/p")
    other = projects.add(name="q", path="/q")
    tid = tasks.add(project_id=pid, name="t")
    sid = stacks.add(name="s")
    stacks.add_item(sid, tid)
    runs.add(pid, pid=111, task_id=tid)
    mid = mcp.add(name="m")
    mcp.set_for_project(pid, [mid])
    # посторонний проект не должен пострадать
    tasks.add(project_id=other, name="keep")

    projects.delete(pid)

    assert projects.get(pid) is None
    assert tasks.list(pid) == []
    assert db.query("SELECT * FROM runs WHERE project_id=?", [pid]) == []
    assert db.query("SELECT * FROM project_mcp WHERE project_id=?", [pid]) == []
    assert db.query("SELECT * FROM stack_items WHERE task_id=?", [tid]) == []
    # сам MCP остаётся, удалилась только привязка
    assert mcp.get(mid) is not None
    # посторонний проект цел
    assert projects.get(other) is not None
    assert len(tasks.list(other)) == 1


def test_task_delete_cascades(tmp_path):
    db = _store(tmp_path)
    projects, tasks = ProjectRepo(db), TaskRepo(db)
    runs, stacks = RunRepo(db, clock=None), StackRepo(db)

    pid = projects.add(name="p", path="/p")
    tid = tasks.add(project_id=pid, name="t")
    keep = tasks.add(project_id=pid, name="keep")
    sid = stacks.add(name="s")
    stacks.add_item(sid, tid)
    stacks.add_item(sid, keep)
    runs.add(pid, pid=1, task_id=tid)
    runs.add(pid, pid=2, task_id=keep)

    tasks.delete(tid)

    assert tasks.get(tid) is None
    assert db.query("SELECT * FROM runs WHERE task_id=?", [tid]) == []
    assert db.query("SELECT * FROM stack_items WHERE task_id=?", [tid]) == []
    # соседняя задача и её зависимые строки целы
    assert tasks.get(keep) is not None
    assert db.query("SELECT * FROM runs WHERE task_id=?", [keep]) != []
    assert db.query("SELECT * FROM stack_items WHERE task_id=?", [keep]) != []


def test_mcp_delete_cascades_bindings(tmp_path):
    db = _store(tmp_path)
    projects, mcp = ProjectRepo(db), McpRepo(db)
    pid = projects.add(name="p", path="/p")
    mid = mcp.add(name="m")
    keep = mcp.add(name="k")
    mcp.set_for_project(pid, [mid, keep])

    mcp.delete(mid)

    assert mcp.get(mid) is None
    assert db.query("SELECT * FROM project_mcp WHERE mcp_id=?", [mid]) == []
    # привязка второго MCP цела, проект цел
    assert db.query("SELECT * FROM project_mcp WHERE mcp_id=?", [keep]) != []
    assert projects.get(pid) is not None


# ── Item 4: индексы ─────────────────────────────────────────────────────────

def test_init_schema_creates_indexes(tmp_path):
    db = _store(tmp_path)
    rows = db.query("SELECT name FROM sqlite_master WHERE type='index'")
    names = {r["name"] for r in rows}
    expected = {
        "idx_tasks_project_id", "idx_tasks_project_id_status",
        "idx_runs_project_id", "idx_runs_task_id", "idx_runs_status",
        "idx_stack_items_stack_id",
        "idx_project_mcp_project_id", "idx_project_mcp_mcp_id",
    }
    assert expected <= names


def test_init_schema_indexes_idempotent(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    init_schema(db)       # повторный вызов не должен падать на индексах


# ── Item 5: транзакции стеков ───────────────────────────────────────────────

def test_add_item_concurrent_positions_unique(tmp_path):
    db = _store(tmp_path)
    stacks, tasks = StackRepo(db), TaskRepo(db)
    pid = ProjectRepo(db).add(name="p", path="/p")
    sid = stacks.add(name="s")
    task_ids = [tasks.add(project_id=pid, name=f"t{i}") for i in range(20)]

    errors = []

    def worker(tid):
        try:
            stacks.add_item(sid, tid)
        except Exception as exc:        # pragma: no cover — диагностика
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(t,)) for t in task_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    positions = [r["position"] for r in stacks.items(sid)]
    assert sorted(positions) == list(range(20))     # без дублей и пропусков


def test_reorder_is_atomic(tmp_path):
    db = _store(tmp_path)
    stacks, tasks = StackRepo(db), TaskRepo(db)
    pid = ProjectRepo(db).add(name="p", path="/p")
    sid = stacks.add(name="s")
    ids = [tasks.add(project_id=pid, name=f"t{i}") for i in range(3)]
    for t in ids:
        stacks.add_item(sid, t)

    stacks.reorder(sid, list(reversed(ids)))
    ordered = [r["task_id"] for r in stacks.items(sid)]
    assert ordered == list(reversed(ids))

"""Дымовой тест сборки точки входа."""

from fastapi.testclient import TestClient

from agentmon.__main__ import build


def test_index_served(tmp_path):
    app = build(db_path=tmp_path / "smoke.db")
    with TestClient(app) as client:
        r = client.get("/")
    assert r.status_code == 200
    assert "Agent Monitor" in r.text


def test_sessions_api(tmp_path):
    app = build(db_path=tmp_path / "smoke.db")
    with TestClient(app) as client:
        r = client.get("/api/sessions")
    assert r.status_code == 200
    assert r.json() == {"sessions": []}


def test_projects_api_starts_empty(tmp_path):
    app = build(db_path=tmp_path / "smoke.db")
    with TestClient(app) as client:
        r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == {"projects": []}


def test_running_tasks_survive_restart_detached(tmp_path):
    """Detached-модель: running-задачу на старте НЕ возвращают вслепую в очередь.

    Процессы агентов монитору не принадлежат и переживают его перезапуск;
    их прогоны лежат в БД, а разбирается с ними диспетчер по task_status.
    Поэтому build больше не вызывает requeue_running — running остаётся running.
    """
    from agentmon.queue import TaskQueue
    from agentmon.registry import ProjectRegistry, open_db
    from agentmon.run_store import RunStore

    db_path = tmp_path / "smoke.db"
    db = open_db(db_path)
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    store = RunStore(db)
    p = reg.add(name="a", path="/proj/a", backend="local")
    tid = q.enqueue(p.id, "осиротевшая")
    q.mark_running(tid, None)
    # Прогон с живым PID (текущий интерпретатор) — reconcile не должен его трогать.
    import os
    store.add(p.id, os.getpid(), task_id=tid)
    db.close()

    build(db_path=db_path)

    db2 = open_db(db_path)
    assert TaskQueue(db2).list(p.id)[0].status == "running"
    assert RunStore(db2).latest_for_task(tid)["status"] == "running"

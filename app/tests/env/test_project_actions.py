"""
Тесты действий панели проекта: обновление статусов задач из task.json и
открытие каталога проекта в VS Code.
"""
import json
import sys
import os
from pathlib import Path

from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


class RecordingPopen:
    """Заглушка subprocess.Popen: запоминает аргументы вызова."""

    def __init__(self):
        self.calls = []

    def __call__(self, args, *a, **kw):
        self.calls.append(args)
        return None


def make_client(tmp_path, popen=None):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store,
                     popen=popen)
    return TestClient(app), store


def _seed_project(store, tmp_path):
    project_path = tmp_path / "proj"
    (project_path / "tasks").mkdir(parents=True)
    pid = ProjectRepo(store).add(name="proj", path=str(project_path))
    return pid, project_path


def _write_task_json(project_path, folder, data):
    d = project_path / "tasks" / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")


# ─── refresh ──────────────────────────────────────────────────────────────

def test_refresh_pulls_status_stage_times_from_taskjson(tmp_path):
    client, store = make_client(tmp_path)
    pid, project_path = _seed_project(store, tmp_path)
    tr = TaskRepo(store)
    tid = tr.add(project_id=pid, name="T", identifier="001", status="planned")
    _write_task_json(project_path, "task#001", {
        "status": "done", "stage": "develop",
        "started_at": 100.0, "finished_at": 200.0,
    })

    r = client.post(f"/api/env/projects/{pid}/refresh")
    assert r.status_code == 200
    assert r.json()["updated"] == 1

    row = tr.get(tid)
    assert row["status"] == "done"
    assert row["stage"] == "develop"
    assert row["started_at"] == 100.0
    assert row["finished_at"] == 200.0


def test_refresh_skips_queued_and_stopped_status(tmp_path):
    """status queued/stopped управляются стеком — их из файла не перезаписываем,
    но stage/времена синхронизируем."""
    client, store = make_client(tmp_path)
    pid, project_path = _seed_project(store, tmp_path)
    tr = TaskRepo(store)
    tq = tr.add(project_id=pid, name="Q", identifier="Q", status="queued")
    ts = tr.add(project_id=pid, name="S", identifier="S", status="stopped")
    for folder in ("task#Q", "task#S"):
        _write_task_json(project_path, folder, {
            "status": "planned", "stage": "develop",
            "started_at": 5.0, "finished_at": None,
        })

    r = client.post(f"/api/env/projects/{pid}/refresh")
    assert r.status_code == 200

    assert tr.get(tq)["status"] == "queued"
    assert tr.get(ts)["status"] == "stopped"
    # stage всё равно синхронизирован
    assert tr.get(tq)["stage"] == "develop"


def test_refresh_skips_tasks_without_file(tmp_path):
    client, store = make_client(tmp_path)
    pid, _ = _seed_project(store, tmp_path)
    tr = TaskRepo(store)
    tid = tr.add(project_id=pid, name="T", identifier="001", status="planned")

    r = client.post(f"/api/env/projects/{pid}/refresh")
    assert r.status_code == 200
    assert r.json()["updated"] == 0
    assert tr.get(tid)["status"] == "planned"


def test_refresh_unknown_project_404(tmp_path):
    client, _ = make_client(tmp_path)
    assert client.post("/api/env/projects/999/refresh").status_code == 404


# ─── open-vscode ────────────────────────────────────────────────────────────

def test_open_vscode_invokes_code_with_project_path(tmp_path):
    rec = RecordingPopen()
    client, store = make_client(tmp_path, popen=rec)
    pid, project_path = _seed_project(store, tmp_path)

    r = client.post(f"/api/env/projects/{pid}/open-vscode")
    assert r.status_code == 200
    assert rec.calls == [["code", str(project_path)]]


def test_open_vscode_missing_code_returns_500(tmp_path):
    def boom(args, *a, **kw):
        raise FileNotFoundError("code")

    client, store = make_client(tmp_path, popen=boom)
    pid, _ = _seed_project(store, tmp_path)

    r = client.post(f"/api/env/projects/{pid}/open-vscode")
    assert r.status_code == 500
    assert "code" in r.json()["detail"]


def test_open_vscode_unknown_project_404(tmp_path):
    rec = RecordingPopen()
    client, _ = make_client(tmp_path, popen=rec)
    assert client.post("/api/env/projects/999/open-vscode").status_code == 404


def test_refresh_transfers_stages_and_db_update(tmp_path):
    client, store = make_client(tmp_path)
    pid, project_path = _seed_project(store, tmp_path)
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(project_id=pid, name="t", identifier="100500",
                              stages_json="[]", status="planned")
    _write_task_json(project_path, "task#100500", {
        "status": "running", "stage": "develop",
        "started_at": 1.0, "finished_at": None,
        "stages": [{"name": "develop", "status": "running", "iteration": 2,
                    "started_at": 1.0, "finished_at": None}],
        "db_update": {"started_at": 2.0, "finished_at": 3.0},
    })
    r = client.post(f"/api/env/projects/{pid}/refresh")
    assert r.status_code == 200
    import json
    task = TaskRepo(store).get(tid)
    stages = json.loads(task["stages_json"])
    assert stages[0]["iteration"] == 2
    assert json.loads(task["db_update_json"]) == {"started_at": 2.0, "finished_at": 3.0}


# ─── open-report ────────────────────────────────────────────────────────────

def test_open_report_launches_code(tmp_path):
    rec = RecordingPopen()
    client, store = make_client(tmp_path, popen=rec)
    pid, project_path = _seed_project(store, tmp_path)
    d = project_path / "tasks" / "task#100500"
    d.mkdir(parents=True)
    (d / "ANALYZE.md").write_text("ok", encoding="utf-8")
    import json
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(
        project_id=pid, name="t", identifier="100500", status="running",
        stages_json=json.dumps([{"name": "analyze", "status": "done",
                                 "artifact": "ANALYZE.md"}]))
    r = client.post(f"/api/env/tasks/{tid}/open-report", json={"stage": "analyze"})
    assert r.status_code == 200
    assert rec.calls == [["code", str(d / "ANALYZE.md")]]


def test_open_report_404_when_file_missing(tmp_path):
    rec = RecordingPopen()
    client, store = make_client(tmp_path, popen=rec)
    pid, project_path = _seed_project(store, tmp_path)
    import json
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(
        project_id=pid, name="t", identifier="100500", status="running",
        stages_json=json.dumps([{"name": "analyze", "status": "done",
                                 "artifact": "ANALYZE.md"}]))
    r = client.post(f"/api/env/tasks/{tid}/open-report", json={"stage": "analyze"})
    assert r.status_code == 404
    assert rec.calls == []

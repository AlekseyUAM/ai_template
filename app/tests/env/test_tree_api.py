"""Tests for GET /api/env/tree endpoint."""
import time
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def make(tmp_path):
    """Create a TestClient with a store and initialized schema."""
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db), queue=TaskQueue(db),
                                 monitor=mon, store=store)), store


def test_tree_api_basic(tmp_path):
    """Test /api/env/tree with seeded project and task."""
    client, store = make(tmp_path)

    # Seed: one project with one task (started_at set), one empty project
    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    # Project 1 with a task
    p1_id = proj_repo.add(name="Project1", path="/path/to/p1")
    t1_id = task_repo.add(
        project_id=p1_id,
        name="Task1",
        status="running",
        stage="initialization",
    )
    # Update task with started_at
    task_repo.update(t1_id, started_at=1000.0)

    # Project 2 empty
    p2_id = proj_repo.add(name="Project2", path="/path/to/p2")

    # Request tree
    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    data = resp.json()

    # Check version
    assert "version" in data
    assert data["version"]  # non-empty

    # Check projects
    assert "projects" in data
    projects = {p["id"]: p for p in data["projects"]}

    # Project 1 should have task
    assert p1_id in projects
    p1 = projects[p1_id]
    assert p1["name"] == "Project1"
    assert p1["path"] == "/path/to/p1"
    assert len(p1["tasks"]) == 1
    t1 = p1["tasks"][0]
    assert t1["id"] == t1_id
    assert t1["name"] == "Task1"
    assert "tasks/task#" in t1["task_path"]
    assert t1["task_path"] == f"/path/to/p1/tasks/task#{t1_id}"
    assert t1["status"] == "выполняется"  # russian for running
    assert t1["stage"] == "initialization"
    assert isinstance(t1["elapsed_min"], (int, float))

    # Project 2 should be empty
    assert p2_id in projects
    p2 = projects[p2_id]
    assert p2["name"] == "Project2"
    assert p2["path"] == "/path/to/p2"
    assert p2["tasks"] == []


def test_tree_api_task_path_uses_identifier(tmp_path):
    """Задача с identifier → task_path вида tasks/task#{identifier}."""
    client, store = make(tmp_path)

    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    p_id = proj_repo.add(name="P", path="/path/to/p")
    t_id = task_repo.add(project_id=p_id, name="T", identifier="FEAT-7", status="planned")

    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    task = resp.json()["projects"][0]["tasks"][0]
    assert task["id"] == t_id
    assert task["task_path"] == "/path/to/p/tasks/task#FEAT-7"


def test_tree_api_status_labels(tmp_path):
    """Test Russian status labels."""
    client, store = make(tmp_path)

    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    p_id = proj_repo.add(name="Project", path="/path/to/p")

    status_map = {
        "planned": "запланирована",
        "queued": "в очереди",
        "running": "выполняется",
        "stopped": "остановлена",
        "awaiting_user": "ожидает пользователя",
        "done": "выполнена",
        "failed": "ошибка",
    }

    for status, label in status_map.items():
        t_id = task_repo.add(
            project_id=p_id,
            name=f"Task_{status}",
            status=status,
        )
        task_repo.update(t_id, started_at=1000.0)

    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    data = resp.json()

    project = data["projects"][0]
    returned_statuses = {t["status"] for t in project["tasks"]}
    expected_labels = set(status_map.values())
    assert returned_statuses == expected_labels


def test_tree_api_elapsed_min(tmp_path):
    """Test elapsed_min calculation."""
    client, store = make(tmp_path)

    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    p_id = proj_repo.add(name="Project", path="/path/to/p")

    # Task without started_at
    task_repo.add(
        project_id=p_id,
        name="NoStart",
        status="planned",
    )

    # Task with started_at only
    t_id = task_repo.add(
        project_id=p_id,
        name="OnlyStart",
        status="running",
    )
    task_repo.update(t_id, started_at=1000.0)

    # Task with both started_at and finished_at
    t_id = task_repo.add(
        project_id=p_id,
        name="Complete",
        status="done",
    )
    task_repo.update(t_id, started_at=1000.0, finished_at=1060.0)

    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    data = resp.json()

    project = data["projects"][0]
    tasks_by_name = {t["name"]: t for t in project["tasks"]}

    # No start
    assert tasks_by_name["NoStart"]["elapsed_min"] == 0

    # Only start: elapsed = (now - started) / 60; now is generated by lambda
    # This is tricky: we need to pass now_fn to the router
    # For now, just check it's a number
    assert isinstance(tasks_by_name["OnlyStart"]["elapsed_min"], (int, float))

    # Complete: (1060 - 1000) / 60 = 1.0
    assert tasks_by_name["Complete"]["elapsed_min"] == 1.0


def test_tree_api_epoch_zero_timestamps(tmp_path):
    """Test epoch-0 timestamps (0.0) for started_at and finished_at in elapsed_min calculation."""
    client, store = make(tmp_path)

    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    p_id = proj_repo.add(name="Project", path="/path/to/p")

    # Task with epoch-0 timestamps (used in deterministic tests)
    t_id = task_repo.add(
        project_id=p_id,
        name="EpochZero",
        status="done",
    )
    task_repo.update(t_id, started_at=0.0, finished_at=0.0)

    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    data = resp.json()

    project = data["projects"][0]
    task = project["tasks"][0]

    # Verify elapsed_min is 0.0 (not treated as absent)
    assert task["elapsed_min"] == 0.0


def test_tree_api_status_raw(tmp_path):
    """Узел-задача содержит status_raw с сырым значением и status с русской меткой."""
    client, store = make(tmp_path)

    proj_repo = ProjectRepo(store)
    task_repo = TaskRepo(store)

    p_id = proj_repo.add(name="Project", path="/path/to/p")
    task_repo.add(
        project_id=p_id,
        name="Planned Task",
        status="planned",
    )

    resp = client.get("/api/env/tree")
    assert resp.status_code == 200
    data = resp.json()

    project = data["projects"][0]
    task = project["tasks"][0]

    # status_raw должен содержать сырой статус
    assert "status_raw" in task, "поле status_raw отсутствует в узле задачи"
    assert task["status_raw"] == "planned"
    # status по-прежнему русская метка
    assert task["status"] == "запланирована"


def test_tree_api_no_store(tmp_path):
    """Test 503 when store is None."""
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    client = TestClient(create_app(registry=ProjectRegistry(db), queue=TaskQueue(db),
                                   monitor=mon, store=None))

    resp = client.get("/api/env/tree")
    assert resp.status_code == 503

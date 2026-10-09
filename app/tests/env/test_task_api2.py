"""
Тесты для task_api2.py — API задач v2 (create/stage/approve).
TestClient со store=connect(tmp)+init_schema; проект создаётся через ProjectRepo.
"""
import json
import sys
import os

import pytest
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def make_client(tmp_path):
    """Создаёт TestClient с подключённым store и инициализированной схемой."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store)
    client = TestClient(app)
    return client, store


def seed_project(store, tmp_path):
    """Создаёт проект в БД и возвращает (project_id, project_path)."""
    project_path = tmp_path / "myproject"
    project_path.mkdir()
    repo = ProjectRepo(store)
    pid = repo.add(name="test-project", path=str(project_path))
    return pid, project_path


# ─── 503 if store None ────────────────────────────────────────────────────────

def test_503_when_no_store(tmp_path):
    """Возвращает 503 если store не настроен."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=None)
    client = TestClient(app)
    r = client.post("/api/env/tasks", json={
        "project_id": 1, "name": "T", "identifier": "T-1", "goal": "G", "plan": "P",
        "constraints": "C", "tests": "T", "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 503


# ─── POST /api/env/tasks — create ────────────────────────────────────────────

def test_create_task_success(tmp_path):
    """Создание задачи: запись в БД + файлы на диске."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача 1",
        "identifier": "T-1",
        "goal": "Цель задачи",
        "plan": "План выполнения",
        "constraints": "Ограничения",
        "tests": "test_something",
        "enabled_stages": ["analyze", "plan", "tests"],
        "gated_stages": ["plan"],
    })
    assert r.status_code == 200
    data = r.json()
    assert "task" in data
    task = data["task"]
    assert task["name"] == "Задача 1"
    assert task["status"] == "planned"

    tid = task["id"]
    assert task["identifier"] == "T-1"
    task_dir = project_path / "tasks" / "task#T-1"
    assert task_dir.exists(), f"Директория задачи не создана: {task_dir}"
    assert (task_dir / "TASK.md").exists(), "TASK.md не создан"
    assert (task_dir / "task.json").exists(), "task.json не создан"


def test_create_task_disk_files_content(tmp_path):
    """TASK.md содержит goal/plan/constraints/tests; task.json содержит stages."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача файл",
        "identifier": "T-1",
        "goal": "Моя цель",
        "plan": "Мой план",
        "constraints": "Мои ограничения",
        "tests": "мои тесты",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 200
    task_dir = project_path / "tasks" / "task#T-1"

    task_md = (task_dir / "TASK.md").read_text()
    assert "Моя цель" in task_md
    assert "Мой план" in task_md
    assert "Мои ограничения" in task_md
    assert "мои тесты" in task_md

    task_json_data = json.loads((task_dir / "task.json").read_text())
    assert isinstance(task_json_data["stages"], list)


def test_create_task_persists_update_db_and_max_minutes(tmp_path):
    """update_db и max_minutes сохраняются в БД, task.json и TASK.md."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача с параметрами",
        "identifier": "P-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
        "update_db": True,
        "max_minutes": 90,
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["update_db"] == 1
    assert task["max_minutes"] == 90

    task_dir = project_path / "tasks" / "task#P-1"
    task_json_data = json.loads((task_dir / "task.json").read_text())
    assert task_json_data["update_db"] is True
    assert task_json_data["max_minutes"] == 90
    task_md = (task_dir / "TASK.md").read_text()
    assert "90" in task_md
    assert "Обновлять базу данных и расширения" in task_md


def test_create_task_persists_mark_changes_and_developer_id(tmp_path):
    """mark_changes сохраняется везде; developer_id берётся из проекта в task.json."""
    client, store = make_client(tmp_path)
    project_path = tmp_path / "proj_dev"
    project_path.mkdir()
    pid = ProjectRepo(store).add(
        name="dev-project", path=str(project_path), identifier="dev42")

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача с маркерами",
        "identifier": "M-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["develop"],
        "gated_stages": [],
        "mark_changes": True,
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["mark_changes"] == 1

    task_dir = project_path / "tasks" / "task#M-1"
    task_json_data = json.loads((task_dir / "task.json").read_text())
    assert task_json_data["mark_changes"] is True
    assert task_json_data["developer_id"] == "dev42"
    task_md = (task_dir / "TASK.md").read_text()
    assert "Выделять изменения в коде идентификаторами: да" in task_md


def test_create_task_defaults_mark_changes_false(tmp_path):
    """Без поля mark_changes задача создаётся с выключенным флагом."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Без маркеров",
        "identifier": "NM-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["develop"],
        "gated_stages": [],
    })
    assert r.status_code == 200
    assert r.json()["task"]["mark_changes"] == 0
    task_json_data = json.loads(
        (project_path / "tasks" / "task#NM-1" / "task.json").read_text())
    assert task_json_data["mark_changes"] is False
    task_md = (project_path / "tasks" / "task#NM-1" / "TASK.md").read_text()
    assert "Выделять изменения в коде идентификаторами: нет" in task_md


def test_create_task_defaults_update_db_false_max_minutes_60(tmp_path):
    """Без полей: update_db=0 (выкл), max_minutes=60 по умолчанию."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Дефолтная задача",
        "identifier": "D-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["update_db"] == 0
    assert task["max_minutes"] == 60


def test_create_task_persists_interactive(tmp_path):
    """interactive сохраняется в БД, но НЕ пишется в task.json и TASK.md
    (нужен только монитору агентов)."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Интерактивная задача",
        "identifier": "I-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
        "interactive": True,
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["interactive"] == 1

    task_dir = project_path / "tasks" / "task#I-1"
    task_json_data = json.loads((task_dir / "task.json").read_text())
    assert "interactive" not in task_json_data
    task_md = (task_dir / "TASK.md").read_text()
    assert "Интерактивный режим" not in task_md


def test_create_task_defaults_interactive_off(tmp_path):
    """Без поля: interactive=0 (выкл) по умолчанию."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Дефолтная интерактивность",
        "identifier": "DI-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 200
    task = r.json()["task"]
    assert task["interactive"] == 0


def test_create_task_rejects_bad_max_minutes(tmp_path):
    """max_minutes должен быть положительным целым → иначе 400."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Плохая длительность",
        "identifier": "B-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
        "max_minutes": 0,
    })
    assert r.status_code == 400
    errors = r.json().get("detail", {}).get("errors", [])
    assert any("длительн" in e.lower() for e in errors)


def test_create_task_requires_identifier(tmp_path):
    """Пустой идентификатор → 400, задача не создаётся."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача",
        "identifier": "",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 400
    errors = r.json().get("detail", {}).get("errors", [])
    assert any("идентификатор" in e.lower() for e in errors)


def test_create_task_duplicate_identifier_400(tmp_path):
    """Повторный идентификатор в рамках проекта → 400."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    body = {
        "project_id": pid, "name": "Задача", "identifier": "DUP",
        "goal": "Цель", "plan": "План", "constraints": "Ограничения",
        "tests": "", "enabled_stages": ["analyze"], "gated_stages": [],
    }
    assert client.post("/api/env/tasks", json=body).status_code == 200
    r2 = client.post("/api/env/tasks", json={**body, "name": "Другая"})
    assert r2.status_code == 400
    errors = r2.json().get("detail", {}).get("errors", [])
    assert any("идентификатор" in e.lower() for e in errors)


def test_create_task_dir_named_by_identifier(tmp_path):
    """Каталог задачи именуется task#{identifier}."""
    client, store = make_client(tmp_path)
    pid, project_path = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid, "name": "Задача", "identifier": "FEAT-42",
        "goal": "Цель", "plan": "План", "constraints": "Ограничения",
        "tests": "", "enabled_stages": ["analyze"], "gated_stages": [],
    })
    assert r.status_code == 200
    assert (project_path / "tasks" / "task#FEAT-42").is_dir()


def test_create_task_validation_400_empty_name(tmp_path):
    """Пустое имя → 400 с ошибками валидации."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 400
    data = r.json()
    # FastAPI оборачивает detail → {"detail": {"errors": [...]}}
    errors = data.get("errors") or data.get("detail", {}).get("errors", [])
    assert errors, f"Ожидались ошибки валидации, получено: {data}"


def test_create_task_validation_400_testing_without_tests(tmp_path):
    """testing без tests → 400 с ошибкой про testing/tests."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["testing"],
        "gated_stages": [],
    })
    assert r.status_code == 400
    data = r.json()
    errors = data.get("errors") or data.get("detail", {}).get("errors", [])
    assert errors, f"Ожидались ошибки валидации, получено: {data}"
    errors_str = " ".join(errors).lower()
    assert "testing" in errors_str


# ─── GET /api/env/tasks — list & get ─────────────────────────────────────────

def test_list_tasks_empty(tmp_path):
    """GET /api/env/tasks → пустой список когда нет задач."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r = client.get("/api/env/tasks", params={"project_id": pid})
    assert r.status_code == 200
    assert r.json()["tasks"] == []


def test_list_tasks_filter_by_project(tmp_path):
    """GET /api/env/tasks?project_id= фильтрует по проекту."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    # Создаём задачу
    client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача 1",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "тесты",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })

    r = client.get("/api/env/tasks", params={"project_id": pid})
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["name"] == "Задача 1"


def test_get_task_by_id(tmp_path):
    """GET /api/env/tasks/{id} → возвращает задачу."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача get",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r = client.get(f"/api/env/tasks/{tid}")
    assert r.status_code == 200
    assert r.json()["task"]["id"] == tid


def test_get_task_not_found(tmp_path):
    """GET /api/env/tasks/9999 → 404."""
    client, store = make_client(tmp_path)

    r = client.get("/api/env/tasks/9999")
    assert r.status_code == 404


# ─── DELETE /api/env/tasks/{id} ───────────────────────────────────────────────

def test_delete_task(tmp_path):
    """DELETE /api/env/tasks/{id} удаляет задачу."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Удалить меня",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r_del = client.delete(f"/api/env/tasks/{tid}")
    assert r_del.status_code == 200

    r_get = client.get(f"/api/env/tasks/{tid}")
    assert r_get.status_code == 404


# ─── POST /api/env/tasks/{id}/stage — stage update ───────────────────────────

def test_stage_update_gated_done_becomes_awaiting_user(tmp_path):
    """Гейтированный этап переходит в done → задача awaiting_user."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    # Создаём задачу с гейтом на 'analyze', и есть 'plan' после
    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Гейт задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze", "plan"],
        "gated_stages": ["analyze"],
    })
    assert r_create.status_code == 200
    tid = r_create.json()["task"]["id"]

    # Помечаем 'analyze' как done
    r_stage = client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "done",
    })
    assert r_stage.status_code == 200
    task = r_stage.json()["task"]
    # Гейтированный этап done и не approved → awaiting_user
    assert task["status"] == "awaiting_user", (
        f"Ожидался статус awaiting_user, получен: {task['status']}"
    )


def test_stage_update_non_gated_done_stays_planned(tmp_path):
    """Не-гейтированный этап done → задача не awaiting_user."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Без гейта",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze", "plan"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r_stage = client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "done",
    })
    assert r_stage.status_code == 200
    task = r_stage.json()["task"]
    # Нет гейта → не awaiting_user
    assert task["status"] != "awaiting_user"


def test_stage_update_with_changed_files(tmp_path):
    """Stage update с changed_files сохраняет файлы."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Файловая задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r_stage = client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "done",
        "changed_files": ["file1.py", "file2.py"],
    })
    assert r_stage.status_code == 200
    task = r_stage.json()["task"]
    stages = json.loads(task["stages_json"])
    analyze = next(s for s in stages if s["name"] == "analyze")
    assert "file1.py" in analyze["changed_files"]
    assert "file2.py" in analyze["changed_files"]


def test_stage_update_task_not_found(tmp_path):
    """POST /api/env/tasks/9999/stage → 404."""
    client, store = make_client(tmp_path)

    r = client.post("/api/env/tasks/9999/stage", json={
        "stage": "analyze",
        "status": "done",
    })
    assert r.status_code == 404


# ─── POST /api/env/tasks/{id}/approve ────────────────────────────────────────

def test_approve_clears_awaiting_user(tmp_path):
    """Approve гейтированного этапа снимает awaiting_user → planned."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Approve задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze", "plan"],
        "gated_stages": ["analyze"],
    })
    tid = r_create.json()["task"]["id"]

    # Переводим analyze в done → awaiting_user
    client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "done",
    })

    # Approve
    r_approve = client.post(f"/api/env/tasks/{tid}/approve", json={"stage": "analyze"})
    assert r_approve.status_code == 200
    task = r_approve.json()["task"]
    # После approve не должен быть awaiting_user
    assert task["status"] != "awaiting_user", (
        f"После approve статус должен смениться с awaiting_user, получен: {task['status']}"
    )

    # Проверяем, что approved=True в stages_json
    stages = json.loads(task["stages_json"])
    analyze = next(s for s in stages if s["name"] == "analyze")
    assert analyze["approved"] is True


def test_approve_task_not_found(tmp_path):
    """POST /api/env/tasks/9999/approve → 404."""
    client, store = make_client(tmp_path)

    r = client.post("/api/env/tasks/9999/approve", json={"stage": "analyze"})
    assert r.status_code == 404


# ─── GET /api/env/tasks/{id}/overall ─────────────────────────────────────────

def test_get_overall(tmp_path):
    """GET /api/env/tasks/{id}/overall → {overall}."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Overall задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r = client.get(f"/api/env/tasks/{tid}/overall")
    assert r.status_code == 200
    assert "overall" in r.json()


def test_get_overall_not_found(tmp_path):
    """GET /api/env/tasks/9999/overall → 404."""
    client, store = make_client(tmp_path)

    r = client.get("/api/env/tasks/9999/overall")
    assert r.status_code == 404


# ─── New validation tests ─────────────────────────────────────────────────────

def test_create_task_missing_project_id_400(tmp_path):
    """POST /api/env/tasks без project_id → 400."""
    client, store = make_client(tmp_path)

    r = client.post("/api/env/tasks", json={
        "name": "Задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "тесты",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    assert r.status_code == 400
    errors = r.json().get("detail", {}).get("errors", [])
    assert any("project_id" in e for e in errors)


def test_stage_update_missing_status_400(tmp_path):
    """POST /api/env/tasks/{id}/stage без status → 400."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r = client.post(f"/api/env/tasks/{tid}/stage", json={"stage": "analyze"})
    assert r.status_code == 400


def test_stage_update_unknown_stage_400(tmp_path):
    """POST /api/env/tasks/{id}/stage с несуществующим этапом → 400."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    r = client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "nonexistent_stage",
        "status": "done",
    })
    assert r.status_code == 400
    assert "неизвестный этап" in r.json().get("detail", "")


def test_create_task_nonexistent_project_no_db_record(tmp_path):
    """POST /api/env/tasks с несуществующим project_id → ошибка и задача НЕ создаётся в БД."""
    client, store = make_client(tmp_path)
    # НЕ создаём проект — project_id=9999 не существует

    r = client.post("/api/env/tasks", json={
        "project_id": 9999,
        "name": "Задача без проекта",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "тесты",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    # Должна быть ошибка (400 по текущему коду)
    assert r.status_code in (400, 404), f"Ожидался 400/404, получен {r.status_code}"

    # Главное: задача НЕ должна появиться в БД
    from agentmon.store.tasks import TaskRepo
    task_repo = TaskRepo(store)
    tasks = task_repo.list()
    assert tasks == [], (
        f"Задача НЕ должна создаваться при несуществующем project_id, "
        f"но в БД найдено: {tasks}"
    )


def test_changed_files_dedup(tmp_path):
    """Два вызова /stage с одним файлом → файл в списке только один раз."""
    client, store = make_client(tmp_path)
    pid, _ = seed_project(store, tmp_path)

    r_create = client.post("/api/env/tasks", json={
        "project_id": pid,
        "name": "Дедуп задача",
        "identifier": "T-1",
        "goal": "Цель",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "",
        "enabled_stages": ["analyze"],
        "gated_stages": [],
    })
    tid = r_create.json()["task"]["id"]

    client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "in_progress",
        "changed_files": ["file1.py", "file2.py"],
    })

    r = client.post(f"/api/env/tasks/{tid}/stage", json={
        "stage": "analyze",
        "status": "done",
        "changed_files": ["file1.py", "file3.py"],
    })
    assert r.status_code == 200
    stages = json.loads(r.json()["task"]["stages_json"])
    analyze = next(s for s in stages if s["name"] == "analyze")
    changed = analyze["changed_files"]
    # file1.py should appear only once despite being sent twice
    assert changed.count("file1.py") == 1
    assert "file2.py" in changed
    assert "file3.py" in changed

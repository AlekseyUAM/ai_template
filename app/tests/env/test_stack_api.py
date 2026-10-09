"""Тесты API стеков (stack_api.py).

Покрывает:
- GET /api/env/stacks — форма ответа (stacks с items);
- POST /api/env/stacks — создание стека;
- DELETE /api/env/stacks/{id} — удаление + monitor.stop при наличии прогонов;
- POST /api/env/stacks/{id}/items — добавление элемента (только planned → 400 иначе);
- DELETE /api/env/stacks/{id}/items/{item_id} — удаление элемента;
- POST /api/env/stacks/{id}/reorder — только для не-running (running → 400);
- POST /api/env/stacks/{id}/start — статус running;
- POST /api/env/stacks/{id}/stop — статус stopped + monitor.stop вызван;
- POST /api/env/tasks/test — создаёт задачу kind=test, status=planned;
- 503 если store=None.
"""
import os
import sys

import pytest
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


# ─── фейковый монитор ─────────────────────────────────────────────────────────

class FakeMonitor:
    """Двойник Monitor для изоляции API от реальных процессов."""

    def __init__(self):
        self.stopped: list = []   # записи project-like объектов, переданных в stop
        self._alive: set = set()  # project_id с живым прогоном

    def stop(self, project, mode="interrupt"):
        self.stopped.append(project)

    def is_alive(self, project) -> bool:
        return project.id in self._alive

    # заглушки для совместимости с Monitor-интерфейсом
    def start(self, project, prompt="", task_id=None, cmd=None):
        pass

    def task_status(self, task_id):
        return None

    def last_error(self, project):
        return None

    def sessions(self):
        return []


# ─── вспомогательная фабрика ──────────────────────────────────────────────────

def make_client(tmp_path):
    """Создаёт TestClient с настроенным store и FakeMonitor."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = FakeMonitor()
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store)
    client = TestClient(app)
    return client, store, mon


def seed_project_and_task(store, tmp_path, task_status="planned"):
    """Создаёт проект и одну задачу, возвращает (project_id, task_id)."""
    pr = ProjectRepo(store)
    tr = TaskRepo(store)
    project_path = tmp_path / "myproject"
    project_path.mkdir(exist_ok=True)
    pid = pr.add(name="test-project", path=str(project_path))
    tid = tr.add(project_id=pid, name="тест-задача", status=task_status)
    return pid, tid


# ─── 503 если store=None ──────────────────────────────────────────────────────

def test_503_when_no_store(tmp_path):
    """Все маршруты стеков возвращают 503 если store не настроен."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = FakeMonitor()
    app = create_app(registry=registry, queue=queue, monitor=mon, store=None)
    client = TestClient(app)
    r = client.get("/api/env/stacks")
    assert r.status_code == 503


# ─── GET /api/env/stacks ──────────────────────────────────────────────────────

def test_get_stacks_empty(tmp_path):
    """GET /api/env/stacks → {stacks: []} если нет стеков."""
    client, store, mon = make_client(tmp_path)
    r = client.get("/api/env/stacks")
    assert r.status_code == 200
    data = r.json()
    assert "stacks" in data
    assert data["stacks"] == []


def test_get_stacks_with_items(tmp_path):
    """GET /api/env/stacks → форма ответа: stacks с items (item_id, task_id, task_name...)."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path)

    # создаём стек и добавляем задачу
    sr = StackRepo(store)
    stack_id = sr.add(name="Стек А")
    sr.add_item(stack_id, tid)

    r = client.get("/api/env/stacks")
    assert r.status_code == 200
    stacks = r.json()["stacks"]
    assert len(stacks) == 1
    st = stacks[0]
    assert st["id"] == stack_id
    assert st["name"] == "Стек А"
    assert st["status"] == "idle"
    assert len(st["items"]) == 1
    item = st["items"][0]
    assert item["task_id"] == tid
    assert item["task_name"] == "тест-задача"
    assert item["project_id"] == pid
    assert item["task_status"] == "planned"
    assert "item_id" in item


# ─── POST /api/env/stacks ─────────────────────────────────────────────────────

def test_create_stack(tmp_path):
    """POST /api/env/stacks {name} → создаёт стек со статусом idle."""
    client, store, mon = make_client(tmp_path)
    r = client.post("/api/env/stacks", json={"name": "Новый стек"})
    assert r.status_code == 200
    data = r.json()
    assert "stack" in data
    stack = data["stack"]
    assert stack["name"] == "Новый стек"
    assert stack["status"] == "idle"
    assert "id" in stack


# ─── DELETE /api/env/stacks/{id} ─────────────────────────────────────────────

def test_delete_stack(tmp_path):
    """DELETE /api/env/stacks/{id} → удаляет стек; повторный GET не возвращает его."""
    client, store, mon = make_client(tmp_path)
    r_create = client.post("/api/env/stacks", json={"name": "Удалить"})
    stack_id = r_create.json()["stack"]["id"]

    r_del = client.delete(f"/api/env/stacks/{stack_id}")
    assert r_del.status_code == 200
    assert r_del.json()["ok"] is True

    stacks = client.get("/api/env/stacks").json()["stacks"]
    assert not any(s["id"] == stack_id for s in stacks)


def test_delete_stack_stops_running_task(tmp_path):
    """DELETE стека с running задачей → monitor.stop вызван."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="running")

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек с прогоном")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, tid)
    # пометим проект как живой
    mon._alive.add(pid)

    r = client.delete(f"/api/env/stacks/{stack_id}")
    assert r.status_code == 200
    assert len(mon.stopped) == 1


# ─── POST /api/env/stacks/{id}/items ─────────────────────────────────────────

def test_add_item_planned_ok(tmp_path):
    """POST /{id}/items с planned-задачей → 200 {ok}."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="planned")

    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]

    r = client.post(f"/api/env/stacks/{stack_id}/items", json={"task_id": tid})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_add_item_interactive_task_400(tmp_path):
    """POST /{id}/items с интерактивной planned-задачей → 400 (её нельзя в стек)."""
    client, store, mon = make_client(tmp_path)
    pr = ProjectRepo(store)
    tr = TaskRepo(store)
    project_path = tmp_path / "myproject"
    project_path.mkdir(exist_ok=True)
    pid = pr.add(name="test-project", path=str(project_path))
    tid = tr.add(project_id=pid, name="интерактивная", status="planned", interactive=1)

    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]

    r = client.post(f"/api/env/stacks/{stack_id}/items", json={"task_id": tid})
    assert r.status_code == 400
    assert "вручную" in r.json().get("detail", "")


def test_add_item_non_interactive_task_ok(tmp_path):
    """POST /{id}/items с обычной (не интерактивной) planned-задачей → 200."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="planned")

    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]

    r = client.post(f"/api/env/stacks/{stack_id}/items", json={"task_id": tid})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_add_item_non_planned_400(tmp_path):
    """POST /{id}/items с задачей не в статусе planned → 400."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="running")

    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]

    r = client.post(f"/api/env/stacks/{stack_id}/items", json={"task_id": tid})
    assert r.status_code == 400


# ─── DELETE /api/env/stacks/{id}/items/{item_id} ─────────────────────────────

def test_remove_item(tmp_path):
    """DELETE /{id}/items/{item_id} → удаляет элемент из стека."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path)

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек")
    item_id = sr.add_item(stack_id, tid)

    r = client.delete(f"/api/env/stacks/{stack_id}/items/{item_id}")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # проверяем что элемент удалён
    items = sr.items(stack_id)
    assert len(items) == 0


# ─── POST /api/env/stacks/{id}/reorder ───────────────────────────────────────

def test_reorder_idle_ok(tmp_path):
    """POST /{id}/reorder для idle-стека → 200."""
    client, store, mon = make_client(tmp_path)
    pr = ProjectRepo(store)
    tr = TaskRepo(store)
    project_path = tmp_path / "proj"
    project_path.mkdir()
    pid = pr.add(name="proj", path=str(project_path))
    t1 = tr.add(project_id=pid, name="t1")
    t2 = tr.add(project_id=pid, name="t2")

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек")
    sr.add_item(stack_id, t1)
    sr.add_item(stack_id, t2)

    r = client.post(f"/api/env/stacks/{stack_id}/reorder", json={"task_ids": [t2, t1]})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_reorder_running_400(tmp_path):
    """POST /{id}/reorder для running-стека → 400."""
    client, store, mon = make_client(tmp_path)
    sr = StackRepo(store)
    stack_id = sr.add(name="Стек")
    sr.set_status(stack_id, "running")

    r = client.post(f"/api/env/stacks/{stack_id}/reorder", json={"task_ids": []})
    assert r.status_code == 400


# ─── POST /api/env/stacks/{id}/start ─────────────────────────────────────────

def test_start_stack(tmp_path):
    """POST /{id}/start → статус стека становится running."""
    client, store, mon = make_client(tmp_path)
    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]

    r = client.post(f"/api/env/stacks/{stack_id}/start")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    sr = StackRepo(store)
    assert sr.get(stack_id)["status"] == "running"


# ─── POST /api/env/stacks/{id}/stop ──────────────────────────────────────────

def test_stop_stack(tmp_path):
    """POST /{id}/stop → статус stopped + monitor.stop вызван для running-задачи."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="running")

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, tid)
    mon._alive.add(pid)

    r = client.post(f"/api/env/stacks/{stack_id}/stop")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    assert sr.get(stack_id)["status"] == "stopped"
    assert len(mon.stopped) == 1


def test_stop_stack_no_running_task(tmp_path):
    """POST /{id}/stop для стека без running-задач → 200 без вызова monitor.stop."""
    client, store, mon = make_client(tmp_path)
    r_st = client.post("/api/env/stacks", json={"name": "Стек"})
    stack_id = r_st.json()["stack"]["id"]
    client.post(f"/api/env/stacks/{stack_id}/start")

    r = client.post(f"/api/env/stacks/{stack_id}/stop")
    assert r.status_code == 200
    assert len(mon.stopped) == 0


# ─── POST /api/env/tasks/test ─────────────────────────────────────────────────

def test_create_test_task(tmp_path):
    """POST /api/env/tasks/test → создаёт задачу kind=test, status=planned."""
    client, store, mon = make_client(tmp_path)
    pid, _ = seed_project_and_task(store, tmp_path)

    r = client.post("/api/env/tasks/test", json={"project_id": pid})
    assert r.status_code == 200
    data = r.json()
    assert "task" in data
    task = data["task"]
    assert task["kind"] == "test"
    assert task["status"] == "planned"
    assert task["project_id"] == pid


def test_create_test_task_custom_name(tmp_path):
    """POST /api/env/tasks/test с name → задача получает это имя."""
    client, store, mon = make_client(tmp_path)
    pid, _ = seed_project_and_task(store, tmp_path)

    r = client.post("/api/env/tasks/test", json={"project_id": pid, "name": "Моя тест-задача"})
    assert r.status_code == 200
    assert r.json()["task"]["name"] == "Моя тест-задача"


def test_create_test_task_default_name(tmp_path):
    """POST /api/env/tasks/test без name → задача называется 'Тест'."""
    client, store, mon = make_client(tmp_path)
    pid, _ = seed_project_and_task(store, tmp_path)

    r = client.post("/api/env/tasks/test", json={"project_id": pid})
    assert r.status_code == 200
    assert r.json()["task"]["name"] == "Тест"


def test_create_test_task_invalid_project_400(tmp_path):
    """POST /api/env/tasks/test с несуществующим project_id → 400."""
    client, store, mon = make_client(tmp_path)
    r = client.post("/api/env/tasks/test", json={"project_id": 9999})
    assert r.status_code == 400


# ─── C2: задача не может быть в двух стеках ───────────────────────────────────

def test_add_item_duplicate_task_400(tmp_path):
    """Добавление одной задачи в два разных стека → 400 при второй попытке."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="planned")

    # первый стек
    r1 = client.post("/api/env/stacks", json={"name": "Стек 1"})
    stack1_id = r1.json()["stack"]["id"]

    # второй стек
    r2 = client.post("/api/env/stacks", json={"name": "Стек 2"})
    stack2_id = r2.json()["stack"]["id"]

    # добавляем в первый — должно пройти
    r_add1 = client.post(f"/api/env/stacks/{stack1_id}/items", json={"task_id": tid})
    assert r_add1.status_code == 200, f"ожидали 200, получили {r_add1.status_code}"

    # добавляем ту же задачу во второй — должно вернуть 400
    r_add2 = client.post(f"/api/env/stacks/{stack2_id}/items", json={"task_id": tid})
    assert r_add2.status_code == 400, (
        f"ожидали 400 при дублировании задачи в стеке, получили {r_add2.status_code}"
    )
    assert "уже в стеке" in r_add2.json().get("detail", "")


# ─── I3: stop_stack не вызывает monitor.stop если проект не alive ─────────────

def test_stop_stack_sets_task_status_stopped(tmp_path):
    """POST /{id}/stop → задача, бывшая running, получает статус stopped."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="running")

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, tid)
    mon._alive.add(pid)

    r = client.post(f"/api/env/stacks/{stack_id}/stop")
    assert r.status_code == 200

    tr = TaskRepo(store)
    task = tr.get(tid)
    assert task["status"] == "stopped", (
        f"ожидали статус 'stopped', получили '{task['status']}'"
    )


def test_stop_stack_not_alive_no_monitor_stop(tmp_path):
    """POST /{id}/stop для running-задачи, но проект не alive → monitor.stop НЕ вызван."""
    client, store, mon = make_client(tmp_path)
    pid, tid = seed_project_and_task(store, tmp_path, task_status="running")

    sr = StackRepo(store)
    stack_id = sr.add(name="Стек без живого прогона")
    sr.set_status(stack_id, "running")
    sr.add_item(stack_id, tid)
    # НЕ добавляем pid в mon._alive — проект не alive

    r = client.post(f"/api/env/stacks/{stack_id}/stop")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # monitor.stop не должен быть вызван
    assert len(mon.stopped) == 0, (
        f"monitor.stop не должен вызываться для не-alive проекта, "
        f"но было вызовов: {len(mon.stopped)}"
    )

"""Тесты страницы справочника задач (tasks)."""
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def test_tasks_page(tmp_path):
    """GET /tasks должен вернуть 200 с заголовком 'Задачи' и таблицей."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    client = TestClient(create_app(registry=registry, queue=queue, monitor=mon, store=store))

    r = client.get("/tasks")
    assert r.status_code == 200
    assert "Задачи" in r.text
    assert "Статус" in r.text

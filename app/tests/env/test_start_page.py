"""Tests for new start page at /."""
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def _client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db),
                                 queue=TaskQueue(db), monitor=mon, store=store))


def test_index_returns_200_with_expected_content(tmp_path):
    """GET / → 200 and body contains Agent Monitor, Проекты и задачи, Выполнение."""
    client = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert "Agent Monitor" in r.text
    assert "Проекты и задачи" in r.text
    assert "Выполнение" in r.text

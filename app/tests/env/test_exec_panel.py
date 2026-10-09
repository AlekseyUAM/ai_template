"""Tests for the execution panel (Выполнение) on the start page.

Tests that:
1. GET / → 200 and body contains 'Выполнение' markup and stack-related elements
2. GET /static/start.js → 200 and contains /api/env/stacks endpoints
3. (Drag-drop behavior not unit-tested, only markup/script presence verified)
"""
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
    """Create a test client with in-memory DB and store."""
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(
        ProjectRegistry(db),
        FakeBackends(None),
        generating_window=10.0,
        now_fn=lambda: 1.0,
    )
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return TestClient(
        create_app(
            registry=ProjectRegistry(db),
            queue=TaskQueue(db),
            monitor=mon,
            store=store,
        )
    )


def test_index_has_execution_panel_markup(tmp_path):
    """GET / → 200 and body contains Выполнение panel and stack elements."""
    client = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert "Выполнение" in r.text
    # Check for execution panel buttons/structure
    assert "Создать стек" in r.text or "стек" in r.text.lower()


def test_static_start_js_loaded(tmp_path):
    """GET /static/start.js → 200 and contains stack API references."""
    client = _client(tmp_path)
    r = client.get("/static/start.js")
    assert r.status_code == 200
    # Check that the script references the stacks API
    assert "/api/env/stacks" in r.text
    # Check for test task endpoint
    assert "/api/env/tasks/test" in r.text

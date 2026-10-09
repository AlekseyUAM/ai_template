"""Tests that all served pages include shared header.js and correct CSS path."""
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema

import sys, os
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


ROUTES = ["/", "/projects", "/tasks", "/mcp", "/project-wizard", "/task-wizard"]


def test_all_pages_return_200(tmp_path):
    client = _client(tmp_path)
    for route in ROUTES:
        r = client.get(route)
        assert r.status_code == 200, f"{route} returned {r.status_code}"


def test_all_pages_have_header_js(tmp_path):
    client = _client(tmp_path)
    for route in ROUTES:
        r = client.get(route)
        assert "/static/header.js" in r.text, f"{route} missing /static/header.js"


def test_all_pages_have_correct_css_path(tmp_path):
    client = _client(tmp_path)
    for route in ROUTES:
        r = client.get(route)
        assert "/static/github-dark.css" in r.text, \
            f"{route} missing /static/github-dark.css"
        assert 'href="/github-dark.css"' not in r.text, \
            f"{route} has wrong bare /github-dark.css path"


def test_header_js_sets_document_title(tmp_path):
    """GET /static/header.js → содержит установку document.title с 'Agent Monitor v'."""
    client = _client(tmp_path)
    r = client.get("/static/header.js")
    assert r.status_code == 200
    assert "document.title" in r.text, \
        "header.js does not set document.title"
    assert "Agent Monitor v" in r.text, \
        "header.js does not set document.title to 'Agent Monitor v...'"

from pathlib import Path
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402

WEB = Path(__file__).resolve().parents[2] / "web"


def _client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    return TestClient(create_app(registry=ProjectRegistry(db),
                                 queue=TaskQueue(db), monitor=mon))


def test_index_has_no_chat():
    """New start page: contains Agent Monitor, no chat references."""
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "chatview" not in html and "chatlog" not in html
    assert "Чат" not in html
    # New start page must have the expected sections
    assert "Agent Monitor" in html
    assert "Проекты и задачи" in html


def test_message_route_removed(tmp_path):
    client = _client(tmp_path)
    r = client.post("/api/projects/1/message", json={"text": "x"})
    assert r.status_code == 404

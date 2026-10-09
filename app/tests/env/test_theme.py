from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def _client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    return TestClient(create_app(registry=ProjectRegistry(db),
                                 queue=TaskQueue(db), monitor=mon))


def test_css_served(tmp_path):
    r = _client(tmp_path).get("/static/github-dark.css")
    assert r.status_code == 200
    assert "#0d1117" in r.text


def test_wizard_pages_link_stylesheet(tmp_path):
    client = _client(tmp_path)
    for path in ("/project-wizard", "/task-wizard"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        assert "github-dark.css" in r.text, f"{path} missing stylesheet link"

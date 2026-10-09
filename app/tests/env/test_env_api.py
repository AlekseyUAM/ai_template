# app/tests/env/test_env_api.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends    # noqa: E402


def make_client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    mon = Monitor(reg, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    return TestClient(create_app(registry=reg, queue=q, monitor=mon)), reg


def payload(project_dir):
    return {
        "config": {
            "schema_version": 1, "project_name": "demo",
            "project_dir": str(project_dir), "developer_id": "i",
            "developer_email": "i@e.ru", "platform_dir": "/opt/1cv8",
            "platform_version": "8.3.27.1786", "db_kind": "file",
            "db_connection": "/b", "web_publication": "",
            "mcp": [{"id": "1c-naparnic", "enabled": True, "mode": "external",
                     "endpoint": "http://h:9000/sse", "secret_env": None}],
            "agents": [{"agent": "developer", "model": "claude-opus-4-8",
                        "effort": "high"}],
        },
        "update": False, "dump_cf": False, "dump_cfe": False,
    }


def test_create_environment_registers_project(tmp_path):
    client, reg = make_client(tmp_path)
    proj_dir = tmp_path / "demo"
    proj_dir.mkdir()
    r = client.post("/api/environment/create", json=payload(proj_dir))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (proj_dir / ".1c-devbase.json").exists()
    assert [p.path for p in reg.list()] == [str(proj_dir)]

import importlib
from fastapi.testclient import TestClient


def test_build_serves_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTMON_DB", str(tmp_path / "agentmon.db"))
    monkeypatch.setenv("AGENTMON_DSN", str(tmp_path / "store.db"))
    from agentmon import config as cfg
    importlib.reload(cfg)
    from agentmon import __main__ as m
    importlib.reload(m)
    app = m.build()
    client = TestClient(app)
    r = client.get("/api/mcp")          # 200 (store wired), не 503
    assert r.status_code == 200
    # вернуть config к дефолту для других тестов
    monkeypatch.delenv("AGENTMON_DB", raising=False)
    monkeypatch.delenv("AGENTMON_DSN", raising=False)
    importlib.reload(cfg)

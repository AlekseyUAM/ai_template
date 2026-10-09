import importlib
from agentmon import config


def test_dsn_default_is_sqlite(monkeypatch):
    monkeypatch.delenv("AGENTMON_DSN", raising=False)
    importlib.reload(config)
    assert "postgres" not in config.DSN   # дефолт — sqlite-файл


def test_dsn_from_env(monkeypatch):
    monkeypatch.setenv("AGENTMON_DSN", "postgresql://u:p@h:5432/db")
    importlib.reload(config)
    assert config.DSN == "postgresql://u:p@h:5432/db"
    monkeypatch.delenv("AGENTMON_DSN", raising=False)
    importlib.reload(config)

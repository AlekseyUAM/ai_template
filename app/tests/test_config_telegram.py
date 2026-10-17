import importlib
import agentmon.config as config


def _reload(monkeypatch, **env):
    for k in ("AGENTMON_TG_TOKEN", "AGENTMON_TG_CHAT_IDS", "AGENTMON_PORT"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(config)


def test_token_none_when_unset(monkeypatch):
    cfg = _reload(monkeypatch)
    assert cfg.TG_TOKEN is None
    assert cfg.TG_CHAT_IDS == []


def test_chat_ids_parsed(monkeypatch):
    cfg = _reload(monkeypatch, AGENTMON_TG_TOKEN="t", AGENTMON_TG_CHAT_IDS=" 111, 222 ,,333 ")
    assert cfg.TG_TOKEN == "t"
    assert cfg.TG_CHAT_IDS == ["111", "222", "333"]


def test_local_base_url(monkeypatch):
    cfg = _reload(monkeypatch, AGENTMON_PORT="9000")
    assert cfg.local_base_url() == "http://127.0.0.1:9000"


def teardown_module(module):
    importlib.reload(config)

import importlib
import agentmon.config as config
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.telegram import runtime


def test_build_bot_none_without_token(monkeypatch):
    monkeypatch.delenv("AGENTMON_TG_TOKEN", raising=False)
    importlib.reload(config)
    importlib.reload(runtime)
    db = connect(":memory:")
    init_schema(db)
    assert runtime.build_bot(db, db, registry=None) is None


def test_build_bot_present_with_token(monkeypatch):
    monkeypatch.setenv("AGENTMON_TG_TOKEN", "T")
    monkeypatch.setenv("AGENTMON_TG_CHAT_IDS", "111")
    importlib.reload(config)
    importlib.reload(runtime)
    db = connect(":memory:")
    init_schema(db)
    built = runtime.build_bot(db, db, registry=None)
    assert built is not None
    client, bot, notifier = built
    assert notifier is not None


def teardown_module(module):
    import os
    os.environ.pop("AGENTMON_TG_TOKEN", None)
    os.environ.pop("AGENTMON_TG_CHAT_IDS", None)
    importlib.reload(config)
    importlib.reload(runtime)

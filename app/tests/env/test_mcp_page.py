from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def test_mcp_page_served(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    client = TestClient(create_app(registry=ProjectRegistry(db),
                                   queue=TaskQueue(db), monitor=mon, store=store))
    r = client.get("/mcp")
    assert r.status_code == 200
    assert "MCP-серверы" in r.text


def _client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db),
                                 queue=TaskQueue(db), monitor=mon, store=store))


def test_add_form_starts_hidden_inline(tmp_path):
    """Форма добавления скрыта инлайн-стилем — первый клик «Добавить» её открывает
    (регрессия бага двойного нажатия)."""
    html = _client(tmp_path).get("/mcp").text
    # у элемента add-form должен быть инлайновый display:none
    import re
    m = re.search(r'id="add-form"[^>]*', html)
    assert m, "нет элемента add-form"
    assert "display:none" in m.group(0).replace(" ", "")


def test_js_loads_types_endpoint(tmp_path):
    js = _client(tmp_path).get("/static/mcp.js").text
    assert "/api/mcp/types" in js


def test_js_rebuilds_table_and_has_form_actions(tmp_path):
    """loadMcp перестраивает таблицу целиком (не падает на null #mcpTable после
    empty-state), а форма содержит кнопки действия с авто-сохранением."""
    js = _client(tmp_path).get("/static/mcp.js").text
    assert '<tbody id="mcpTable">' in js        # таблица строится заново
    assert "deployFromForm" in js and "downloadFromForm" in js
    # обязательные поля — красная звёздочка (span.required), как на других страницах
    assert 'class="required"' in js
    # лог развёртывания прокручивается в зону видимости
    assert "scrollIntoView" in js


def test_mcp_page_has_required_asterisk_style(tmp_path):
    html = _client(tmp_path).get("/mcp").text
    assert ".required::after" in html and "--danger" in html

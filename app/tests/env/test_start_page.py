"""Tests for new start page at /."""
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
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db),
                                 queue=TaskQueue(db), monitor=mon, store=store))


def test_index_returns_200_with_expected_content(tmp_path):
    """GET / → 200 and body contains Agent Monitor, Проекты и задачи, Выполнение."""
    client = _client(tmp_path)
    r = client.get("/")
    assert r.status_code == 200
    assert "Agent Monitor" in r.text
    assert "Проекты и задачи" in r.text
    assert "Выполнение" in r.text


def test_start_js_has_expand_and_report(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/start.js").text
    assert "function toggleTaskDetails" in js
    assert "function openReport" in js
    assert "open-report" in js
    assert "expandedTasks" in js
    assert "5 * 60 * 1000" in js          # таймер синка 5 минут


def test_start_js_has_remove_from_stack(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/start.js").text
    assert "function removeStackItem" in js
    assert "stack-item-del" in js
    # удаление элемента из стека через существующий REST-маршрут
    assert "/items/" in js


def test_start_js_has_russian_labels_and_project_name(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/start.js").text
    # русские названия статусов задачи и этапов
    assert "function taskStatusLabel" in js
    assert "function stageStatusLabel" in js
    assert "function stageNameLabel" in js
    assert "запланирована" in js   # planned
    assert "ожидает" in js          # pending
    assert "Разработка" in js       # develop — как в мастере задачи
    # имя проекта в заголовке стека
    assert "project_name" in js


def test_start_js_has_collapsible_projects_and_stack_controls(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/start.js").text
    # сворачивание проектов в дереве
    assert "function toggleProject" in js
    assert "collapsedProjects" in js
    # заголовок стека: идентификатор + имя проекта, яркий статус
    assert "stack-head-left" in js
    assert "stack-id" in js
    assert "function stackStatusClass" in js
    # кнопки состояния + «нажата»/неактивна
    assert "pressed" in js
    assert "disabled" in js
    # развёрнутая карточка задачи: пункты столбиком
    assert "Продолжительность" in js
    # перетаскивание только для planned-задач
    assert 'draggable="${planned}"' in js

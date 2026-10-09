"""Тесты страниц мастера проекта и справочника (project-wizard, projects)."""
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


def test_project_wizard_page(tmp_path):
    """GET /project-wizard должен вернуть 200 с заголовком 'Создать проект'."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    client = TestClient(create_app(registry=registry, queue=queue, monitor=mon, store=store))

    r = client.get("/project-wizard")
    assert r.status_code == 200
    assert "Создать проект" in r.text


def test_project_wizard_is_single_page(tmp_path):
    """Страница мастера — одностраничная: все разделы на одной странице, без
    пошаговой навигации (Далее/Назад), с кнопкой Создать и проверкой базы."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    client = TestClient(create_app(registry=registry, queue=queue, monitor=mon, store=store))

    r = client.get("/project-wizard")
    assert r.status_code == 200
    html = r.text
    # без пошаговой навигации
    assert 'id="nextBtn"' not in html
    assert 'id="backBtn"' not in html
    assert 'data-step=' not in html
    # кнопки Создать и проверки базы
    assert 'id="createBtn"' in html
    assert 'id="checkDbBtn"' in html
    # поле пароля БД защищено от автозаполнения браузера
    import re
    m = re.search(r'id="dbPassword"[^>]*', html)
    assert m and 'autocomplete="new-password"' in m.group(0)
    # все разделы присутствуют на одной странице
    for title in ("Проект", "Разработчик", "Платформа", "База", "MCP", "Модели агентов", "Действия"):
        assert title in html

    # JS мастера доступен; валидации сохранены, пошаговой логики нет
    js = client.get("/static/project-wizard.js")
    assert js.status_code == 200
    assert "validate-name" in js.text
    assert "update-env" in js.text
    assert "renderStep" not in js.text


def test_projects_page(tmp_path):
    """GET /projects должен вернуть 200 с заголовком 'Проекты' и таблицей."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    client = TestClient(create_app(registry=registry, queue=queue, monitor=mon, store=store))

    r = client.get("/projects")
    assert r.status_code == 200
    assert "Проекты" in r.text
    assert "Путь" in r.text

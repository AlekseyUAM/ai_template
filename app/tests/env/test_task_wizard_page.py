# app/tests/env/test_task_wizard_page.py
from pathlib import Path
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends    # noqa: E402


def test_task_wizard_page_served(tmp_path):
    """GET /task-wizard → 200 с заголовком «Создать задачу»."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    client = TestClient(create_app(registry=registry, queue=queue, monitor=mon, store=store))
    r = client.get("/task-wizard")
    assert r.status_code == 200
    assert "Создать задачу" in r.text


WEB = Path(__file__).resolve().parents[2] / "web"


def test_task_wizard_html_has_identifier_and_textareas():
    """Карточка: поле Идентификатор (обязательное) + Цель/Ограничения многострочные."""
    html = (WEB / "task-wizard.html").read_text(encoding="utf-8")
    assert 'id="identifier"' in html and 'Идентификатор' in html
    # Цель и Ограничения — textarea (как План)
    assert '<textarea id="goal"' in html
    assert '<textarea id="constraints"' in html
    # Подсказка в поле Тесты
    assert "Описание тестов, которые необходимо создать" in html
    assert "Написание тестов" in html


def test_task_wizard_js_stage_labels_and_testing_gate():
    """Переименование этапов и запрет выбора Тестирования без Написания тестов."""
    js = (WEB / "task-wizard.js").read_text(encoding="utf-8")
    assert '"Написание тестов"' in js
    assert '"Код-ревью"' in js
    # этап analyze переименован в «Аналитика»
    assert '"Аналитика"' in js
    assert '"Анализ"' not in js
    # UI-логика зависимости testing от tests
    assert "syncTestingAvailability" in js
    assert "identifier" in js
    # новые поля уходят в payload
    assert "update_db" in js
    assert "max_minutes" in js
    # интерактивный режим уходит в payload
    assert "interactive" in js
    # флаг выделения изменений идентификаторами уходит в payload
    assert "mark_changes" in js


def test_task_wizard_html_identifier_hint_and_new_fields():
    """Подсказка идентификатора + поля «обновлять БД» и «макс. длительность»."""
    html = (WEB / "task-wizard.html").read_text(encoding="utf-8")
    # подсказка идентификатора
    assert "Идентификатор задачи (#123)" in html
    # чекбокс обновления БД и расширений
    assert 'id="update_db"' in html
    assert 'type="checkbox"' in html
    assert "Обновлять базу данных и расширения" in html
    # число минут с дефолтом 60
    assert 'id="max_minutes"' in html
    assert "Максимальная длительность выполнения" in html
    assert 'value="60"' in html
    # чекбокс интерактивного режима с подсказкой
    assert 'id="interactive"' in html
    assert "Интерактивный режим" in html
    assert "Такую задачу нельзя добавить в стек" in html
    # чекбокс выделения изменений идентификаторами
    assert 'id="mark_changes"' in html
    assert "Выделять изменения в коде идентификаторами" in html


def test_github_dark_defines_hover_vars():
    """Кнопки не сливаются с фоном: переменные hover определены в теме."""
    css = (WEB / "github-dark.css").read_text(encoding="utf-8")
    assert "--accent-hover:" in css
    assert "--btn-hover-bg:" in css

"""E2E: задача из tmp/test.md через мастер + кнопка подтверждения гейта.

Запуск (нужен живой AgentMon и установленный Chromium):

    .venv/bin/python -m playwright install chromium   # один раз
    AGENTMON_E2E=1 .venv/bin/python -m pytest \\
        app/tests/web/test_task_wizard_e2e.py -m e2e -q

Проект берётся из tmp/test.md; переопределить можно переменной окружения:

    AGENTMON_E2E=1 AGENTMON_E2E_TASK_PROJECT=ssl2_docker \\
        .venv/bin/python -m pytest app/tests/web/test_task_wizard_e2e.py -m e2e -q

Для ssh/docker-проектов файлы задачи (TASK.md, task.json, USER_FEEDBACK.md)
читаются на машине проекта: для docker — через docker exec в контейнере.

Без AGENTMON_E2E=1 модуль скипается: обычный pytest не создаёт задач и не
требует браузера.

Проверяется:
1. tmp/test.md парсится в поля мастера; задача создаётся через /task-wizard в
   проекте из файла. Созданная задача остаётся в проекте (это цель теста).
2. Поля и этапы совпадают в БД и в TASK.md/task.json на диске.
3. Кнопки гейта в стеке на /: вспомогательная задача доводится до
   awaiting_user, в панели гейта появляются ровно выстроенные «Одобрить» и
   «Замечание». Замечание возвращает этап в pending и пишет USER_FEEDBACK.md;
   одобрение снимает гейт. Вспомогательная задача и её стек удаляются.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

import pytest

if os.environ.get("AGENTMON_E2E") != "1":
    pytest.skip("e2e: включите AGENTMON_E2E=1", allow_module_level=True)

pytestmark = pytest.mark.e2e

sync_api = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
TASK_MD = ROOT / "tmp" / "test.md"
BASE_URL = os.environ.get("AGENTMON_URL", "http://127.0.0.1:8765").rstrip("/")
TIMEOUT_MS = 15000


# ── клиент живого AgentMon ────────────────────────────────────────────────────


class Api:
    """Минимальный HTTP-клиент; токен — из AGENTMON_TOKEN, если он задан."""

    def __init__(self, base_url: str):
        self.base_url = base_url

    def request(self, method: str, path: str, body=None, **params):
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        token = os.environ.get("AGENTMON_TOKEN")
        if token:
            req.add_header("X-Agentmon-Token", token)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise AssertionError(
                f"{method} {path} → HTTP {exc.code}: {detail}") from exc
        return json.loads(raw) if raw else {}

    def get(self, path: str, **params):
        return self.request("GET", path, **params)

    def post(self, path: str, body=None):
        return self.request("POST", path, body if body is not None else {})

    def delete(self, path: str):
        return self.request("DELETE", path)


# ── разбор tmp/test.md ────────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_PROJECT_RE = re.compile(r"^\s*Проект\s+(.+?)\s*$", re.MULTILINE)


def _yes(value: str, default: bool = False) -> bool:
    value = value.strip().lower()
    if value in ("да", "yes", "true", "1"):
        return True
    if value in ("нет", "no", "false", "0"):
        return False
    return default


def parse_task_md(path: Path) -> dict:
    """Поля мастера из markdown-описания задачи."""
    text = path.read_text(encoding="utf-8")
    title = _TITLE_RE.search(text)
    project = _PROJECT_RE.search(text)
    assert title, f"в {path} нет заголовка '# ...'"
    assert project, f"в {path} нет строки 'Проект <имя>'"

    matches = list(_HEADING_RE.finditer(text))
    sections = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections[match.group(1).strip().lower()] = text[match.end():end].strip()

    params = sections.get("параметры выполнения", "")
    db = re.search(r"Обновлять базу данных[^:]*:\s*(\S+)", params)
    mark = re.search(r"Выделять изменения[^:]*:\s*(\S+)", params)
    limit = re.search(r"Максимальная длительность[^:]*:\s*(\d+)", params)
    return {
        "name": title.group(1).strip(),
        "project": project.group(1).strip(),
        "goal": sections.get("цель", ""),
        "plan": sections.get("план", ""),
        "constraints": sections.get("ограничения", ""),
        "tests": sections.get("тесты", ""),
        "update_db": _yes(db.group(1)) if db else False,
        "mark_changes": _yes(mark.group(1)) if mark else False,
        "max_minutes": int(limit.group(1)) if limit else 60,
    }


# ── фикстуры ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def api() -> Api:
    client = Api(BASE_URL)
    try:
        client.get("/api/env/projects")
    except Exception as exc:  # noqa: BLE001 — нужен читаемый фейл
        pytest.fail(f"AgentMon недоступен на {BASE_URL}: {exc}")
    return client


@pytest.fixture(scope="module")
def browser():
    headed = os.environ.get("AGENTMON_E2E_HEADED") == "1"
    with sync_api.sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        yield browser
        browser.close()


@pytest.fixture()
def page(browser):
    page = browser.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    yield page
    page.close()


# ── шаги сценария ─────────────────────────────────────────────────────────────


def _find_project(api: Api, name: str) -> dict:
    projects = api.get("/api/env/projects").get("projects", [])
    for project in projects:
        if project.get("name") == name:
            return project
    raise AssertionError(
        f"проект {name!r} не найден; доступны: "
        f"{[p.get('name') for p in projects]}")


def _project_with_backend(api: Api, name: str) -> dict:
    """Проект + backend/container: файлы задач лежат на машине проекта."""
    project = _find_project(api, name)
    detail = api.get(f"/api/env/projects/{project['id']}")["project"]
    return {**project, "backend": detail.get("backend"),
            "container": detail.get("container")}


def _task_path(project: dict, *parts: str) -> str:
    return "/".join([str(project["path"]).rstrip("/"), *parts])


def _docker_exec(project: dict, *argv: str) -> subprocess.CompletedProcess:
    container = project.get("container")
    assert container, (
        f"проект {project.get('name')!r} (backend={project.get('backend')}) "
        "без имени контейнера")
    return subprocess.run(["docker", "exec", container, *argv],
                          capture_output=True, text=True, timeout=60)


def _read_task_file(project: dict, folder: str, name: str) -> str:
    """Прочитать файл задачи локально или внутри контейнера проекта."""
    if project.get("backend") == "docker":
        path = _task_path(project, "tasks", folder, name)
        result = _docker_exec(project, "cat", path)
        assert result.returncode == 0, (
            f"нет {path} в контейнере {project['container']}: "
            f"{(result.stderr or '').strip()}")
        return result.stdout
    path = Path(project["path"]) / "tasks" / folder / name
    assert path.is_file(), f"нет {path}"
    return path.read_text(encoding="utf-8")


def _remove_task_dir(project: dict, folder: str) -> None:
    if project.get("backend") == "docker":
        try:
            _docker_exec(project, "rm", "-rf",
                         _task_path(project, "tasks", folder))
        except Exception:  # noqa: BLE001 — уборка не маскирует фейл теста
            pass
        return
    shutil.rmtree(Path(project["path"]) / "tasks" / folder, ignore_errors=True)


def _unique_identifier(api: Api, project_id: int) -> str:
    """Уникальный идентификатор на прогон, чтобы тест можно было повторять."""
    fixed = (os.environ.get("AGENTMON_E2E_IDENTIFIER") or "").strip()
    if fixed:
        tasks = api.get("/api/env/tasks", project_id=project_id).get("tasks", [])
        busy = [t for t in tasks if (t.get("identifier") or "").strip() == fixed]
        assert not busy, (
            f"идентификатор {fixed!r} уже занят задачей id={busy[0]['id']}")
        return fixed
    return "#pwe2e-" + datetime.now().strftime("%y%m%d-%H%M%S")


def _create_task_via_wizard(page, project: dict, identifier: str, spec: dict) -> int:
    page.goto(BASE_URL + "/task-wizard")
    # Проекты подгружаются асинхронно — ждём не только placeholder.
    page.wait_for_function(
        "document.querySelectorAll('#owner option').length > 1")
    page.select_option("#owner", label=project["name"])
    page.fill("#name", spec["name"])
    page.fill("#identifier", identifier)
    page.fill("#goal", spec["goal"])
    page.fill("#plan", spec["plan"])
    page.fill("#constraints", spec["constraints"])
    page.fill("#tests", spec["tests"])
    page.locator("#update_db").set_checked(spec["update_db"])
    page.locator("#mark_changes").set_checked(spec["mark_changes"])
    page.fill("#max_minutes", str(spec["max_minutes"]))
    for stage in ("analyze", "develop"):
        page.check(f'.stage-enabled[data-stage="{stage}"]')
        page.check(f'.stage-gate[data-stage="{stage}"]')

    page.click('#taskForm button[type="submit"]')
    result = page.locator("#result.success")
    expect(result).to_be_visible()
    text = result.inner_text()
    assert "Задача создана" in text, text
    match = re.search(r"ID:\s*(\d+)", text)
    assert match, f"не удалось разобрать ID из баннера: {text!r}"
    return int(match.group(1))


def _assert_task_api(api: Api, tid: int, identifier: str, spec: dict) -> None:
    task = api.get(f"/api/env/tasks/{tid}")["task"]
    assert task["name"] == spec["name"]
    assert (task["identifier"] or "").strip() == identifier
    assert task["goal"] == spec["goal"]
    assert task["plan"] == spec["plan"]
    assert task["constraints"] == spec["constraints"]
    assert (task["tests"] or "") == spec["tests"]
    assert bool(task["update_db"]) is spec["update_db"]
    assert bool(task["mark_changes"]) is spec["mark_changes"]
    assert task["max_minutes"] == spec["max_minutes"]
    assert task["status"] == "planned", task["status"]

    stages = {s["name"]: s for s in json.loads(task["stages_json"])}
    for name in ("analyze", "develop"):
        assert stages[name]["enabled"] is True, name
        assert stages[name]["gate"] is True, name
        assert stages[name]["approved"] is False, name
    assert stages["plan"]["enabled"] is False


def _assert_task_files(project: dict, identifier: str, spec: dict) -> None:
    folder = f"task#{identifier}"
    text = _read_task_file(project, folder, "TASK.md")
    assert spec["goal"] in text
    assert spec["plan"] in text

    data = json.loads(_read_task_file(project, folder, "task.json"))
    stages = {s["name"]: s for s in data["stages"]}
    for name in ("analyze", "develop"):
        assert stages[name]["enabled"] is True, name
        assert stages[name]["gate"] is True, name
        assert stages[name]["approved"] is False, name


def _await_state(api: Api, aux_id: int, check, timeout: float = 10.0) -> dict:
    """Ждёт, пока состояние задачи в БД удовлетворит check(task)."""
    deadline = time.time() + timeout
    while True:
        state = api.get(f"/api/env/tasks/{aux_id}")["task"]
        if check(state):
            return state
        assert time.time() < deadline, (
            f"состояние не изменилось за {timeout}s: status={state['status']}")
        time.sleep(0.2)


def _assert_gate_buttons(api: Api, page, project: dict) -> None:
    """Замечание и одобрение гейта из UI на вспомогательной задаче."""
    stamp = datetime.now().strftime("%y%m%d-%H%M%S")
    aux_identifier = f"#pwgui-{stamp}"
    aux_id = None
    stack_id = None
    note_text = "E2E: поправь требования к реквизиту"
    folder = f"task#{aux_identifier}"
    try:
        aux = api.post("/api/env/tasks", {
            "project_id": project["id"],
            "name": "e2e: кнопки гейта",
            "identifier": aux_identifier,
            "goal": "проверить кнопки гейта",
            "plan": "вспомогательная задача, удаляется тестом",
            "constraints": "ничего не менять",
            "tests": "",
            "enabled_stages": ["analyze", "develop"],
            "gated_stages": ["analyze"],
            "update_db": False,
            "max_minutes": 5,
        })["task"]
        aux_id = aux["id"]

        # Стек не запускаем: StackDispatcher выполняет только running-стеки,
        # поэтому ни approve, ни замечание не запустят агента.
        stack_id = api.post(
            "/api/env/stacks", {"name": f"e2e-gate-{stamp}"})["stack"]["id"]
        api.post(f"/api/env/stacks/{stack_id}/items", {"task_id": aux_id})

        # analyze done + gate unapproved + develop pending → awaiting_user.
        for status in ("running", "done"):
            api.post(f"/api/env/tasks/{aux_id}/stage",
                     {"stage": "analyze", "status": status})
        state = api.get(f"/api/env/tasks/{aux_id}")["task"]
        assert state["status"] == "awaiting_user", state["status"]

        page.goto(BASE_URL + "/")
        item = page.locator(f'.stack-item[data-task-id="{aux_id}"]')
        expect(item).to_be_visible()
        item.locator(".task-row").click()
        bar = item.locator(".gate-bar")
        approve = bar.locator(".approve-btn")
        note = bar.locator(".note-btn")
        expect(bar).to_be_visible()
        expect(approve).to_have_text("Одобрить")
        expect(note).to_have_text("Замечание")

        # Кнопки выстроены ровно: один ряд, одинаковая высота и ширина.
        approve_box = approve.bounding_box()
        note_box = note.bounding_box()
        assert approve_box and note_box
        assert abs(approve_box["y"] - note_box["y"]) < 1.0, (approve_box, note_box)
        assert abs(approve_box["height"] - note_box["height"]) < 1.0, (
            approve_box, note_box)
        assert abs(approve_box["width"] - note_box["width"]) < 1.0, (
            approve_box, note_box)

        # Замечание: модалка → этап снова pending, текст в USER_FEEDBACK.md.
        note.click()
        modal = page.locator("#note-modal")
        expect(modal).to_be_visible()
        page.fill("#note-text", note_text)
        page.click("#note-send")
        expect(modal).to_be_hidden()
        expect(bar).to_have_count(0)
        state = _await_state(
            api, aux_id,
            lambda t: next(s for s in json.loads(t["stages_json"])
                           if s["name"] == "analyze")["status"] == "pending"
            and t["status"] == "planned")
        analyze = next(s for s in json.loads(state["stages_json"])
                       if s["name"] == "analyze")
        assert analyze["status"] == "pending"
        assert analyze["approved"] is False
        assert note_text in _read_task_file(
            project, folder, "USER_FEEDBACK.md")

        # Повторно доводим до awaiting_user и одобряем кнопкой «Одобрить».
        for status in ("running", "done"):
            api.post(f"/api/env/tasks/{aux_id}/stage",
                     {"stage": "analyze", "status": status})
        page.reload()
        item = page.locator(f'.stack-item[data-task-id="{aux_id}"]')
        item.locator(".task-row").click()
        bar = item.locator(".gate-bar")
        approve = bar.locator(".approve-btn")
        expect(approve).to_be_visible()
        expect(approve).to_have_text("Одобрить")

        page.once("dialog", lambda dialog: dialog.accept())
        approve.click()
        expect(bar).to_have_count(0)
        state = _await_state(
            api, aux_id,
            lambda t: next(s for s in json.loads(t["stages_json"])
                           if s["name"] == "analyze")["approved"]
            and t["status"] != "awaiting_user")
        assert state["status"] == "planned", state["status"]
    finally:
        if stack_id is not None:
            try:
                api.delete(f"/api/env/stacks/{stack_id}")
            except Exception:  # noqa: BLE001 — уборка не должна маскировать фейл
                pass
        if aux_id is not None:
            try:
                api.delete(f"/api/env/tasks/{aux_id}")
            except Exception:  # noqa: BLE001
                pass
        _remove_task_dir(project, folder)


# ── тест ──────────────────────────────────────────────────────────────────────


def test_task_from_md_and_gate_approve_button(api: Api, page) -> None:
    spec = parse_task_md(TASK_MD)
    project_name = (os.environ.get("AGENTMON_E2E_TASK_PROJECT")
                    or spec["project"]).strip()
    project = _project_with_backend(api, project_name)
    identifier = _unique_identifier(api, project["id"])
    try:
        tid = _create_task_via_wizard(page, project, identifier, spec)
        _assert_task_api(api, tid, identifier, spec)
        _assert_task_files(project, identifier, spec)
        _assert_gate_buttons(api, page, project)
    except Exception:
        shot = ROOT / "tmp" / f"e2e-task-wizard-{int(time.time())}.png"
        try:
            page.screenshot(path=str(shot), full_page=True)
            print(f"\n[e2e] скриншот падения: {shot}")
        except Exception:  # noqa: BLE001
            pass
        raise

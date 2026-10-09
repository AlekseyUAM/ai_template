# Система задач — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать работу с задачами: структура `tasks/task#<id>/` (task.json + TASK.md + артефакты этапов), статус-CLI, API и веб-мастер «Создать задачу», контент оркестрации этапов.

**Architecture:** `task_schema.py` (модель/CRUD на диске), самодостаточный CLI `content/tools/task_status.py` (деплоится в проект), `task_api.py` (роутер create/list + постановка в очередь agentmon), веб-страница, контент оркестрации (orchestrator-агент, скил, правило). Выполнение этапов ведёт claude-оркестратор через контент и очередь agentmon.

**Tech Stack:** Python 3.10+ (stdlib: json, pathlib, argparse, dataclasses), FastAPI, pytest. Без новых зависимостей.

## Global Constraints

- Кросс-платформа Linux+Windows; пути только `pathlib`.
- Своя реализация; тексты на русском; без новых зависимостей.
- Источник истины — файл (`task.json` в каталоге задачи).
- `id` — 6 цифр, max существующих `task#NNNNNN` + 1, база `100001`.
- 7 этапов (в порядке): `analyze`(analyst→ANALYZE.md), `plan`(architect→ARCHITECT.md),
  `tests`(tester→TESTS.md), `develop`(developer→DEVELOP.md), `testing`(tester→TESTING.md),
  `review`(reviewer→REVIEW.md), `docs`(developer→DOCS.md).
- `status ∈ {pending, running, done, failed, skipped}`; отключённый этап → `skipped`.
- `content/tools/task_status.py` — самодостаточный (без импорта agentmon).
- 6 агентов после №3 (добавляется `orchestrator`).

## File Structure

- Create: `app/src/agentmon/env/task_schema.py`
- Create: `app/src/agentmon/env/content/tools/task_status.py`
- Create: `app/src/agentmon/env/task_api.py`
- Create: `app/web/create-task.html`, `app/web/create-task.js`
- Create: `app/src/agentmon/env/content/agents/orchestrator.md`
- Create: `app/src/agentmon/env/content/skills/task-orchestration/SKILL.md`
- Create: `app/src/agentmon/env/content/rules/task-lifecycle.md`
- Modify: `app/src/agentmon/api.py` (подключить task-роутер; маршрут `/create-task`)
- Modify: `app/src/agentmon/env/content.py` (копировать `tools/`; добавить orchestrator в список CLAUDE.md)
- Modify: `app/web/index.html` (ссылка)
- Modify: `app/tests/env/test_content_files.py` (6 агентов, новый скил/правило)
- Test: `app/tests/env/test_task_schema.py`, `test_task_status_cli.py`, `test_task_api.py`, `test_create_task_page.py`, `test_task_content_integration.py`

---

## Task 1: Модель и структура задачи (task_schema.py)

**Files:**
- Create: `app/src/agentmon/env/task_schema.py`
- Test: `app/tests/env/test_task_schema.py`

**Interfaces:**
- Produces: `Stage`, `TaskSpec` (dataclasses, `to_dict`/`from_dict`), `DEFAULT_STAGES`,
  `STAGE_NAMES`, `build_stages(enabled_names)`, `next_task_id(project_dir)`,
  `task_dir(project_dir, task_id)`, `create_task(project_dir, *, title, goal, plan,
  constraints, enabled_stages, now=None)`, `save_task`, `load_task`, `list_tasks`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_task_schema.py
from agentmon.env import task_schema as ts


def test_next_id_empty_is_base(tmp_path):
    assert ts.next_task_id(tmp_path) == "100001"


def test_create_task_writes_files(tmp_path):
    spec = ts.create_task(tmp_path, title="T", goal="цель", plan="план",
                          constraints="огр", enabled_stages=ts.STAGE_NAMES)
    d = ts.task_dir(tmp_path, spec.id)
    assert (d / "task.json").exists()
    assert "цель" in (d / "TASK.md").read_text(encoding="utf-8")
    assert len(spec.stages) == 7
    assert all(s.status == "pending" for s in spec.stages)


def test_next_id_increments(tmp_path):
    first = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                           enabled_stages=ts.STAGE_NAMES)
    assert first.id == "100001"
    assert ts.next_task_id(tmp_path) == "100002"


def test_disabled_stage_is_skipped(tmp_path):
    spec = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                          enabled_stages=["analyze", "plan"])
    by = {s.name: s for s in spec.stages}
    assert by["analyze"].status == "pending"
    assert by["docs"].status == "skipped" and by["docs"].enabled is False


def test_roundtrip_and_list(tmp_path):
    ts.create_task(tmp_path, title="a", goal="g", plan="p", constraints="c",
                   enabled_stages=ts.STAGE_NAMES)
    tasks = ts.list_tasks(tmp_path)
    assert len(tasks) == 1
    d = ts.task_dir(tmp_path, tasks[0].id)
    assert ts.load_task(d).title == "a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_schema.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.task_schema).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/task_schema.py
import json
from dataclasses import dataclass, asdict
from pathlib import Path

ID_BASE = 100001

DEFAULT_STAGES = [
    {"name": "analyze", "subagent": "analyst",   "artifact": "ANALYZE.md"},
    {"name": "plan",    "subagent": "architect",  "artifact": "ARCHITECT.md"},
    {"name": "tests",   "subagent": "tester",     "artifact": "TESTS.md"},
    {"name": "develop", "subagent": "developer",  "artifact": "DEVELOP.md"},
    {"name": "testing", "subagent": "tester",     "artifact": "TESTING.md"},
    {"name": "review",  "subagent": "reviewer",   "artifact": "REVIEW.md"},
    {"name": "docs",    "subagent": "developer",  "artifact": "DOCS.md"},
]
STAGE_NAMES = [s["name"] for s in DEFAULT_STAGES]


@dataclass
class Stage:
    name: str
    enabled: bool
    subagent: str
    artifact: str
    status: str
    changed_files: list


@dataclass
class TaskSpec:
    id: str
    title: str
    goal: str
    plan: str
    constraints: str
    created_at: float | None
    stages: list

    def to_dict(self) -> dict:
        base = {k: getattr(self, k) for k in
                ("id", "title", "goal", "plan", "constraints", "created_at")}
        base["stages"] = [asdict(s) for s in self.stages]
        return base

    @classmethod
    def from_dict(cls, data: dict) -> "TaskSpec":
        data = dict(data)
        data["stages"] = [Stage(**s) for s in data.get("stages", [])]
        return cls(**data)


def build_stages(enabled_names) -> list:
    enabled = set(enabled_names)
    stages = []
    for d in DEFAULT_STAGES:
        on = d["name"] in enabled
        stages.append(Stage(name=d["name"], enabled=on, subagent=d["subagent"],
                            artifact=d["artifact"],
                            status="pending" if on else "skipped",
                            changed_files=[]))
    return stages


def _tasks_dir(project_dir) -> Path:
    return Path(project_dir) / "tasks"


def next_task_id(project_dir) -> str:
    tasks, ids = _tasks_dir(project_dir), []
    if tasks.exists():
        for p in tasks.iterdir():
            if p.is_dir() and p.name.startswith("task#"):
                tail = p.name[len("task#"):]
                if tail.isdigit():
                    ids.append(int(tail))
    return f"{(max(ids) + 1) if ids else ID_BASE:06d}"


def task_dir(project_dir, task_id) -> Path:
    return _tasks_dir(project_dir) / f"task#{task_id}"


def _task_md(spec) -> str:
    return (f"# {spec.title}\n\n## Цель\n{spec.goal}\n\n## План\n{spec.plan}\n\n"
            f"## Ограничения\n{spec.constraints}\n")


def save_task(task_dir_path, spec) -> None:
    (Path(task_dir_path) / "task.json").write_text(
        json.dumps(spec.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def load_task(task_dir_path) -> TaskSpec:
    data = json.loads((Path(task_dir_path) / "task.json").read_text(encoding="utf-8"))
    return TaskSpec.from_dict(data)


def create_task(project_dir, *, title, goal, plan, constraints,
                enabled_stages, now=None) -> TaskSpec:
    task_id = next_task_id(project_dir)
    spec = TaskSpec(id=task_id, title=title, goal=goal, plan=plan,
                    constraints=constraints, created_at=now,
                    stages=build_stages(enabled_stages))
    d = task_dir(project_dir, task_id)
    d.mkdir(parents=True, exist_ok=True)
    save_task(d, spec)
    (d / "TASK.md").write_text(_task_md(spec), encoding="utf-8")
    return spec


def list_tasks(project_dir) -> list:
    tasks, out = _tasks_dir(project_dir), []
    if tasks.exists():
        for p in sorted(tasks.iterdir()):
            if p.is_dir() and (p / "task.json").exists():
                out.append(load_task(p))
    return out


def update_stage(task_dir_path, stage_name, *, status, changed_files=None) -> None:
    spec = load_task(task_dir_path)
    for s in spec.stages:
        if s.name == stage_name:
            s.status = status
            for f in (changed_files or []):
                if f not in s.changed_files:
                    s.changed_files.append(f)
            save_task(task_dir_path, spec)
            return
    raise ValueError(f"неизвестный этап: {stage_name}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_schema.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/task_schema.py app/tests/env/test_task_schema.py
git commit -m "feat(tasks): модель и структура задачи"
```

---

## Task 2: Статус-CLI task_status.py

**Files:**
- Create: `app/src/agentmon/env/content/tools/task_status.py`
- Test: `app/tests/env/test_task_status_cli.py`

**Interfaces:**
- Produces: самодостаточный скрипт с `update(task_dir, stage, status, files)` и
  `main(argv=None)` (argparse: `task_dir stage status --files ...`). Без импортов agentmon.
- Consumes (в тесте): `task_schema.create_task` для подготовки `task.json`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_task_status_cli.py
import importlib.util
import json
from pathlib import Path
import pytest
from agentmon.env import task_schema as ts

CLI = (Path(__file__).resolve().parents[2] / "src" / "agentmon" / "env"
       / "content" / "tools" / "task_status.py")


def _load():
    spec = importlib.util.spec_from_file_location("task_status", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=ts.STAGE_NAMES)
    return ts.task_dir(tmp_path, s.id)


def test_cli_sets_status_and_files(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "done", "--files", "Module.bsl", "Form.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "done"
    assert dev["changed_files"] == ["Module.bsl", "Form.bsl"]


def test_cli_unknown_stage_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    with pytest.raises(SystemExit):
        mod.main([str(d), "nope", "done"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_status_cli.py -q`
Expected: FAIL (файла нет).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/content/tools/task_status.py
#!/usr/bin/env python3
"""Обновить статус этапа задачи в task.json. Самодостаточный скрипт (без agentmon)."""
import argparse
import json
from pathlib import Path

VALID = ("pending", "running", "done", "failed", "skipped")


def update(task_dir: str, stage: str, status: str, files) -> None:
    path = Path(task_dir) / "task.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for s in data.get("stages", []):
        if s["name"] == stage:
            s["status"] = status
            changed = s.setdefault("changed_files", [])
            for f in (files or []):
                if f not in changed:
                    changed.append(f)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            return
    raise SystemExit(f"неизвестный этап: {stage}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Обновить статус этапа задачи")
    ap.add_argument("task_dir")
    ap.add_argument("stage")
    ap.add_argument("status", choices=VALID)
    ap.add_argument("--files", nargs="*", default=[])
    args = ap.parse_args(argv)
    update(args.task_dir, args.stage, args.status, args.files)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_status_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/content/tools/task_status.py app/tests/env/test_task_status_cli.py
git commit -m "feat(tasks): статус-CLI task_status.py"
```

---

## Task 3: API-роутер задач (task_api.py)

**Files:**
- Create: `app/src/agentmon/env/task_api.py`
- Modify: `app/src/agentmon/api.py` (подключить роутер)
- Test: `app/tests/env/test_task_api.py`

**Interfaces:**
- Consumes: `task_schema` (create_task/list_tasks/STAGE_NAMES); `registry.get`, `queue.enqueue`.
- Produces: `build_task_router(registry, queue) -> APIRouter` с `POST /api/tasks/create`
  (тело `{project_id, title, goal, plan, constraints, enabled_stages, enqueue}`) и
  `GET /api/tasks?project_id=`.
- Modify `create_app`: `app.include_router(build_task_router(registry, queue))`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_task_api.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def make(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    mon = Monitor(reg, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    client = TestClient(create_app(registry=reg, queue=q, monitor=mon))
    return client, reg, q


def test_create_task_makes_structure(tmp_path):
    client, reg, q = make(tmp_path)
    proj = tmp_path / "proj"; proj.mkdir()
    pid = reg.add(name="p", path=str(proj), backend="local").id
    r = client.post("/api/tasks/create", json={
        "project_id": pid, "title": "T", "goal": "g", "plan": "p",
        "constraints": "c", "enabled_stages": ["analyze", "plan"], "enqueue": True})
    assert r.status_code == 200
    tid = r.json()["task"]["id"]
    assert (proj / "tasks" / f"task#{tid}" / "task.json").exists()
    assert len(q.list(pid)) == 1          # поставлена в очередь

    lst = client.get("/api/tasks", params={"project_id": pid}).json()["tasks"]
    assert len(lst) == 1


def test_create_task_unknown_project_404(tmp_path):
    client, _, _ = make(tmp_path)
    r = client.post("/api/tasks/create", json={"project_id": 999, "title": "x"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_task_api.py -q`
Expected: FAIL (ImportError build_task_router / 404-route отсутствует).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/task_api.py
from fastapi import APIRouter, HTTPException

from . import task_schema


def build_task_router(registry, queue) -> APIRouter:
    router = APIRouter()

    def project_or_404(project_id):
        project = registry.get(project_id)
        if project is None:
            raise HTTPException(status_code=404,
                                detail=f"нет проекта с id={project_id}")
        return project

    @router.post("/api/tasks/create")
    def create_task_route(body: dict):
        try:
            project = project_or_404(int(body.get("project_id", 0)))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="плохой project_id")
        try:
            spec = task_schema.create_task(
                project.path,
                title=body.get("title", ""),
                goal=body.get("goal", ""),
                plan=body.get("plan", ""),
                constraints=body.get("constraints", ""),
                enabled_stages=body.get("enabled_stages", task_schema.STAGE_NAMES),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if body.get("enqueue"):
            queue.enqueue(project.id,
                          f"Выполни задачу tasks/task#{spec.id} по этапам из её "
                          f"task.json. Следуй навыку task-orchestration.")
        return {"task": spec.to_dict()}

    @router.get("/api/tasks")
    def list_tasks_route(project_id: int):
        project = project_or_404(project_id)
        return {"tasks": [t.to_dict() for t in task_schema.list_tasks(project.path)]}

    return router
```

- [ ] **Step 4: Подключить роутер в create_app**

В `app/src/agentmon/api.py`, сразу после строки, где подключается роутер окружения
(`app.include_router(build_env_router(registry))`), добавить:

```python
    from .env.task_api import build_task_router
    app.include_router(build_task_router(registry, queue))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_task_api.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Прогнать весь набор**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все).

- [ ] **Step 7: Commit**

```bash
git add app/src/agentmon/env/task_api.py app/src/agentmon/api.py app/tests/env/test_task_api.py
git commit -m "feat(tasks): API создания и списка задач"
```

---

## Task 4: Web-страница «Создать задачу»

**Files:**
- Create: `app/web/create-task.html`, `app/web/create-task.js`
- Modify: `app/src/agentmon/api.py` (маршрут `/create-task`)
- Modify: `app/web/index.html` (ссылка)
- Test: `app/tests/env/test_create_task_page.py`

**Interfaces:**
- Consumes: `POST /api/tasks/create`.
- Produces: страница с формой (project_id, заголовок, цель, план, ограничения, чекбоксы
  7 этапов, галка enqueue), шлёт config на API, показывает результат.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_create_task_page.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def test_create_task_page_served(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    client = TestClient(create_app(registry=ProjectRegistry(db),
                                   queue=TaskQueue(db), monitor=mon))
    r = client.get("/create-task")
    assert r.status_code == 200
    assert "Создать задачу" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_create_task_page.py -q`
Expected: FAIL (404 на /create-task).

- [ ] **Step 3: Создать страницу**

```html
<!-- app/web/create-task.html -->
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Создать задачу</title></head>
<body>
  <h1>Создать задачу</h1>
  <form id="f">
    <input name="project_id" type="number" placeholder="id проекта" required>
    <input name="title" placeholder="заголовок" required>
    <textarea name="goal" placeholder="цель"></textarea>
    <textarea name="plan" placeholder="план"></textarea>
    <textarea name="constraints" placeholder="ограничения"></textarea>
    <fieldset><legend>Этапы</legend><div id="stages"></div></fieldset>
    <label><input type="checkbox" name="enqueue"> поставить в очередь</label>
    <button type="submit">Создать</button>
  </form>
  <pre id="out"></pre>
  <script src="/static/create-task.js"></script>
</body>
</html>
```

```javascript
// app/web/create-task.js
const STAGES = ["analyze","plan","tests","develop","testing","review","docs"];
const box = document.getElementById("stages");
STAGES.forEach(s => {
  box.insertAdjacentHTML("beforeend",
    `<label><input type="checkbox" class="st" value="${s}" checked> ${s}</label> `);
});

document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const enabled_stages = [...box.querySelectorAll(".st:checked")].map(c => c.value);
  const body = {
    project_id: Number(f.project_id.value), title: f.title.value,
    goal: f.goal.value, plan: f.plan.value, constraints: f.constraints.value,
    enabled_stages, enqueue: f.enqueue.checked,
  };
  const r = await fetch("/api/tasks/create",
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await r.json();
  document.getElementById("out").textContent = JSON.stringify(data, null, 2);
});
```

- [ ] **Step 4: Маршрут страницы**

В `app/src/agentmon/api.py`, в блоке `if web_dir.exists():` рядом с `/create-project`
добавить:

```python
        @app.get("/create-task")
        def create_task_page():
            return FileResponse(web_dir / "create-task.html",
                                headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 5: Ссылка в index.html**

В `app/web/index.html` добавить рядом со ссылкой «Создать проект»:

```html
<a href="/create-task">Создать задачу</a>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_create_task_page.py -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Commit**

```bash
git add app/web/create-task.html app/web/create-task.js app/src/agentmon/api.py app/web/index.html app/tests/env/test_create_task_page.py
git commit -m "feat(tasks): web-страница «Создать задачу»"
```

---

## Task 5: Контент оркестрации (orchestrator, скил, правило)

**Files:**
- Create: `app/src/agentmon/env/content/agents/orchestrator.md`
- Create: `app/src/agentmon/env/content/skills/task-orchestration/SKILL.md`
- Create: `app/src/agentmon/env/content/rules/task-lifecycle.md`
- Modify: `app/tests/env/test_content_files.py` (6 агентов; добавить скил/правило в множества)

**Interfaces:**
- Produces: orchestrator-агент (frontmatter как у прочих, `tools` включает Bash для
  вызова `task_status.py`), скил `task-orchestration`, правило `task-lifecycle`.

- [ ] **Step 1: Обновить тест контента**

В `app/tests/env/test_content_files.py`:
- В множестве агентов добавить `orchestrator`: заменить
  `AGENTS = {"analyst", "architect", "developer", "tester", "reviewer"}`
  на `AGENTS = {"analyst", "architect", "developer", "tester", "reviewer", "orchestrator"}`.
- В `SKILLS` добавить `"task-orchestration"`.
- В `RULES` добавить `"task-lifecycle"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: FAIL (нет orchestrator / task-orchestration / task-lifecycle).

- [ ] **Step 3: Создать orchestrator-агента**

`app/src/agentmon/env/content/agents/orchestrator.md`:
```markdown
---
name: orchestrator
description: Оркестратор задач 1С. Ведёт задачу по этапам из task.json, делегирует субагентам, обновляет статусы. Вызывай для выполнения задачи из каталога tasks/task#<id>.
tools: Read, Grep, Glob, Bash
model: {{MODEL}}
effort: {{EFFORT}}
---

# Оркестратор

Ты — оркестратор задачи 1С. Выполняешь задачу из каталога `tasks/task#<id>`.

## Когда вызываюсь
Для прогона задачи по этапам (создана мастером «Создать задачу»).

## Что делаю
1. Читаю `tasks/task#<id>/task.json` и `TASK.md` (цель, план, ограничения).
2. Для каждого включённого этапа (`enabled: true`) по порядку:
   - ставлю статус `running` через `.claude/tools/task_status.py`;
   - делегирую соответствующему субагенту (`subagent` этапа);
   - проверяю, что артефакт этапа (`artifact`) записан в каталог задачи;
   - ставлю `done` (или `failed`) и передаю список изменённых файлов `--files`.
3. Отключённые этапы (`skipped`) пропускаю.
4. По завершении формирую итог.

## Обновление статуса
`python3 .claude/tools/task_status.py tasks/task#<id> <этап> <статус> --files f1 f2`
(следуй навыку `task-orchestration`).

## Границы
Сам прикладной код не пишу — делегирую. Отвечаю за ход этапов и статусы.
```

- [ ] **Step 4: Создать скил task-orchestration**

`app/src/agentmon/env/content/skills/task-orchestration/SKILL.md`:
```markdown
---
name: task-orchestration
description: Как выполнять задачу 1С по этапам из task.json — порядок, статусы, артефакты. Читай перед прогоном задачи из tasks/task#<id>.
allowed-tools: []
---

# Оркестрация задачи

## Источник
`tasks/task#<id>/task.json` — список этапов с полями `name`, `enabled`, `subagent`,
`artifact`, `status`, `changed_files`.

## Порядок этапов
analyze → plan → tests → develop → testing → review → docs.
Выполняй только этапы с `enabled: true`, в указанном порядке.

## Для каждого этапа
1. `task_status.py ... <этап> running`.
2. Делегируй субагенту этапа (`subagent`): передай цель, план, ограничения и
   артефакты предыдущих этапов.
3. Убедись, что субагент записал `<artifact>` (например `ANALYZE.md`) в каталог задачи.
4. `task_status.py ... <этап> done --files <изменённые>` (или `failed` при ошибке).

## Статусы
`pending → running → done | failed`. Отключённый этап — `skipped`, его пропускаем.

## Гейты (опционально)
После `analyze` и `plan` уместна пауза на подтверждение пользователя, если задача
крупная или требования неоднозначны.
```

- [ ] **Step 5: Создать правило task-lifecycle**

`app/src/agentmon/env/content/rules/task-lifecycle.md`:
```markdown
---
name: task-lifecycle
description: Работа с задачей идёт по task.json с обновлением статусов и артефактов.
---

# Жизненный цикл задачи

При работе над задачей из `tasks/task#<id>`:
1. Читай `task.json` и уважай `enabled` каждого этапа.
2. Каждый субагент пишет свой артефакт этапа (`ANALYZE.md`, `ARCHITECT.md`, `TESTS.md`,
   `DEVELOP.md`, `TESTING.md`, `REVIEW.md`, `DOCS.md`) в каталог задачи.
3. Статус этапа и список изменённых файлов обновляются через
   `.claude/tools/task_status.py` (см. навык `task-orchestration`).
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_content_files.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/src/agentmon/env/content/agents/orchestrator.md app/src/agentmon/env/content/skills/task-orchestration app/src/agentmon/env/content/rules/task-lifecycle.md app/tests/env/test_content_files.py
git commit -m "feat(tasks): контент оркестрации (orchestrator, скил, правило)"
```

---

## Task 6: Деплой tools/ через content.py + интеграция

**Files:**
- Modify: `app/src/agentmon/env/content.py` (копировать `tools/`; добавить orchestrator в список CLAUDE.md)
- Test: `app/tests/env/test_task_content_integration.py`

**Interfaces:**
- Consumes: `deploy_content` (content), `task_schema.create_task`.
- Produces: `deploy_content` раскладывает `.claude/tools/task_status.py`; `CLAUDE.md`
  перечисляет orchestrator среди субагентов.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_task_content_integration.py
from agentmon.env.config_schema import EnvConfig, SCHEMA_VERSION
from agentmon.env import content, task_schema as ts


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo", project_dir=str(tmp_path),
        developer_id="i", developer_email="i@e.ru", platform_dir="/opt/1cv8",
        platform_version="8.3.27.1786", db_kind="file", db_connection="/b",
        web_publication="", mcp=[], agents=[])


def test_deploy_places_task_status_tool(tmp_path):
    content.deploy_content(cfg(tmp_path), update=False)
    assert (tmp_path / ".claude" / "tools" / "task_status.py").exists()
    assert (tmp_path / ".claude" / "agents" / "orchestrator.md").exists()


def test_claude_md_lists_orchestrator(tmp_path):
    content.deploy_content(cfg(tmp_path), update=False)
    assert "orchestrator" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_task_and_tool_coexist(tmp_path):
    content.deploy_content(cfg(tmp_path), update=False)
    spec = ts.create_task(tmp_path, title="T", goal="g", plan="p", constraints="c",
                          enabled_stages=ts.STAGE_NAMES)
    assert (ts.task_dir(tmp_path, spec.id) / "task.json").exists()
    assert (tmp_path / ".claude" / "tools" / "task_status.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_content_integration.py -q`
Expected: FAIL (tools не копируется / orchestrator не в CLAUDE.md).

- [ ] **Step 3: Изменить content.py**

В `app/src/agentmon/env/content.py`:
1. Добавить `"tools"` в список копируемых подкаталогов:
```python
    for sub in ("skills", "rules", "hooks", "tools"):
        _copy_tree(CONTENT_DIR / sub, claude / sub)
```
2. Добавить `orchestrator` в кортеж `_AGENTS` (для раздела «Субагенты» в CLAUDE.md):
```python
_AGENTS = ("orchestrator", "analyst", "architect", "developer", "tester", "reviewer")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_content_integration.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Прогнать весь набор**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/content.py app/tests/env/test_task_content_integration.py
git commit -m "feat(tasks): деплой статус-CLI и оркестратора через content.py"
```

---

## Self-Review

**Spec coverage:**
- Структура `tasks/task#<id>/` (task.json + TASK.md) → Task 1. 7 этапов, skipped → Task 1.
- id (max+1, база 100001) → Task 1 (`next_task_id`). update_stage → Task 1.
- Статус-CLI (самодостаточный) → Task 2. Деплой в `.claude/tools/` → Task 6.
- API create/list + enqueue → Task 3. Веб-мастер «Создать задачу» → Task 4.
- Контент оркестрации (orchestrator, task-orchestration, task-lifecycle) → Task 5.
- content.py копирует tools/, CLAUDE.md перечисляет orchestrator → Task 6.
- Тесты (schema, cli, api, page, content, integration) → Task 1-6.

**Placeholder scan:** код/контент полный; `{{MODEL}}`/`{{EFFORT}}` — намеренные
плейсхолдеры (как в №2).

**Type consistency:** `TaskSpec`/`Stage` и их поля едины; `create_task(..., enabled_stages,
now=None)`, `update_stage(task_dir, stage, *, status, changed_files)`,
`build_task_router(registry, queue)`, `deploy_content(config, *, update)` согласованы;
имена этапов и артефактов совпадают между task_schema, CLI, orchestrator, task-lifecycle.

**Отложено (вне №3):** автономный прогон списка задач (№4); бенчмарки (№5); реальная
отрисовка статусов задач в UI agentmon (есть API `GET /api/tasks`, богатый UI —
позже); `created_at` в API остаётся null (детерминизм; проставление времени — минор).

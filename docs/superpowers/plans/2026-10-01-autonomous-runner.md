# Автономный раннер списка задач — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать выбрать список задач проекта и выполнить их автономно: отбор задач + сводный статус + постановка в очередь agentmon + веб-страница «Выполнить задачи».

**Architecture:** `task_run.py` (сводный статус задачи + отбор), `orchestration_prompt` в task_schema (DRY), дополнения в `task_api.py` (`POST /api/tasks/run`, `GET /api/tasks/status`), веб-страница. Движок прогона — существующий диспетчер agentmon.

**Tech Stack:** Python 3.10+ (stdlib), FastAPI, pytest. Без новых зависимостей.

## Global Constraints

- Кросс-платформа; пути только pathlib; без новых зависимостей; тексты на русском.
- `task_overall_status`: есть `failed`→`failed`; все включённые `done`→`done`; есть `running`→`running`; иначе `pending`; нет включённых этапов→`done`.
- `POST /api/tasks/run` только ставит в очередь; прогон ведёт диспетчер agentmon.
- Статус читается из `task.json` (источник истины), не из очереди.
- `orchestration_prompt(task_id)` — единый текст, переиспользуется create (№3) и run (№4).

## File Structure

- Create: `app/src/agentmon/env/task_run.py`
- Modify: `app/src/agentmon/env/task_schema.py` (добавить `orchestration_prompt`)
- Modify: `app/src/agentmon/env/task_api.py` (роуты run/status; рефактор create)
- Create: `app/web/run-tasks.html`, `app/web/run-tasks.js`
- Modify: `app/src/agentmon/api.py` (маршрут `/run-tasks`)
- Modify: `app/web/index.html` (ссылка)
- Test: `app/tests/env/test_task_run.py`, `test_run_api.py`, `test_run_tasks_page.py`

---

## Task 1: Сводный статус и отбор задач (task_run.py)

**Files:**
- Create: `app/src/agentmon/env/task_run.py`
- Modify: `app/src/agentmon/env/task_schema.py` (добавить `orchestration_prompt`)
- Test: `app/tests/env/test_task_run.py`

**Interfaces:**
- Consumes: `task_schema` (list_tasks, create_task, update_stage, Stage/TaskSpec).
- Produces: `OVERALL_PENDING/RUNNING/DONE/FAILED`, `task_overall_status(spec) -> str`,
  `select_tasks(project_dir, task_ids=None, only_runnable=True) -> list`;
  `task_schema.orchestration_prompt(task_id) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_task_run.py
from agentmon.env import task_schema as ts
from agentmon.env import task_run as tr


def test_orchestration_prompt_mentions_task_and_skill():
    p = ts.orchestration_prompt("100007")
    assert "tasks/task#100007" in p and "task-orchestration" in p


def _task(tmp_path, stages):
    return ts.create_task(tmp_path, title="t", goal="", plan="", constraints="",
                          enabled_stages=stages)


def test_overall_pending_fresh(tmp_path):
    spec = _task(tmp_path, ts.STAGE_NAMES)
    assert tr.task_overall_status(spec) == tr.OVERALL_PENDING


def test_overall_done_when_all_enabled_done(tmp_path):
    spec = _task(tmp_path, ["analyze"])
    d = ts.task_dir(tmp_path, spec.id)
    ts.update_stage(d, "analyze", status="done")
    assert tr.task_overall_status(ts.load_task(d)) == tr.OVERALL_DONE


def test_overall_failed_beats_running(tmp_path):
    spec = _task(tmp_path, ["analyze", "plan"])
    d = ts.task_dir(tmp_path, spec.id)
    ts.update_stage(d, "analyze", status="running")
    ts.update_stage(d, "plan", status="failed")
    assert tr.task_overall_status(ts.load_task(d)) == tr.OVERALL_FAILED


def test_overall_done_when_no_enabled(tmp_path):
    spec = _task(tmp_path, [])
    assert tr.task_overall_status(spec) == tr.OVERALL_DONE


def test_select_only_runnable_excludes_done(tmp_path):
    done = _task(tmp_path, ["analyze"])
    ts.update_stage(ts.task_dir(tmp_path, done.id), "analyze", status="done")
    runnable = _task(tmp_path, ts.STAGE_NAMES)
    ids = [t.id for t in tr.select_tasks(tmp_path, only_runnable=True)]
    assert runnable.id in ids and done.id not in ids


def test_select_by_ids(tmp_path):
    a = _task(tmp_path, ts.STAGE_NAMES)
    _task(tmp_path, ts.STAGE_NAMES)
    ids = [t.id for t in tr.select_tasks(tmp_path, task_ids=[a.id], only_runnable=False)]
    assert ids == [a.id]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_run.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.task_run / нет orchestration_prompt).

- [ ] **Step 3: Добавить orchestration_prompt в task_schema.py**

В конец `app/src/agentmon/env/task_schema.py` добавить:

```python
def orchestration_prompt(task_id) -> str:
    return (f"Выполни задачу tasks/task#{task_id} по этапам из её task.json. "
            f"Следуй навыку task-orchestration.")
```

- [ ] **Step 4: Создать task_run.py**

```python
# app/src/agentmon/env/task_run.py
from . import task_schema

OVERALL_PENDING = "pending"
OVERALL_RUNNING = "running"
OVERALL_DONE = "done"
OVERALL_FAILED = "failed"


def task_overall_status(spec) -> str:
    enabled = [s for s in spec.stages if s.enabled]
    if not enabled:
        return OVERALL_DONE
    statuses = [s.status for s in enabled]
    if "failed" in statuses:
        return OVERALL_FAILED
    if all(s == "done" for s in statuses):
        return OVERALL_DONE
    if "running" in statuses:
        return OVERALL_RUNNING
    return OVERALL_PENDING


def select_tasks(project_dir, task_ids=None, only_runnable=True) -> list:
    tasks = task_schema.list_tasks(project_dir)
    if task_ids is not None:
        wanted = set(task_ids)
        tasks = [t for t in tasks if t.id in wanted]
    if only_runnable:
        tasks = [t for t in tasks if task_overall_status(t) != OVERALL_DONE]
    return tasks
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src python -m pytest tests/env/test_task_run.py -q`
Expected: PASS (7 passed).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/task_run.py app/src/agentmon/env/task_schema.py app/tests/env/test_task_run.py
git commit -m "feat(run): сводный статус и отбор задач"
```

---

## Task 2: API прогона и статуса

**Files:**
- Modify: `app/src/agentmon/env/task_api.py`
- Test: `app/tests/env/test_run_api.py`

**Interfaces:**
- Consumes: `task_schema` (list_tasks, orchestration_prompt), `task_run` (select_tasks,
  task_overall_status); `registry.get`, `queue.enqueue`.
- Produces: `POST /api/tasks/run` ({project_id, task_ids?, only_runnable?}) →
  `{enqueued:[ids], count}`; `GET /api/tasks/status?project_id=` →
  `{tasks:[{id,title,overall,done,total}]}`. Рефактор: create использует
  `task_schema.orchestration_prompt`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_run_api.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.env import task_schema as ts
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def make(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    mon = Monitor(reg, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    return TestClient(create_app(registry=reg, queue=q, monitor=mon)), reg, q


def test_run_enqueues_runnable(tmp_path):
    client, reg, q = make(tmp_path)
    proj = tmp_path / "proj"; proj.mkdir()
    pid = reg.add(name="p", path=str(proj), backend="local").id
    # одна выполненная (no enabled → done) и одна готовая к прогону
    ts.create_task(proj, title="done", goal="", plan="", constraints="", enabled_stages=[])
    ts.create_task(proj, title="run", goal="", plan="", constraints="",
                   enabled_stages=ts.STAGE_NAMES)
    r = client.post("/api/tasks/run", json={"project_id": pid, "only_runnable": True})
    assert r.status_code == 200
    assert r.json()["count"] == 1               # только невыполненная
    assert len(q.list(pid)) == 1


def test_status_reports_overall(tmp_path):
    client, reg, q = make(tmp_path)
    proj = tmp_path / "proj"; proj.mkdir()
    pid = reg.add(name="p", path=str(proj), backend="local").id
    ts.create_task(proj, title="t", goal="", plan="", constraints="",
                   enabled_stages=["analyze", "plan"])
    data = client.get("/api/tasks/status", params={"project_id": pid}).json()["tasks"]
    assert data[0]["overall"] == "pending"
    assert data[0]["total"] == 2 and data[0]["done"] == 0


def test_run_unknown_project_404(tmp_path):
    client, _, _ = make(tmp_path)
    assert client.post("/api/tasks/run", json={"project_id": 999}).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_run_api.py -q`
Expected: FAIL (роутов run/status нет).

- [ ] **Step 3: Изменить task_api.py**

1. Обновить импорт модулей вверху файла:
```python
from . import task_schema, task_run
```

2. В `create_task_route` заменить тело enqueue на единый промпт:
```python
        if body.get("enqueue"):
            queue.enqueue(project.id, task_schema.orchestration_prompt(spec.id))
```

3. Внутри `build_task_router`, перед `return router`, добавить два роута:
```python
    @router.post("/api/tasks/run")
    def run_tasks_route(body: dict):
        try:
            project = project_or_404(int(body.get("project_id", 0)))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="плохой project_id")
        selected = task_run.select_tasks(
            project.path, task_ids=body.get("task_ids"),
            only_runnable=body.get("only_runnable", True))
        for t in selected:
            queue.enqueue(project.id, task_schema.orchestration_prompt(t.id))
        return {"enqueued": [t.id for t in selected], "count": len(selected)}

    @router.get("/api/tasks/status")
    def tasks_status_route(project_id: int):
        project = project_or_404(project_id)
        out = []
        for t in task_schema.list_tasks(project.path):
            enabled = [s for s in t.stages if s.enabled]
            out.append({"id": t.id, "title": t.title,
                        "overall": task_run.task_overall_status(t),
                        "done": sum(1 for s in enabled if s.status == "done"),
                        "total": len(enabled)})
        return {"tasks": out}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_run_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Прогнать весь набор**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все; существующий test_task_api с create по-прежнему зелёный).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/task_api.py app/tests/env/test_run_api.py
git commit -m "feat(run): API прогона и сводного статуса задач"
```

---

## Task 3: Web-страница «Выполнить задачи»

**Files:**
- Create: `app/web/run-tasks.html`, `app/web/run-tasks.js`
- Modify: `app/src/agentmon/api.py` (маршрут `/run-tasks`)
- Modify: `app/web/index.html` (ссылка)
- Test: `app/tests/env/test_run_tasks_page.py`

**Interfaces:**
- Consumes: `GET /api/tasks/status`, `POST /api/tasks/run`.
- Produces: страница со списком задач (чекбоксы + overall + прогресс), кнопками
  «Запустить выбранные» / «Запустить все невыполненные» / «Обновить».

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_run_tasks_page.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


def test_run_tasks_page_served(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    client = TestClient(create_app(registry=ProjectRegistry(db),
                                   queue=TaskQueue(db), monitor=mon))
    r = client.get("/run-tasks")
    assert r.status_code == 200
    assert "Выполнить задачи" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_run_tasks_page.py -q`
Expected: FAIL (404 на /run-tasks).

- [ ] **Step 3: Создать страницу**

```html
<!-- app/web/run-tasks.html -->
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Выполнить задачи</title></head>
<body>
  <h1>Выполнить задачи</h1>
  <input id="pid" type="number" placeholder="id проекта">
  <button id="load">Загрузить</button>
  <form id="f">
    <div id="tasks"></div>
    <button type="submit">Запустить выбранные</button>
    <button type="button" id="all">Запустить все невыполненные</button>
    <button type="button" id="refresh">Обновить</button>
  </form>
  <pre id="out"></pre>
  <script src="/static/run-tasks.js"></script>
</body>
</html>
```

```javascript
// app/web/run-tasks.js
const box = document.getElementById("tasks");
const out = document.getElementById("out");
const pid = () => Number(document.getElementById("pid").value);

async function load() {
  const r = await fetch(`/api/tasks/status?project_id=${pid()}`);
  const data = await r.json();
  box.innerHTML = "";
  (data.tasks || []).forEach(t => {
    box.insertAdjacentHTML("beforeend",
      `<label><input type="checkbox" class="t" value="${t.id}"> ` +
      `#${t.id} ${t.title} — ${t.overall} (${t.done}/${t.total})</label><br>`);
  });
}

async function run(body) {
  const r = await fetch("/api/tasks/run",
    {method: "POST", headers: {"Content-Type": "application/json"},
     body: JSON.stringify(body)});
  out.textContent = JSON.stringify(await r.json(), null, 2);
  await load();
}

document.getElementById("load").addEventListener("click", load);
document.getElementById("refresh").addEventListener("click", load);
document.getElementById("all").addEventListener("click",
  () => run({project_id: pid(), only_runnable: true}));
document.getElementById("f").addEventListener("submit", (e) => {
  e.preventDefault();
  const ids = [...box.querySelectorAll(".t:checked")].map(c => c.value);
  run({project_id: pid(), task_ids: ids, only_runnable: false});
});
```

- [ ] **Step 4: Маршрут страницы**

В `app/src/agentmon/api.py`, в блоке `if web_dir.exists():` рядом с `/create-task`
добавить:

```python
        @app.get("/run-tasks")
        def run_tasks_page():
            return FileResponse(web_dir / "run-tasks.html",
                                headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 5: Ссылка в index.html**

В `app/web/index.html` рядом со ссылкой «Создать задачу» добавить:

```html
<a href="/run-tasks">Выполнить задачи</a>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest tests/env/test_run_tasks_page.py -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Прогнать весь набор**

Run: `cd ~/projects/ai_template/app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все).

- [ ] **Step 8: Commit**

```bash
git add app/web/run-tasks.html app/web/run-tasks.js app/src/agentmon/api.py app/web/index.html app/tests/env/test_run_tasks_page.py
git commit -m "feat(run): web-страница «Выполнить задачи»"
```

---

## Self-Review

**Spec coverage:**
- Сводный статус задачи → Task 1 (`task_overall_status`). Отбор списка → Task 1 (`select_tasks`).
- Единый промпт оркестрации (DRY) → Task 1 (`orchestration_prompt`), применён в create+run (Task 2).
- API прогона (ставит в очередь) + статус → Task 2. Веб-страница выбора/запуска → Task 3.
- Прогон ведёт существующий диспетчер; статус из task.json → по дизайну (Task 2 `GET status`).
- Тесты (task_run, run API, страница) → Task 1-3.

**Placeholder scan:** код полный, без TODO.

**Type consistency:** `task_overall_status(spec)`, `select_tasks(project_dir, task_ids, only_runnable)`,
`orchestration_prompt(task_id)`, `build_task_router(registry, queue)` согласованы; статусы
этапов и `OVERALL_*` не смешиваются; поля `{id,title,overall,done,total}` едины между API и JS.

**Отложено (вне №4):** бенчмарки (№5); богатый дашборд/история прогонов; автоопрос статуса
(сейчас кнопка «Обновить»); отражение статуса очереди agentmon рядом с task.json-статусом.

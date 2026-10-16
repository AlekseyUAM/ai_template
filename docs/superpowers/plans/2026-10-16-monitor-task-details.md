# Монитор: детальная карточка задачи — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** В окне «Монитор» показывать задачу свёрнутой одной строкой с разворотом в полную карточку (текущий этап, тайминги этапов, лимит, обновление БД, номер итерации, кнопка открытия отчёта этапа в VS Code).

**Architecture:** Оркестратор пишет прогресс в `task.json` (producer). Бэкенд Монитора по таймеру (5 мин) синхронизирует `task.json`→БД через расширенный `refresh_project`, затем `GET /api/env/stacks` отдаёт обогащённые элементы. Фронтенд рисует свёрнутую строку + разворот и кнопку «Отчёт» (открывает артефакт в VS Code через `popen(["code", ...])`).

**Tech Stack:** Python 3.14, FastAPI, sqlite/postgres (адаптер `store/db.py`), ванильный JS (`app/web/start.js`), pytest (`fastapi.testclient.TestClient`).

## Global Constraints

- Отметки времени — epoch-секунды (как `queue.py`, task-уровневые `started_at`).
- Миграции БД — только идемпотентно через `_ensure_columns` (ADD COLUMN), переносимо sqlite+postgres.
- `task_status.py` работает с `task.json` как с сырым словарём (без зависимостей, кроме `argparse/json/time/pathlib`) — он деплоится в проекты.
- Читатели этапов используют `.get(...)` с дефолтами: `started_at`/`finished_at` → `None`, `iteration` → `1`.
- Поле `db_update` в `task.json` — словарь `{"started_at": float, "finished_at": float|None}`; в БД хранится как TEXT-колонка `db_update_json` (JSON или NULL).
- Фронтенд-тесты — проверка отдаваемого текста (`TestClient.get`), как в `test_start_page.py` (без браузера).
- Запуск тестов: `python -m pytest <путь>::<тест> -v` из корня репозитория (venv `.venv` уже активируется окружением).

---

### Task 1: Поля этапа в обоих построителях + dataclass `Stage`

Добавляем `started_at`, `finished_at`, `iteration` в оба источника этапов, чтобы свежесозданные задачи несли поля, а round-trip через dataclass не падал.

**Files:**
- Modify: `app/src/agentmon/env/task_model.py` (функция `build_stages`, словарь этапа ~строки 53-62)
- Modify: `app/src/agentmon/env/task_schema.py` (dataclass `Stage` строки 12-19; функция `build_stages` строки 45-54)
- Test: `app/tests/env/test_task_status_cli.py` (новые тесты) и `app/tests/test_app_smoke.py` не трогаем

**Interfaces:**
- Produces: каждый этап-словарь (DB-модель) и dataclass `Stage` имеют поля `started_at: float|None = None`, `finished_at: float|None = None`, `iteration: int = 1`.

- [ ] **Step 1: Написать падающий тест на поля dataclass и round-trip**

Добавить в конец `app/tests/env/test_task_status_cli.py`:

```python
def test_stage_has_timing_and_iteration_defaults(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(x for x in data["stages"] if x["name"] == "develop")
    assert dev["started_at"] is None
    assert dev["finished_at"] is None
    assert dev["iteration"] == 1


def test_stage_roundtrip_with_new_fields(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    reloaded = ts.load_task(d)          # from_dict(Stage(**s)) не должен падать
    assert reloaded.stages[0].iteration == 1
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_task_status_cli.py::test_stage_has_timing_and_iteration_defaults app/tests/env/test_task_status_cli.py::test_stage_roundtrip_with_new_fields -v`
Expected: FAIL — `KeyError: 'started_at'` / `TypeError: __init__() got an unexpected keyword` или отсутствие ключа.

- [ ] **Step 3: Добавить поля в dataclass `Stage` (task_schema.py)**

```python
@dataclass
class Stage:
    name: str
    enabled: bool
    subagent: str
    artifact: str
    status: str
    changed_files: list
    started_at: float | None = None
    finished_at: float | None = None
    iteration: int = 1
```

- [ ] **Step 4: Передавать дефолты в `task_schema.build_stages`**

Заменить тело цикла `build_stages` (task_schema.py) на:

```python
        stages.append(Stage(name=d["name"], enabled=on, subagent=d["subagent"],
                            artifact=d["artifact"],
                            status="pending" if on else "skipped",
                            changed_files=[],
                            started_at=None, finished_at=None, iteration=1))
```

- [ ] **Step 5: Добавить поля в `task_model.build_stages` (DB-модель)**

В словаре `stage` (task_model.py) добавить три ключа:

```python
        stage = {
            "name": name,
            "enabled": is_enabled,
            "subagent": stage_def["subagent"],
            "artifact": stage_def["artifact"],
            "gate": is_gated,
            "approved": False,
            "status": "pending" if is_enabled else "skipped",
            "changed_files": [],
            "started_at": None,
            "finished_at": None,
            "iteration": 1,
        }
```

- [ ] **Step 6: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest app/tests/env/test_task_status_cli.py -v`
Expected: PASS (все, включая прежние).

- [ ] **Step 7: Коммит**

```bash
git add app/src/agentmon/env/task_model.py app/src/agentmon/env/task_schema.py app/tests/env/test_task_status_cli.py
git commit -m "Монитор: поля started_at/finished_at/iteration в этапах задачи"
```

---

### Task 2: `task_status.py` — тайминги этапа и номер итерации

При переходе этапа в `running` ставим `started_at`; при `done`/`failed` — `finished_at`; повторный `running` после `finished_at` инкрементирует `iteration` и сбрасывает `finished_at`.

**Files:**
- Modify: `template/.claude/tools/task_status.py` (функция `update`, строки 69-106)
- Test: `app/tests/env/test_task_status_cli.py`

**Interfaces:**
- Consumes: поля этапа из Task 1.
- Produces: после `update(..., "running")` у этапа `started_at` заполнено, `iteration≥1`; после `done`/`failed` — `finished_at` заполнено.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_task_status_cli.py`:

```python
def test_cli_stamps_stage_timing(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["started_at"] is not None
    assert dev["finished_at"] is None
    assert dev["iteration"] == 1
    mod.main([str(d), "develop", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["finished_at"] is not None
    assert dev["finished_at"] >= dev["started_at"]


def test_cli_rerun_increments_iteration(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    mod.main([str(d), "develop", "running"])   # повторный прогон в цикле
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["iteration"] == 2
    assert dev["finished_at"] is None          # сброшен до нового завершения
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_task_status_cli.py::test_cli_stamps_stage_timing app/tests/env/test_task_status_cli.py::test_cli_rerun_increments_iteration -v`
Expected: FAIL — `started_at` остаётся `None` / `iteration` не меняется.

- [ ] **Step 3: Реализовать простановку в `update()`**

В `template/.claude/tools/task_status.py`, внутри ветки `else:` (не `approve`), после установки `s["status"] = status` и до пересчёта overall, вставить:

```python
                now_stage = time.time()
                if status == "running":
                    if s.get("finished_at") is not None:
                        # повторный прогон этапа в цикле develop↔testing/review
                        s["iteration"] = int(s.get("iteration", 1)) + 1
                        s["finished_at"] = None
                    else:
                        s.setdefault("iteration", 1)
                    s["started_at"] = now_stage
                elif status in ("done", "failed"):
                    s["finished_at"] = now_stage
```

(Строку `s["status"] = status` и работу с `changed_files` оставить как есть; блок выше идёт сразу после них, внутри того же `else`.)

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest app/tests/env/test_task_status_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/tools/task_status.py app/tests/env/test_task_status_cli.py
git commit -m "task_status: тайминги этапа и номер итерации в task.json"
```

---

### Task 3: `task_status.py` — подкоманды `db-update start|done`

Отдельный «псевдоэтап» `db-update` пишет тайминги загрузки в ИБ в `data["db_update"]`.

**Files:**
- Modify: `template/.claude/tools/task_status.py` (аргпарсер строки 109-118; функция `update`/новая `set_db_update`)
- Test: `app/tests/env/test_task_status_cli.py`

**Interfaces:**
- Produces: `task.json["db_update"] = {"started_at": float, "finished_at": float|None}`. CLI: `task_status.py <dir> db-update start` и `... db-update done`.

- [ ] **Step 1: Написать падающий тест**

```python
def test_cli_db_update_start_and_done(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "db-update", "start"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["db_update"]["started_at"] is not None
    assert data["db_update"]["finished_at"] is None
    mod.main([str(d), "db-update", "done"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["db_update"]["finished_at"] is not None
    assert data["db_update"]["finished_at"] >= data["db_update"]["started_at"]
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_task_status_cli.py::test_cli_db_update_start_and_done -v`
Expected: FAIL — `SystemExit` (argparse не знает статус `start`) или `KeyError: 'db_update'`.

- [ ] **Step 3: Снять жёсткий `choices` со статуса и добавить ветку db-update**

В `main()` заменить аргумент `status` (убрать `choices=VALID`, валидируем вручную) и добавить роутинг:

```python
    ap.add_argument("status",
                    help="pending|running|done|failed|skipped|approve, "
                         "или start|done для псевдоэтапа db-update")
    ap.add_argument("--files", nargs="*", default=[])
    args = ap.parse_args(argv)
    if args.stage == "db-update":
        set_db_update(args.task_dir, args.status)
    else:
        if args.status not in VALID:
            raise SystemExit(f"неизвестный статус: {args.status}")
        update(args.task_dir, args.stage, args.status, args.files)
```

- [ ] **Step 4: Добавить функцию `set_db_update`**

Рядом с `update()` в `task_status.py`:

```python
def set_db_update(task_dir: str, phase: str) -> None:
    """Пишет тайминги обновления ИБ в task.json: phase ∈ {start, done}."""
    if phase not in ("start", "done"):
        raise SystemExit(f"db-update: ожидается start|done, получено {phase!r}")
    path = Path(task_dir) / "task.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    now = time.time()
    du = data.get("db_update") or {}
    if phase == "start":
        du = {"started_at": now, "finished_at": None}
    else:
        du.setdefault("started_at", now)
        du["finished_at"] = now
    data["db_update"] = du
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
```

- [ ] **Step 5: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest app/tests/env/test_task_status_cli.py -v`
Expected: PASS (включая прежние — проверить, что снятие `choices` не сломало `test_cli_unknown_stage_errors`: он даёт неизвестный STAGE и ждёт SystemExit из `update()`, что сохранено).

- [ ] **Step 6: Коммит**

```bash
git add template/.claude/tools/task_status.py app/tests/env/test_task_status_cli.py
git commit -m "task_status: подкоманды db-update start|done"
```

---

### Task 4: `SKILL.md` — интеграция db-update и итераций, удаление `.iteration_count`

Документация оркестрации под новое поведение.

**Files:**
- Modify: `template/.claude/skills/task-orchestration/SKILL.md` (секция «Загрузка в базу…» строки ~86-105; секция «Циклический workflow…» строки ~177-188; секция «Статусы» строки ~171-174)

**Interfaces:** нет (документация).

- [ ] **Step 1: Обновить секцию загрузки в ИБ**

В секции «## Загрузка в базу после этапа `develop` (флаг `update_db`)» добавить явные шаги вокруг загрузки:

```markdown
Перед началом загрузки в ИБ выполни:
`python .claude/tools/task_status.py tasks/task#<id> db-update start`
После успешной загрузки и обновления БД:
`python .claude/tools/task_status.py tasks/task#<id> db-update done`
(при ошибке загрузки `done` не вызывай — тайминг окончания останется пустым).
```

- [ ] **Step 2: Переписать учёт итераций на поле этапа**

В секции «## Циклический workflow develop ↔ testing/review» заменить пункты про `.iteration_count` на:

```markdown
2. При вердикте «✗ НЕ ПРОЙДЕНО» / «✗ НА ДОРАБОТКУ» — не продолжать к следующему
   этапу: вернуть нужный этап в `pending` командой `task_status.py ... <этап> pending`
   и запустить заново. Номер итерации этапа ведётся автоматически: `task_status.py`
   инкрементирует поле `iteration` соответствующего этапа в `task.json` при его
   повторном переходе в `running`. Архивируй артефакты итерации
   (`DEVELOP.md`→`DEVELOP.<n>.md`, где `<n>` — прежнее значение `iteration` этого
   этапа из `task.json`).
3. Лимит — 10 итераций: если `iteration` возвращаемого этапа в `task.json` ≥ 10,
   пометь этап `failed` и остановись.
```

- [ ] **Step 3: Поправить секцию «Статусы» (убрать упоминание ручного счётчика-файла)**

Убедиться, что в секции «## Статусы» и прочих местах нет ссылок на `.iteration_count`; заменить любые оставшиеся упоминания на «поле `iteration` этапа в `task.json`». (Проверка: `grep -n "iteration_count" template/.claude/skills/task-orchestration/SKILL.md` должен быть пуст.)

- [ ] **Step 4: Проверить отсутствие упоминаний файла-счётчика**

Run: `grep -rn "iteration_count" template/.claude/`
Expected: пустой вывод.

- [ ] **Step 5: Коммит**

```bash
git add template/.claude/skills/task-orchestration/SKILL.md
git commit -m "task-orchestration: db-update тайминги и итерация этапа из task.json"
```

---

### Task 5: Колонка `db_update_json` в таблице `tasks`

**Files:**
- Modify: `app/src/agentmon/store/schema.py` (CREATE TABLE tasks строки 20-29; `_ensure_columns` tasks строки 47-53)
- Test: `app/tests/env/test_stack_api.py` (новый тест миграции) или `app/tests/test_api.py`

**Interfaces:**
- Produces: колонка `tasks.db_update_json TEXT` присутствует после `init_schema`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `app/tests/env/test_stack_api.py` (использует `connect`/`init_schema`):

```python
def test_tasks_has_db_update_json_column(tmp_path):
    from agentmon.store.db import connect
    from agentmon.store.schema import init_schema, _existing_columns
    store = connect(str(tmp_path / "s.db"))
    init_schema(store)
    assert "db_update_json" in _existing_columns(store, "tasks")
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_stack_api.py::test_tasks_has_db_update_json_column -v`
Expected: FAIL — колонки нет.

- [ ] **Step 3: Добавить колонку в CREATE TABLE и в миграцию**

В CREATE TABLE tasks добавить `db_update_json TEXT,` (например, после `stages_json TEXT,`). В `_ensure_columns(db, "tasks", {...})` добавить ключ:

```python
        "db_update_json": "TEXT",
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest app/tests/env/test_stack_api.py::test_tasks_has_db_update_json_column -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/store/schema.py app/tests/env/test_stack_api.py
git commit -m "БД: колонка tasks.db_update_json"
```

---

### Task 6: `refresh_project` переносит `stages_json` и `db_update_json`

**Files:**
- Modify: `app/src/agentmon/env/project_api.py` (функция `refresh_project`, строки 380-424)
- Test: `app/tests/env/test_project_actions.py`

**Interfaces:**
- Consumes: `task.json` с `stages`/`db_update`; колонка `db_update_json` (Task 5).
- Produces: после `POST /api/env/projects/{pid}/refresh` в БД `tasks.stages_json` = JSON списка этапов из файла, `tasks.db_update_json` = JSON `db_update` (или NULL).

- [ ] **Step 1: Написать падающий тест**

Добавить в `app/tests/env/test_project_actions.py` (есть `make_client`, `_seed_project`, `_write_task_json`, `TaskRepo`):

```python
def test_refresh_transfers_stages_and_db_update(tmp_path):
    client, store = make_client(tmp_path)
    pid, project_path = _seed_project(store, tmp_path)
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(project_id=pid, name="t", identifier="100500",
                              stages_json="[]", status="planned")
    _write_task_json(project_path, "task#100500", {
        "status": "running", "stage": "develop",
        "started_at": 1.0, "finished_at": None,
        "stages": [{"name": "develop", "status": "running", "iteration": 2,
                    "started_at": 1.0, "finished_at": None}],
        "db_update": {"started_at": 2.0, "finished_at": 3.0},
    })
    r = client.post(f"/api/env/projects/{pid}/refresh")
    assert r.status_code == 200
    import json
    task = TaskRepo(store).get(tid)
    stages = json.loads(task["stages_json"])
    assert stages[0]["iteration"] == 2
    assert json.loads(task["db_update_json"]) == {"started_at": 2.0, "finished_at": 3.0}
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_project_actions.py::test_refresh_transfers_stages_and_db_update -v`
Expected: FAIL — `stages_json` остаётся `"[]"`, `db_update_json` None.

- [ ] **Step 3: Расширить перенос полей в `refresh_project`**

В цикле по задачам, в блоке формирования `fields` (после переноса `stage/started_at/finished_at`), добавить:

```python
            if "stages" in data:
                fields["stages_json"] = json.dumps(data["stages"], ensure_ascii=False)
            if "db_update" in data:
                fields["db_update_json"] = json.dumps(data["db_update"],
                                                       ensure_ascii=False)
```

(`json` уже импортируется в функции.)

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `python -m pytest app/tests/env/test_project_actions.py -v`
Expected: PASS (включая прежние тесты refresh).

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/project_api.py app/tests/env/test_project_actions.py
git commit -m "refresh: перенос stages_json и db_update из task.json в БД"
```

---

### Task 7: Обогащение элементов стека в `_enrich_items`

**Files:**
- Modify: `app/src/agentmon/env/stack_api.py` (функция `_enrich_items`, строки 58-72; добавить импорты `json`, `Path`, `task_folder_name`)
- Test: `app/tests/env/test_stack_api.py`

**Interfaces:**
- Consumes: `tasks` c `stages_json`, `db_update_json`, `stage`, `started_at`, `finished_at`, `max_minutes`, `update_db`, `identifier`; `ProjectRepo` для пути проекта.
- Produces: каждый item содержит дополнительно: `stage`, `started_at`, `finished_at`, `max_minutes`, `update_db` (bool), `db_update` (dict|None), `stages` (list), `last_done_stage` (str|None). Поля этапа: `name, status, enabled, gate, approved, started_at, finished_at, iteration, artifact, artifact_exists`.

- [ ] **Step 1: Написать падающий тест**

Добавить в `app/tests/env/test_stack_api.py`:

```python
def test_enrich_item_exposes_stage_details(tmp_path):
    import json
    from pathlib import Path
    client, store = _make_client_with_store(tmp_path)   # см. Step 1a
    # проект на диске + задача + task.json с готовым этапом и артефактом
    project_path = tmp_path / "proj"
    (project_path / "tasks" / "task#100500").mkdir(parents=True)
    (project_path / "tasks" / "task#100500" / "ANALYZE.md").write_text("ok", encoding="utf-8")
    pid = ProjectRepo(store).add(name="proj", path=str(project_path))
    tid = TaskRepo(store).add(
        project_id=pid, name="t", identifier="100500", status="running",
        stage="plan", started_at=1.0, finished_at=None, max_minutes=30, update_db=1,
        stages_json=json.dumps([
            {"name": "analyze", "status": "done", "enabled": True, "gate": True,
             "approved": True, "started_at": 1.0, "finished_at": 2.0, "iteration": 1,
             "artifact": "ANALYZE.md"},
            {"name": "plan", "status": "running", "enabled": True, "gate": False,
             "approved": False, "started_at": 2.0, "finished_at": None, "iteration": 1,
             "artifact": "ARCHITECT.md"},
        ]))
    TaskRepo(store).update(tid, db_update_json=json.dumps({"started_at": 5.0, "finished_at": 6.0}))
    sid = StackRepo(store).add(name="001")
    StackRepo(store).add_item(sid, tid)

    r = client.get("/api/env/stacks")
    item = r.json()["stacks"][0]["items"][0]
    assert item["stage"] == "plan"
    assert item["max_minutes"] == 30
    assert item["update_db"] is True
    assert item["db_update"] == {"started_at": 5.0, "finished_at": 6.0}
    assert item["last_done_stage"] == "analyze"
    analyze = next(s for s in item["stages"] if s["name"] == "analyze")
    assert analyze["artifact_exists"] is True
    plan = next(s for s in item["stages"] if s["name"] == "plan")
    assert plan["artifact_exists"] is False
```

- [ ] **Step 1a: Добавить фабрику клиента со стором (если её нет в файле)**

Если в `test_stack_api.py` нет функции, возвращающей `(client, store)`, добавить:

```python
def _make_client_with_store(tmp_path):
    db = open_db(tmp_path / "reg.sqlite")
    mon = FakeMonitor()
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=ProjectRegistry(db), queue=TaskQueue(db),
                     monitor=mon, store=store)
    return TestClient(app), store
```

(Сверить с уже существующей фабрикой в файле и переиспользовать её, если она есть.)

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_stack_api.py::test_enrich_item_exposes_stage_details -v`
Expected: FAIL — ключей `stage`/`stages`/`last_done_stage` нет в item.

- [ ] **Step 3: Реализовать обогащение**

В начало `stack_api.py` добавить импорты:

```python
import json
from pathlib import Path
from agentmon.env.task_schema import task_folder_name
```

Заменить тело `_enrich_items` на (сохранив прежние базовые поля):

```python
    def _enrich_items(sr, tr, pr, stack_id):
        result = []
        for item in sr.items(stack_id):
            task = tr.get(item["task_id"])
            if task is None:
                continue
            try:
                stages = json.loads(task.get("stages_json") or "[]")
            except (ValueError, TypeError):
                stages = []
            db_update = None
            if task.get("db_update_json"):
                try:
                    db_update = json.loads(task["db_update_json"])
                except (ValueError, TypeError):
                    db_update = None

            # путь проекта на диске — для проверки наличия артефактов
            project = pr.get(task["project_id"])
            task_dir = None
            if project is not None:
                folder = task_folder_name(task["id"], task.get("identifier"))
                task_dir = Path(project["path"]) / "tasks" / folder

            last_done = None
            enriched_stages = []
            for s in stages:
                artifact = s.get("artifact") or ""
                exists = bool(task_dir and artifact
                              and (task_dir / artifact).exists())
                enriched_stages.append({
                    "name": s.get("name"),
                    "status": s.get("status"),
                    "enabled": s.get("enabled"),
                    "gate": s.get("gate"),
                    "approved": s.get("approved"),
                    "started_at": s.get("started_at"),
                    "finished_at": s.get("finished_at"),
                    "iteration": s.get("iteration", 1),
                    "artifact": artifact,
                    "artifact_exists": exists,
                })
                if s.get("status") == "done":
                    last_done = s.get("name")

            result.append({
                "item_id": item["id"],
                "task_id": task["id"],
                "task_name": task["name"],
                "project_id": task["project_id"],
                "task_status": task["status"],
                "stage": task.get("stage"),
                "started_at": task.get("started_at"),
                "finished_at": task.get("finished_at"),
                "max_minutes": task.get("max_minutes"),
                "update_db": bool(task.get("update_db")),
                "db_update": db_update,
                "stages": enriched_stages,
                "last_done_stage": last_done,
            })
        return result
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest app/tests/env/test_stack_api.py -v`
Expected: PASS (включая прежний тест формы ответа — базовые поля сохранены).

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/stack_api.py app/tests/env/test_stack_api.py
git commit -m "Монитор: обогащение элементов стека этапами, таймингами, db_update"
```

---

### Task 8: Эндпоинт `POST /api/env/tasks/{tid}/open-report`

Открывает артефакт указанного этапа в VS Code. Живёт в `build_project_router` (там уже инжектится `popen` и есть `open_vscode`).

**Files:**
- Modify: `app/src/agentmon/env/project_api.py` (рядом с `open_vscode`, строки 426-445; при необходимости импорт `task_folder_name`)
- Test: `app/tests/env/test_project_actions.py`

**Interfaces:**
- Consumes: `popen` (инжекция), `TaskRepo`, `ProjectRepo`, `task_folder_name`.
- Produces: `POST /api/env/tasks/{tid}/open-report` тело `{"stage": "<имя>"}` → `popen(["code", <путь артефакта>])`; 404 если задачи/этапа/файла нет; 500 если `code` не в PATH.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_project_actions.py`:

```python
def test_open_report_launches_code(tmp_path):
    rec = RecordingPopen()
    client, store = make_client(tmp_path, popen=rec)
    pid, project_path = _seed_project(store, tmp_path)
    d = project_path / "tasks" / "task#100500"
    d.mkdir(parents=True)
    (d / "ANALYZE.md").write_text("ok", encoding="utf-8")
    import json
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(
        project_id=pid, name="t", identifier="100500", status="running",
        stages_json=json.dumps([{"name": "analyze", "status": "done",
                                 "artifact": "ANALYZE.md"}]))
    r = client.post(f"/api/env/tasks/{tid}/open-report", json={"stage": "analyze"})
    assert r.status_code == 200
    assert rec.calls == [["code", str(d / "ANALYZE.md")]]


def test_open_report_404_when_file_missing(tmp_path):
    rec = RecordingPopen()
    client, store = make_client(tmp_path, popen=rec)
    pid, project_path = _seed_project(store, tmp_path)
    import json
    from agentmon.store.tasks import TaskRepo
    tid = TaskRepo(store).add(
        project_id=pid, name="t", identifier="100500", status="running",
        stages_json=json.dumps([{"name": "analyze", "status": "done",
                                 "artifact": "ANALYZE.md"}]))
    r = client.post(f"/api/env/tasks/{tid}/open-report", json={"stage": "analyze"})
    assert r.status_code == 404
    assert rec.calls == []
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_project_actions.py::test_open_report_launches_code app/tests/env/test_project_actions.py::test_open_report_404_when_file_missing -v`
Expected: FAIL — 404/405 (маршрута нет).

- [ ] **Step 3: Реализовать эндпоинт**

В `project_api.py` добавить импорт (к существующим import в начале модуля):

```python
from .task_schema import task_folder_name
```

После `open_vscode` (перед `return router`) добавить:

```python
    @router.post("/api/env/tasks/{tid}/open-report")
    def open_report(tid: int, body: dict):
        """Открывает артефакт указанного этапа задачи в VS Code."""
        import json
        from pathlib import Path
        from agentmon.store.tasks import TaskRepo
        task_repo = TaskRepo(store)
        task = task_repo.get(tid)
        if task is None:
            raise HTTPException(status_code=404, detail=f"нет задачи с id={tid}")
        stage_name = (body or {}).get("stage")
        try:
            stages = json.loads(task.get("stages_json") or "[]")
        except (ValueError, TypeError):
            stages = []
        stage = next((s for s in stages if s.get("name") == stage_name), None)
        if stage is None or not stage.get("artifact"):
            raise HTTPException(status_code=404,
                                detail=f"этап {stage_name!r} или его артефакт не найден")
        project_repo, _ = get_repos()
        project = project_repo.get(task["project_id"])
        if project is None:
            raise HTTPException(status_code=404, detail="проект задачи не найден")
        folder = task_folder_name(task["id"], task.get("identifier"))
        artifact_path = Path(project["path"]) / "tasks" / folder / stage["artifact"]
        if not artifact_path.exists():
            raise HTTPException(status_code=404,
                                detail=f"файл отчёта не найден: {stage['artifact']}")
        try:
            popen(["code", str(artifact_path)])
        except FileNotFoundError:
            raise HTTPException(status_code=500,
                                detail="команда 'code' не найдена в PATH — установите VS Code CLI")
        except Exception as exc:                           # noqa: BLE001
            raise HTTPException(status_code=500,
                                detail=f"не удалось открыть VS Code: {exc}")
        return {"ok": True}
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `python -m pytest app/tests/env/test_project_actions.py -v`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/project_api.py app/tests/env/test_project_actions.py
git commit -m "API: open-report — открыть артефакт этапа в VS Code"
```

---

### Task 9: Фронтенд — свёрнутая строка, разворот, кнопка «Отчёт», синк 5 мин

**Files:**
- Modify: `app/web/start.js` (функции `renderStacks` строки 155-217; init-блок строки 435-452; новые функции `toggleTaskDetails`, `openReport`, `syncRunningProjects`, хелпер форматирования времени)
- Modify: `app/web/index.html` (`<style>` рядом со `.stack-item`, строки ~129-137 — стили `.task-row`, `.task-details`, `.chevron`, `.report-btn`)
- Test: `app/tests/env/test_start_page.py` (проверка отдаваемого `start.js`)

**Interfaces:**
- Consumes: обогащённые поля item из Task 7 (`stage`, `started_at`, `finished_at`, `max_minutes`, `db_update`, `stages`, `last_done_stage`); эндпоинт `open-report` (Task 8); `refresh` (Task 6).
- Produces: `window.toggleTaskDetails(taskId)`, `window.openReport(taskId, stage)`.

- [ ] **Step 1: Написать падающий тест (served JS содержит новые функции)**

Добавить в `app/tests/env/test_start_page.py`:

```python
def test_start_js_has_expand_and_report(tmp_path):
    client = _client(tmp_path)
    js = client.get("/static/start.js").text
    assert "function toggleTaskDetails" in js
    assert "function openReport" in js
    assert "open-report" in js
    assert "expandedTasks" in js
    assert "5 * 60 * 1000" in js          # таймер синка 5 минут
```

(Если статик отдаётся по другому пути — свериться с `test_header_consistency.py`/`index.html` `<script src>` и поправить URL.)

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python -m pytest app/tests/env/test_start_page.py::test_start_js_has_expand_and_report -v`
Expected: FAIL — функций нет.

- [ ] **Step 3: Добавить состояние и хелпер времени (вверх start.js, рядом со строкой 3)**

```javascript
const expandedTasks = new Set();   // task_id развёрнутых карточек

function fmtTime(sec) {
  if (!sec) return "—";
  const d = new Date(sec * 1000);
  return d.toLocaleString("ru-RU");
}

function fmtElapsed(startSec, endSec) {
  if (!startSec) return "—";
  const end = endSec ? endSec * 1000 : Date.now();
  const mins = Math.floor((end - startSec * 1000) / 60000);
  return mins + " мин";
}
```

- [ ] **Step 4: Переписать рендер элемента в `renderStacks`**

Заменить формирование `itemsHtml` (строки 174-184) на свёрнутую строку + панель деталей:

```javascript
      const itemsHtml = stack.items && stack.items.length > 0
        ? stack.items.map(item => {
            const itemCls = item.task_status === "выполняется" ? "status-running" :
                          item.task_status === "ошибка" ? "status-failed" : "";
            const open = expandedTasks.has(item.task_id);
            const stageInfo = item.stage ? ` · ${escHtml(item.stage)}` : "";
            const elapsed = item.started_at
              ? ` · ${fmtElapsed(item.started_at, item.finished_at)}`
                + (item.max_minutes ? ` / ${item.max_minutes} мин` : "")
              : "";
            const stagesRows = (item.stages || []).map(s => {
              const rep = (s.name === item.last_done_stage && s.artifact_exists)
                ? `<button class="report-btn" onclick="event.stopPropagation(); openReport(${Number(item.task_id)}, '${escHtml(s.name)}')">Отчёт</button>`
                : "";
              return `<tr><td>${escHtml(s.name)}</td><td>${escHtml(s.status || "")}</td>`
                + `<td>${s.iteration || 1}</td><td>${fmtTime(s.started_at)}</td>`
                + `<td>${fmtTime(s.finished_at)}</td><td>${rep}</td></tr>`;
            }).join("");
            const dbRow = item.db_update
              ? `<div>Обновление БД: ${fmtTime(item.db_update.started_at)} → ${fmtTime(item.db_update.finished_at)}</div>`
              : "";
            const details = `<div class="task-details" ${open ? "" : 'style="display:none"'}>
                <div>Начало: ${fmtTime(item.started_at)} · Окончание: ${fmtTime(item.finished_at)} · Лимит: ${item.max_minutes || "—"} мин</div>
                ${dbRow}
                <table class="stage-table"><thead><tr><th>Этап</th><th>Статус</th><th>Итер.</th><th>Начало</th><th>Окончание</th><th></th></tr></thead>
                <tbody>${stagesRows}</tbody></table>
              </div>`;
            return `<div class="stack-item" draggable="true" data-task-id="${item.task_id}"
                         data-item-id="${item.item_id}" data-project-id="${item.project_id}">
              <div class="task-row" onclick="toggleTaskDetails(${Number(item.task_id)})">
                <span class="chevron">${open ? "▾" : "▸"}</span>
                <span class="${itemCls}">${escHtml(item.task_name)}</span>
                <span style="font-size:10px; color:var(--muted);"> (${escHtml(item.task_status)})${stageInfo}${elapsed}</span>
              </div>
              ${details}
            </div>`;
          }).join("")
        : `<div class="stack-item-empty">Нет задач</div>`;
```

- [ ] **Step 5: Добавить функции `toggleTaskDetails`, `openReport`, `syncRunningProjects`**

В `start.js` (рядом с другими функциями, до init):

```javascript
function toggleTaskDetails(taskId) {
  if (expandedTasks.has(taskId)) expandedTasks.delete(taskId);
  else expandedTasks.add(taskId);
  renderStacks();
}

async function openReport(taskId, stage) {
  try {
    const r = await fetch(`/api/env/tasks/${taskId}/open-report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
    if (!r.ok) {
      let detail = r.status;
      try { detail = (await r.json()).detail || detail; } catch (_) {}
      alert("Не удалось открыть отчёт: " + detail);
    }
  } catch (e) {
    console.error("open report error", e);
    alert("Ошибка соединения");
  }
}

// Раз в 5 минут подтягиваем task.json → БД для проектов с задачами в running-стеках
async function syncRunningProjects() {
  try {
    const r = await fetch("/api/env/stacks");
    if (!r.ok) return;
    const data = await r.json();
    const pids = new Set();
    (data.stacks || []).forEach(st => {
      if (st.status === "running") (st.items || []).forEach(it => pids.add(it.project_id));
    });
    for (const pid of pids) {
      await fetch(`/api/env/projects/${pid}/refresh`, { method: "POST" });
    }
    await renderStacks();
  } catch (e) {
    console.error("sync running projects error", e);
  }
}
```

- [ ] **Step 6: Повесить таймер синка 5 минут в init-блоке**

В `document.addEventListener("DOMContentLoaded", ...)` после существующего `setInterval` добавить:

```javascript
  // Синхронизация task.json → БД раз в 5 минут
  setInterval(syncRunningProjects, 5 * 60 * 1000);
```

- [ ] **Step 7: Добавить стили в `index.html` `<style>`**

Рядом со `.stack-item` добавить:

```css
    .task-row { display:flex; align-items:center; gap:4px; cursor:pointer; }
    .chevron { font-size:10px; color:var(--muted); width:10px; }
    .task-details { margin-top:6px; font-size:11px; color:var(--muted); }
    .stage-table { width:100%; border-collapse:collapse; margin-top:4px; }
    .stage-table th, .stage-table td { text-align:left; padding:2px 4px; border-bottom:1px solid #30363d; }
    .report-btn { font-size:10px; padding:1px 6px; cursor:pointer; background:#21262d; color:#c9d1d9; border:1px solid #30363d; border-radius:4px; }
    .report-btn:hover { background:#30363d; }
```

- [ ] **Step 8: Запустить фронтенд-тест + полный прогон**

Run: `python -m pytest app/tests/env/test_start_page.py -v`
Expected: PASS.

- [ ] **Step 9: Запустить весь тест-сьют**

Run: `python -m pytest -q`
Expected: PASS (без регрессий).

- [ ] **Step 10: Коммит**

```bash
git add app/web/start.js app/web/index.html app/tests/env/test_start_page.py
git commit -m "Монитор: свёрнутая карточка задачи с разворотом, отчёт этапа, синк 5 мин"
```

---

## Проверка глазами (ручная)

После Task 9: запустить приложение (`python run.py`), открыть `/`, создать стек с задачей, убедиться:
- задача — одна строка со шевроном; клик разворачивает панель;
- в панели видны тайминги задачи, таблица этапов с итерациями, блок обновления БД (если `update_db`);
- у последнего завершённого этапа есть кнопка «Отчёт», она открывает артефакт в VS Code;
- перетаскивание задач между стеками не сломалось;
- состояние разворота переживает авто-ре-рендер (5 сек).

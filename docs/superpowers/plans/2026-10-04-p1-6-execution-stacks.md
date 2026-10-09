# P1.6 — Панель «Выполнение» (стеки) — Implementation Plan

> REQUIRED SUB-SKILL: superpowers:subagent-driven-development.

**Goal:** Стеки выполнения: модель+API (CRUD/items/reorder/start/stop/delete), стек-раннер (последовательно внутри стека, параллельно между стеками, project-lock), тестовые задачи-заглушки, UI панель «Выполнение» с drag-drop.

## Global Constraints
- Задачи одного проекта — последовательно (project-lock); стеки параллельны. UI vanilla + SortableJS (вендор-файл, без сборки).
- monitor.start получает опциональный `cmd`; test-задача = sleep 60. Проект для monitor — лёгкий объект из ProjectRepo-строки.
- Русский; тёмная тема.

## Files
- Modify: `app/src/agentmon/store/schema.py` (tasks + `kind TEXT NOT NULL DEFAULT 'real'`); `app/src/agentmon/store/tasks.py` (add поддерживает kind)
- Modify: `app/src/agentmon/monitor.py` (start cmd override)
- Create: `app/src/agentmon/env/stack_dispatcher.py`, `app/src/agentmon/env/stack_api.py`
- Modify: `app/src/agentmon/api.py` (роутер), `app/src/agentmon/__main__.py` (тик стеков)
- Create: `app/web/vendor/Sortable.min.js` (вендор), обновить `app/web/index.html`+`start.js` (панель «Выполнение»)
- Tests: `test_monitor_cmd.py`, `test_stack_api.py`, `test_stack_dispatcher.py`, `test_exec_panel.py`

---

## Task 1: monitor.start cmd override + task kind
**Changes:**
- `monitor.py` `start(self, project, prompt="", task_id=None, cmd=None)`: if `cmd` is not None → `launch(cmd, cwd=project.path, ...)`; else build `_cmd_for(project, prompt)`. Keep everything else.
- `store/schema.py`: add `kind TEXT NOT NULL DEFAULT 'real'` to `tasks`.
- `store/tasks.py` `TaskRepo.add(...)`: accept `kind="real"` and persist.

- [ ] Step1 failing tests: `app/tests/env/test_monitor_cmd.py` (fake runner: `monitor.start(project_like, cmd=["python","-c","pass"], task_id=1)` → runner.launch called with that cmd, run recorded) and extend `tests/store/test_tasks.py` (add with kind="test" persists kind). 
- [ ] Step2 fail. Step3 implement. Step4 pass (+ tests/store + tests/env/test_monitor* ). Step5 commit `feat(stacks): monitor cmd override + task kind`.

---

## Task 2: Стек-раннер (stack_dispatcher.py)
**Interfaces:** `StackDispatcher(store, monitor, now_fn=time.time)`; `tick()`:
- для каждого стека со status "running": взять его items по порядку; найти первую задачу (TaskRepo.get) со статусом not in {done, failed}; 
  - если нет таких → стек done (status "idle"); 
  - если проект задачи занят (есть живой прогон: `monitor.is_alive(project_like(project_id, path))` или `store.running(project_id)` c живым pid) → пропустить (ждать);
  - иначе: если задача ещё не running (status planned/queued) → `monitor.start(project_like, prompt_or_cmd, task_id=task_id)` (cmd для kind=test = [sys.executable,"-c","import time;time.sleep(60)"]; иначе prompt оркестрации `orchestration_prompt(task_id)` из task_schema) + TaskRepo.set_status(task_id, "running"); 
  - если running → проверить `monitor.task_status(task_id)`: done→set_status done; failed→set_status failed (дальше тик двинет к следующей).
- `project_like(project_id)` строит объект из ProjectRepo-строки (SimpleNamespace id/path/name/key/backend/claude_cmd).

- [ ] Step1 failing test `test_stack_dispatcher.py`: fake monitor (start records (project_id, cmd/prompt, task_id); is_alive/task_status settable), store seeded (project, 2 задачи одного проекта в стеке running). tick → первая задача стартует (monitor.start вызван), помечена running; вторая НЕ стартует пока первая alive (project-lock); после task_status done первой → вторая стартует; test-задача → start получил cmd со sleep. 
- [ ] Step2 fail. Step3 implement. Step4 pass. Step5 commit `feat(stacks): стек-раннер (последовательно, project-lock, тест-заглушки)`.

---

## Task 3: API стеков (stack_api.py) + wire __main__
**Interfaces:** `build_stack_router(store, monitor) -> APIRouter`; create_app подключает; __main__ добавляет тик StackDispatcher в lifespan-цикл (рядом с dispatcher).
Маршруты (см. спек): GET /api/env/stacks; POST /api/env/stacks; DELETE /{id} (срубить прогоны + удалить); POST /{id}/items {task_id} (только planned); DELETE /{id}/items/{item_id}; POST /{id}/reorder {task_ids} (не-running); POST /{id}/start; POST /{id}/stop (срубить текущий прогон); POST /api/env/tasks/test {project_id,name?} (kind=test, planned, один этап). 503 если store None.

- [ ] Step1 failing test `test_stack_api.py` (CRUD; add item только planned→иначе 400; reorder не-running; start→status running; stop→stopped + monitor.stop вызван; delete; test-task endpoint создаёт kind=test). TestClient со store + fake monitor.
- [ ] Step2 fail. Step3 implement + wire create_app + __main__ (тик). Step4 pass + FULL. Step5 commit `feat(stacks): API стеков + тик в __main__`.

---

## Task 4: UI панель «Выполнение» + SortableJS
- Добавить `app/web/vendor/Sortable.min.js` (минифицированный SortableJS, один файл — скачать/вставить; без сборки). Подключить в index.html.
- Обновить `index.html`+`start.js`: панель «Выполнение» — колонки-стеки (GET /api/env/stacks), кнопки «Создать стек»/«Создать тестовую задачу», у стека запуск/стоп/удаление, список задач с SortableJS (drag из дерева planned-задач в стек → POST items; reorder внутри не-running → POST reorder). Автообновление.
- Тест `test_exec_panel.py`: `/` содержит «Выполнение» и подключение Sortable; (behaviour drag — не тестируем в unit, только наличие разметки/скрипта).

- [ ] Step1 failing test. Step2 fail. Step3 implement. Step4 pass + FULL. Step5 commit `feat(stacks): web-панель «Выполнение» (drag-drop стеки)`.

## Self-Review
- monitor cmd+kind (T1), раннер (T2), API+тик (T3), UI (T4) покрывают спек.
- project-lock сериализует задачи одного проекта; стеки двигаются параллельно тиком.
- Отложено: богатая визуализация; repoint task_status.py агента на API (слежение за статусами из прогонов делает раннер через task_status монитора).

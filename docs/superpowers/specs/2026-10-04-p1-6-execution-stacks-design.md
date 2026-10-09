# P1.6 — Панель «Выполнение» (стеки) — дизайн

Дата: 2026-10-04. Статус: утверждён (Фаза 1).

## Контекст
Панель «Выполнение» из `tmp/NOTE.md`: стеки выполнения. В стек перетаскивается задача
в статусе «Запланирована». Стек: запуск/стоп/удаление (удаление срубает процесс).
Стек — список задач, выполняемых последовательно; несколько стеков — параллельно; в
незапущенном стеке можно менять порядок. Нужны тестовые задачи-заглушки (sleep ~1 мин
→ успех). Решения: задачи одного проекта — последовательно (project-lock); стеки
параллельны между разными проектами; UI vanilla + SortableJS.

## Модель
- StackRepo (P1.1): stacks(status idle|running|stopped) + stack_items(order). 
- Задача получает `kind` (real|test) — поле в schema (test = заглушка sleep).
- Стек-раннер (StackDispatcher): по тику для каждого running-стека берёт первую
  незавершённую задачу; если её проект уже занят живым прогоном (project-lock) —
  ждёт; иначе запускает через monitor; по завершении (task_status done/failed)
  переходит к следующей; когда все готовы — стек → idle/done.

## Запуск задачи
- monitor.start получает опциональный `cmd` (список): если задан — запускается он,
  иначе `claude -p "<orchestration prompt>"` (как сейчас).
- test-задача (kind=test): `cmd=[python, -c, "import time;time.sleep(60)"]` → успешный
  выход. Реальная задача: промпт оркестрации по её `tasks/task#<id>`.
- Проект для monitor берётся как лёгкий объект из ProjectRepo-строки (id/path/name/
  key/backend/claude_cmd) — detached-ядро не требует agentmon-registry.

## API (`env/stack_api.py`)
- `GET /api/env/stacks` → стеки с элементами (task id/name/project/status).
- `POST /api/env/stacks {name}` → создать; `DELETE /api/env/stacks/{id}` → срубить
  running-прогон элементов + удалить.
- `POST /api/env/stacks/{id}/items {task_id}` → добавить задачу (только «planned»);
  `DELETE /api/env/stacks/{id}/items/{item_id}`; `POST /api/env/stacks/{id}/reorder
  {task_ids[]}` (только для не-running стека).
- `POST /api/env/stacks/{id}/start` / `/stop` → статус running/stopped; stop срубает
  текущий прогон.
- `POST /api/env/tasks/test {project_id, name?}` → создать тестовую задачу (kind=test,
  один этап-заглушка), статус planned.

## Стек-раннер
- `StackDispatcher(store, monitor, now_fn).tick()` — проходит running-стеки; для первой
  задачи стека со статусом != done/failed: если проект занят (monitor живой прогон по
  project_id) — пропустить; иначе `monitor.start(project_like, prompt_or_cmd, task_id)`
  + пометить задачу running; по завершении прогона — done/failed задаче, дальше.
- Подключается в `__main__` lifespan (отдельный тик рядом с dispatcher), или встроить в
  существующий dispatch loop.

## Web — панель «Выполнение» (в стартовой)
Колонки-стеки: заголовок, кнопки запуск/стоп/удаление; список задач (SortableJS —
перетаскивание из дерева «Проекты и задачи» и переупорядочивание внутри не-running
стека). Кнопка «Создать стек», «Создать тестовую задачу». Связь с деревом: planned-
задачи можно перетащить в стек. Тёмная тема. SortableJS подключить как статик-вендор
(один файл, без сборки).

## Границы
- Параллельность между стеками обеспечивается тиком (несколько стеков двигаются), с
  project-lock. Истинная одновременность процессов — через detached-раннер.
- Богатая визуализация прогресса — минимально (статусы/подсветка).

## Тестирование
- stack API: CRUD, add item (только planned), reorder (не-running), start/stop, delete
  срубает; test-task endpoint создаёт kind=test planned.
- StackDispatcher: running-стек запускает первую задачу (monitor.start вызван с cmd для
  test / prompt для real); project-lock (вторая задача того же проекта не стартует,
  пока первый прогон жив); завершение → следующая; через фейковый monitor/runner.
- monitor.start с cmd override запускает cmd (фейковый runner).
- Полный набор зелёный.

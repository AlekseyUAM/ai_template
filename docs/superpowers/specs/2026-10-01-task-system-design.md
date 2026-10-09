# Система задач — дизайн (подсистема №3)

Дата: 2026-10-01
Статус: утверждён к реализации (автономный режим)

## Контекст

Подсистема №3 даёт работу с задачами поверх окружения (№1 — установщик/ядро, №2 —
содержимое). В agentmon добавляется мастер «Создать задачу», на диске появляется
структура `tasks/task#<id>/`, а субагенты по ходу работы пишут статусы этапов и
артефакты. Рамочные решения проекта действуют (своя реализация, кросс-платформа,
без новых зависимостей, русский, Вариант A — файл источник истины).

Разграничение: **выполнение этапов** ведёт claude-оркестратор внутри проекта
(контент №2/№3 + существующая очередь agentmon), а Python-сторона №3 даёт
структуру задачи, обновление статусов, мастер и API. Автономный прогон **списка**
задач — это №4 (здесь — одиночная задача).

## Структура задачи на диске

```
<project>/tasks/task#<id>/
├─ task.json      # настройки этапов + статусы + изменённые файлы (источник истины)
├─ TASK.md        # человекочитаемое описание: цель, план, ограничения
├─ ANALYZE.md     # ← артефакты этапов, пишутся по ходу выполнения
├─ ARCHITECT.md
├─ TESTS.md
├─ DEVELOP.md
├─ TESTING.md
├─ REVIEW.md
└─ DOCS.md
```

`id` — шестизначный, следующий за максимальным среди существующих `task#NNNNNN`
(база 100001). Детерминирован, тестируем.

### task.json

```json
{
  "id": "100001",
  "title": "...",
  "goal": "...",
  "plan": "...",
  "constraints": "...",
  "created_at": null,
  "stages": [
    {"name": "analyze",  "enabled": true, "subagent": "analyst",   "artifact": "ANALYZE.md",   "status": "pending", "changed_files": []},
    {"name": "plan",     "enabled": true, "subagent": "architect",  "artifact": "ARCHITECT.md", "status": "pending", "changed_files": []},
    {"name": "tests",    "enabled": true, "subagent": "tester",     "artifact": "TESTS.md",     "status": "pending", "changed_files": []},
    {"name": "develop",  "enabled": true, "subagent": "developer",  "artifact": "DEVELOP.md",   "status": "pending", "changed_files": []},
    {"name": "testing",  "enabled": true, "subagent": "tester",     "artifact": "TESTING.md",   "status": "pending", "changed_files": []},
    {"name": "review",   "enabled": true, "subagent": "reviewer",   "artifact": "REVIEW.md",    "status": "pending", "changed_files": []},
    {"name": "docs",     "enabled": true, "subagent": "developer",  "artifact": "DOCS.md",      "status": "pending", "changed_files": []}
  ]
}
```

`status ∈ {pending, running, done, failed, skipped}`. Отключённый этап (`enabled:false`)
получает `status:"skipped"` при создании.

## Компоненты

### `task_schema.py` (agentmon-сторона)

- `@dataclass Stage(name, enabled, subagent, artifact, status, changed_files)`.
- `@dataclass TaskSpec(id, title, goal, plan, constraints, created_at, stages)`.
- `DEFAULT_STAGES` — 7 этапов выше.
- `build_stages(enabled_names) -> list[Stage]` — собирает этапы, отключённые →
  `skipped`.
- `next_task_id(project_dir) -> str` — max существующих +1, база 100001, 6 цифр.
- `create_task(project_dir, *, title, goal, plan, constraints, enabled_stages, now=None) -> TaskSpec`
  — создаёт каталог `tasks/task#<id>/`, пишет `task.json` и `TASK.md`.
- `load_task(task_dir) / save_task(task_dir, spec)`.
- `list_tasks(project_dir) -> list[TaskSpec]`.
- `update_stage(task_dir, stage_name, *, status, changed_files=None)` — правит один
  этап в `task.json` (для статус-CLI и API).

### `content/tools/task_status.py` (деплоится в проект)

Самодостаточный CLI (без импорта agentmon — проект не держит agentmon на PYTHONPATH):
`python task_status.py <task_dir> <stage> <status> [--files a.bsl b.bsl]` — читает
`task.json`, ставит статус этапа и дополняет `changed_files`, пишет обратно.
Оркестратор/субагенты вызывают его, чтобы обновлять статус структурно, а не правя
JSON руками. Деплоится через `content.py` в `.claude/tools/task_status.py`.

### `task_api.py` (роутер в agentmon)

- `POST /api/tasks/create` — тело `{project_id, title, goal, plan, constraints,
  enabled_stages[], enqueue: bool}`. Создаёт структуру задачи в каталоге проекта
  (путь берётся из реестра agentmon по `project_id`); при `enqueue` ставит в
  очередь agentmon задачу с промптом, указывающим оркестратору выполнить
  `tasks/task#<id>` по этапам. Возвращает `{task: {...}}`.
- `GET /api/tasks?project_id=...` — список задач проекта со статусами этапов.
- Подключается в `create_app` (как роутер окружения).

### Web-страница «Создать задачу»

Поля: заголовок, цель, план (многострочно), ограничения, чекбоксы 7 этапов,
галка «поставить в очередь сейчас». Submit → `POST /api/tasks/create`, показывает
созданную задачу и статусы. Ссылка со страницы index. Отдаётся существующим
паттерном FileResponse + `/static`.

### Контент оркестрации (в дерево content №2)

- `agents/orchestrator.md` — главный агент: классифицирует задачу, ведёт по
  включённым этапам, делегирует 5 субагентам, после каждого этапа вызывает
  `task_status.py` (running→done/failed) и следит за артефактом этапа.
- `skills/task-orchestration/SKILL.md` — процедура выполнения задачи по `task.json`:
  порядок этапов, гейты (ручное подтверждение после анализа/плана — опционально),
  обновление статусов, запись `<ARTIFACT>.md`.
- `rules/task-lifecycle.md` — правило: при работе над задачей читать `task.json`,
  уважать `enabled`, писать артефакт и статус каждого этапа.

## Правки в существующем коде

- `content.py`: добавить копирование каталога `tools/` в `.claude/tools/`; оркестратор
  (`orchestrator.md`) попадает автоматически (копирование `agents/*`). Валидационный
  тест контента обновить: агентов теперь 6 (добавлен orchestrator).

## Границы (не входит в №3)

- Автономный прогон **списка** задач без участия — №4.
- Бенчмарки — №5.
- Реальное исполнение этапов (делегирование, прогон тестов) ведёт claude-оркестратор
  через контент и очередь agentmon; Python №3 не реализует собственный раннер
  субагентов.

## Тестирование

- `task_schema`: `next_task_id` (пустой проект → 100001; с задачами → max+1);
  `create_task` пишет `task.json`+`TASK.md`, отключённые этапы → skipped; `list_tasks`;
  `update_stage` меняет статус и дополняет changed_files; round-trip load/save.
- `task_status.py` (CLI): запуск с аргументами на временном `task.json` ставит статус
  и файлы; неизвестный этап → ненулевой код + сообщение.
- `task_api`: POST создаёт структуру и (при enqueue) кладёт задачу в очередь
  (проверка через реестр/очередь agentmon на TestClient); GET возвращает список;
  неизвестный project_id → 404.
- Web-страница «Создать задачу» отдаётся (содержит заголовок).
- Контент: orchestrator-агент валиден; `task-orchestration` скил и `task-lifecycle`
  правило валидны; `content.py` деплоит `.claude/tools/task_status.py`.
- Интеграция: после `create_task`+деплоя контента в проекте есть структура задачи и
  `.claude/tools/task_status.py`; полный набор тестов зелёный.

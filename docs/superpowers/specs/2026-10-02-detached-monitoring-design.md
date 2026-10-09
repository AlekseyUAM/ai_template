# Detached-мониторинг агентов — дизайн

Дата: 2026-10-02
Статус: на утверждение (крупный рефактор ядра agentmon)

## Зачем

Текущая модель agentmon держит агента в PTY внутри процесса монитора: агенты
гибнут вместе с монитором, слежение завязано на владении PTY и типизацию stdin
(чат). Чат убран → интерактивный stdin не нужен. Переходим на **detached-процессы +
PID + JSONL + код выхода**: устойчиво к перезапуску монитора, кросс-платформенно,
проще.

## Ключевая идея

Каждую задачу очереди запускаем headless-командой `claude -p "<промпт>"`
(`--dangerously-skip-permissions`) **отдельным detached-процессом** в каталоге
проекта. Промпт — это промпт оркестрации (#3/#4): «Выполни задачу tasks/task#… по
этапам, следуй task-orchestration». Процесс отрабатывает задачу (оркестратор ведёт
этапы через субагентов) и завершается. Слежение:
- **PID жив** → агент работает; PID исчез → завершился.
- **Код выхода** (через wrapper) → success/fail.
- **JSONL** `claude` (observer, как сейчас) → модель, токены, стоимость, фаза, idle/generating.
- **task.json** → семантический прогресс этапов.

## Компоненты

### `run_wrapper.py` (кросс-платформенный захват кода выхода)
`python -m agentmon.run_wrapper <exit_file> -- <cmd...>`: запускает дочерний
процесс, по завершении пишет его код выхода в `<exit_file>`. Нужен, т.к. у
detached-процесса код выхста иначе не получить после факта. Кросс-платформенно
(просто Python subprocess).

### `runner_detached.py`
- `launch(cmd: list, cwd: str, log_file: str, exit_file: str) -> int` — запускает
  `run_wrapper` обёрнутый `cmd` detached, stdin=DEVNULL, stdout/stderr→log_file;
  Linux: `start_new_session=True`; Windows: `creationflags=DETACHED_PROCESS |
  CREATE_NEW_PROCESS_GROUP`. Возвращает PID.
- `is_running(pid: int) -> bool` — Linux: `os.kill(pid, 0)`; Windows: `OpenProcess`
  через ctypes (или `tasklist`). Кросс-платформенно.
- `terminate(pid: int) -> None` — мягко/жёстко завершить (SIGTERM/taskkill).

### Реестр прогонов (SQLite `runs`)
Таблица `runs(id, project_id, task_id, pid, cmd, log_file, exit_file,
started_at, finished_at, exit_code, status)`, `status ∈ {running, done, failed}`.
Переживает перезапуск монитора — это и даёт устойчивость.

### Монитор (переработка)
- `start(project, prompt)` → `launch(...)`, запись в `runs` (status=running).
- `refresh()` → по каждому `running`-прогону: если PID мёртв → читать exit_file,
  проставить done/failed + finished_at.
- `sessions()` → объединяет `runs` (liveness/PID) + observer-JSONL (токены/фаза) по
  cwd проекта. Формат ответа API сохраняется (грид «Агенты» не меняется).
- `stop(project, mode)` → `terminate(pid)` активного прогона проекта.
- При старте монитора: не requeue вслепую, а сверить `runs` с реальными PID — живые
  остаются running, мёртвые доводятся до done/failed.

### Диспетчер (переработка)
Поллит очередь; для `queued` задачи запускает detached `claude -p "<text>"` (text —
промпт оркестрации), создаёт `runs`-запись, помечает задачу `running`. По завершении
прогона (refresh) — задача `done`/`failed` по коду выхода.

### Бэкенды
- **local** — detached по описанному. **ssh** — на этот этап **не поддерживаем**
  (remote-PID/detached по ssh сложнее); помечаем как «позже». Текущий ssh-backend
  либо оставляем нетронутым и недоступным для detached, либо прячем в UI. Решение:
  в UI форме проекта временно оставить только `local` (ssh — отдельная задача).

### Удаляемое/ретайр
PTY-слой (`pty_process.py`, PTY-ветки в `backends/local.py`,`ssh.py`) и
`monitor.send/transcript/capture` (чат-уровень) — ретайрятся. Observer/jsonl —
остаются (их читаем для токенов/фаз).

## Совместимость и тесты

Большой churn: ~300 тестов завязаны на `FakeBackends`/PTY. План:
- Ввести абстракцию «runner» (launch/is_running/terminate) с `FakeRunner` для тестов
  вместо `FakeBackends`.
- Переписать `test_monitor.py`/`test_dispatcher.py`/`test_api.py` под runs-модель
  (статусы из PID/exit, а не PTY).
- Сохранить формат `/api/sessions` и `/ws/sessions`, чтобы фронт «Агенты» не менять.
- Observer-тесты (`test_observer.py`, `jsonl_cursor`) остаются.

## Открытые вопросы (решить в плане)
- Точный флаг запуска: `claude -p "<prompt>"` vs файл промпта (длинные промпты).
- Где хранить log/exit файлы: `<project>/.agentmon/runs/<run_id>.{log,exit}`.
- Политика одновременности: один активный прогон на проект (как сейчас) или N.

## Границы
- ssh-backend detached — отдельная будущая задача.
- Не трогаем страницы-мастера (#1-#4) и контент окружения.

## Тестирование (цели)
- `runner_detached`: launch реально запускает short-lived процесс (напр. `python -c`),
  is_running True→False после завершения, exit_file содержит код; terminate убивает.
- `run_wrapper`: пишет код выхода дочернего процесса.
- Монитор: running-прогон с живым фейковым PID → sessions показывает running; мёртвый
  → done/failed по exit_file; restart-resilience (новый монитор видит прежние runs).
- Диспетчер: queued → launch → running; завершение → done/failed.
- API `/api/sessions` формат сохранён; полный набор зелёный.

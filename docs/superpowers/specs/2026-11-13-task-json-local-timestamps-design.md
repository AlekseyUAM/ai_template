# Локальные ISO-даты в task.json

Дата: 2026-11-13

## Проблема

Отметки времени в `tasks/task#<id>/task.json` — epoch-числа (`time.time()`)
либо `null`. Человеку, открывшему файл, они ничего не говорят: чтобы понять
время, нужен переводчик. Кроме того, `created_at` при заведении задачи через
монитор вообще не заполняется — в `TaskRepo.add` не передаётся `now`, и поле
остаётся `null`.

## Цель

Все даты в `task.json` — человекочитаемые строки ISO 8601 в часовом поясе ОС,
где выполняется пишущий процесс, с числовым смещением:

```json
"created_at": "2026-11-13T11:37:18+03:00"
```

`null` остаётся `null`. Формат БД, API и UI не меняется.

## Решения, принятые при обсуждении

- **ISO только в файле.** База хранит epoch-числа как раньше: на них завязаны
  арифметика `tree_api` (`elapsed_min`), `start.js` (`new Date(sec*1000)`,
  `fmtElapsed`) и типы колонок `DOUBLE PRECISION`/`REAL`. Перевод — на границе
  `task.json → БД`.
- **Часовой пояс — пишущего процесса.** `task_status.py` и создание задачи
  пишут `datetime.now().astimezone()`. Для local-бэкенда это ОС монитора; для
  docker/ssh — ОС контейнера/удалённого хоста. Проброс TZ монитора в окружение
  агента (env/ssh/docker) отклонён на этом этапе: дороже по числу затронутых
  файлов, а формат от него не зависит и может быть добавлен позже.
- **Старые файлы читаются.** Читатели принимают и ISO-строки, и epoch-числа.
  Существующие `task.json` не переписываются разово: при следующей записи
  `task_status.py` автоматически приводит числовые даты к ISO.
- **`created_at` заполняется при создании задачи** — заодно закрывается
  пустое поле в свежих файлах.

## Формат

- ISO 8601, точность до секунд: `YYYY-MM-DDTHH:MM:SS+HH:MM` (для UTC-ОС —
  `+00:00`; `Z` не пишем).
- Поля: `created_at`, `started_at`, `finished_at`;
  `stages[].started_at`, `stages[].finished_at`;
  `db_update.started_at`, `db_update.finished_at` (когда `db_update` есть).
- Невалидная/отсутствующая дата — `null`.

## Изменения по слоям

### Новый `app/src/agentmon/env/timefmt.py`

- `to_local_iso(ts) -> str | None` — epoch-секунды → ISO в локальном поясе
  (`datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")`).
- `parse_ts(value) -> float | None` — ISO-строка (`+03:00`, `Z`, `+0000`),
  число или числовая строка → epoch-секунды; `None`/мусор → `None`.
  Исключений не бросает.

### Создание задачи — `env/task_api2.py`

- В `TaskRepo.add(...)` передавать `now=time.time()` — `created_at` попадает
  в БД (числом) и оттуда в файл.
- При сборке `task_data` для `task.json` конвертировать `created_at`,
  `started_at`, `finished_at` и даты всех этапов через `to_local_iso`.
- `db_update_json` в файле остаётся как есть (при создании `null`).

### Оркестратор — `template/.claude/tools/task_status.py` (standalone)

- `_now_iso()` = `datetime.now().astimezone().isoformat(timespec="seconds")`.
- Заменяет `time.time()` во всех записываемых в файл датах: тайминги этапа,
  `started_at`/`finished_at` задачи, `db_update`.
- `time.time()` остаётся только для проверки свежести lock-файла
  (`STALE_LOCK_SECONDS`) — это не данные task.json.
- Перед записью числовые даты в уже существующем файле нормализуются в ISO:
  старые файлы с epoch сходятся к новому формату без отдельной миграции.
- Логика гейтов и `iteration` не меняется: там только проверки на `None`.

### Синхронизация файла в БД — `env/task_sync.py`

- `started_at`/`finished_at` задачи — `parse_ts` перед записью в колонки.
- В `_apply_stage_timings` нормализовать `started_at`/`finished_at` каждого
  этапа через `parse_ts` до сравнений с `prev` (там числа из БД) и фолбэка
  `now` (число).
- `db_update`: конвертировать `started_at`/`finished_at` в числа перед
  `json.dumps` в `db_update_json`; прочие ключи словаря сохранять.
- Невалидная строка → `None`: фолбэк для `running/done/failed` этапов
  проставит `now`, как и сегодня.

### Не меняется

- `env/task_json.py` (approve: только `approved`/`status`), `env/tree_api.py`,
  `env/stack_api.py`, `app/web/start.js`.
- `env/task_schema.py` — файловый legacy-путь (`create_task`, `TaskSpec`) не
  используется монитором; его epoch-семантика и тесты остаются.
- `benchmark/tasks/*/task.json` — исторические снимки, валидны как есть.

## Совместимость и раскатка

- Старые task.json (epoch/`null`) читаются без ошибок; новая запись поля
  переводит его в ISO.
- Существующим проектам нужен `update-env`, чтобы получить новый
  `template/.claude/tools/task_status.py`; монитор — перезапуск, чтобы
  подхватить новый Python-код.
- В PG строка в `DOUBLE PRECISION` не попадёт: `task_sync` кладёт только
  число или `None`.

## Тесты

- `app/tests/env/test_task_status_cli.py` — даты этапов/задачи/`db_update`:
  строки ISO, есть смещение, `finished >= started` после парсинга.
- `app/tests/env/test_task_sync.py` — ISO с `+03:00` и `Z` конвертируются в
  числа в БД (task-level, этапы, `db_update`); mixed epoch/ISO; мусор → `None`;
  отсутствие дрейфа времени между синками.
- `app/tests/env/test_timefmt.py` — прямой разбор/форматирование, границы.
- `app/tests/env/test_task_api2.py` — `created_at` в task.json — ISO со
  смещением, в БД — число.
- Старые тесты с epoch-фикстурами должны пройти без изменений (обратная
  совместимость).
- Полный прогон: `python -m pytest app/tests -q`.

## Вне области

- Изменение формата дат в БД/API/UI.
- Переписывание исторических `benchmark/tasks/*/task.json`.
- Проброс TZ ОС монитора в агенты на docker/ssh.

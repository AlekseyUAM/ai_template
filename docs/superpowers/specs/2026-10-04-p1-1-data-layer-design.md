# P1.1 — Слой данных (PostgreSQL) — дизайн

Дата: 2026-10-04
Статус: утверждён (Фаза 1; пользователь одобрил спеки/планы всех задач фазы заранее)

## Контекст

Фаза 1 переносит хранение проектов/задач/MCP/стеков/прогонов во внутреннюю БД
(**PostgreSQL**). P1.1 — фундамент: слой данных и схема, на которых строятся P1.2-P1.6.

Решения Фазы 1 (из обсуждения):
- Postgres — метаданные/статусы; файлы на диске — артефакты этапов (`ANALYZE.md`…) и
  выгрузки cf/cfe.
- Задачи одного проекта выполняются последовательно (project-lock; в P1.6).
- UI — vanilla JS; Postgres — в Docker нами.

## Инженерный дефолт: dual-dialect адаптер

Чтобы продуктовое хранилище было PostgreSQL, а тест-сьют оставался быстрым и не
требовал поднятого Postgres/psycopg:

- Слой данных работает через тонкий адаптер, поддерживающий **sqlite** (по умолчанию
  для тестов и локальной разработки) и **postgresql** (продукт, драйвер `psycopg`
  v3). Схема переносимая; различия диалектов локализованы (автоинкрементный PK в DDL,
  трансляция плейсхолдеров `?`→`%s`).
- DSN задаётся переменной `AGENTMON_DSN`: `postgresql://user:pass@host:5432/db` →
  Postgres; иначе путь/`sqlite://…` → sqlite-файл (дефолт для обратной совместимости).
- Продукт запускается с Postgres (docker-compose, см. ниже). Тесты — на sqlite в
  tmp/in-memory, без Docker и без psycopg.
- `psycopg[binary]` — необязательная зависимость (нужна только при postgres-DSN).

## Компоненты (`app/src/agentmon/store/`)

- `db.py` — `connect(dsn) -> Db`. `Db`:
  - `.dialect` ∈ {"sqlite","postgres"}.
  - `.execute(sql, params=())` — DML; транслирует `?`→`%s` для postgres; commit по месту.
  - `.query(sql, params=()) -> list[dict]` — SELECT, строки как dict.
  - `.one(sql, params=()) -> dict|None`.
  - `.autopk()` — фрагмент DDL первичного ключа-автоинкремента для диалекта
    (sqlite: `INTEGER PRIMARY KEY AUTOINCREMENT`; postgres: `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`).
  - `.returning_id(...)` — вставка с возвратом id (sqlite: lastrowid; postgres: `RETURNING id`).
  - `.close()`.
- `schema.py` — `init_schema(db)` создаёт таблицы (идемпотентно, `IF NOT EXISTS`),
  переносимо через `db.autopk()`.
- Репозитории: `projects.py`, `mcp.py`, `tasks.py`, `stacks.py`, `runs.py` — классы с
  CRUD поверх `Db`.

### Схема (переносимая)

- `projects(id, name UNIQUE, path UNIQUE, identifier, email, platform_dir,
  platform_version, db_kind, db_connection, web_publication, env_version, created_at)`.
- `mcp_servers(id, name UNIQUE, purpose, kind, standard_key, connection_json, port,
  token_env, created_at)` — kind ∈ {standard, custom}.
- `project_mcp(project_id, mcp_id)` — выбранные MCP проекта (многие-ко-многим).
- `tasks(id, project_id, name, goal, plan, constraints, tests, stages_json, status,
  stage, started_at, finished_at, created_at)` — status ∈ {planned, queued, running,
  stopped, awaiting_user, done, failed}; `stage` — текущий этап; `stages_json` —
  конфиг этапов (enabled/subagent/artifact/gate/approved/status/changed_files).
- `stacks(id, name, status, created_at)` — status ∈ {idle, running, stopped}.
- `stack_items(id, stack_id, task_id, position)`.
- `runs(id, project_id, task_id, pid, log_file, exit_file, status, started_at,
  finished_at, exit_code)` — переносит текущий `run_store`.

### Деплой Postgres

- `deploy/postgres/docker-compose.yml` — сервис `postgres:16` на `127.0.0.1:5432`,
  volume, env (POSTGRES_USER/PASSWORD/DB).
- Документация: как поднять (`docker compose up -d`) и выставить `AGENTMON_DSN`.

## Границы P1.1

- Только слой данных + схема + репозитории + адаптер + compose Postgres.
- Старые `registry`/`queue`/`run_store` (sqlite) НЕ удаляются в P1.1 — их потребители
  (monitor/dispatcher/api/UI) переключатся на новые репозитории в P1.3-P1.6. Это
  держит сьют зелёным по ходу миграции.
- UI, мастер, стеки, справочники — последующие подпроекты.

## Тестирование

- `db.py`: sqlite-коннект; `?`-плейсхолдеры; `returning_id` возвращает id; `query`
  отдаёт dict; postgres-ветка — юнит-тест трансляции плейсхолдеров без живого сервера.
- `schema.py`: `init_schema` создаёт все таблицы идемпотентно (повторный вызов ок).
- Репозитории: CRUD на sqlite tmp — создать/прочитать/обновить/удалить/список для
  projects, mcp (+project_mcp), tasks, stacks (+items, reorder), runs.
- (Опц.) интеграционный тест на Postgres — маркирован, пропускается если нет
  `AGENTMON_TEST_DSN`/psycopg.
- Полный существующий набор остаётся зелёным (старые модули не тронуты).

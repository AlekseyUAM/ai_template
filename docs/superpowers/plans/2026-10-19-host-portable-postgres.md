# Портативная PostgreSQL на хосте (AI1C_PG_MODE=host) — План

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Дать `bootstrap.py` возможность развернуть PostgreSQL **портативно на хосте** (скачать zip-сборку, initdb, pg_ctl, создать роль/БД) — без Docker и админ-прав, для Windows. Настройка `AI1C_PG_MODE=host|docker`, дефолт `host`. docker-путь и SQLite-фолбэк сохраняются.

**Architecture:** Новый stdlib-модуль `pg_portable.py` (корень репо, импортируется bootstrap.py и run.py) со всем портативным-PG слоем; ввод-вывод (download/extract/run) инъектируется → юнит-тесты без сети и реальной PG. bootstrap ветвится по `AI1C_PG_MODE`; run.py в host-режиме монитора поднимает портативную PG перед стартом.

**Tech Stack:** Python stdlib (urllib, zipfile, subprocess), pytest. Живой прогон (Windows) — за пользователем; здесь только инъекции + юниты.

## Global Constraints
- `pg_portable.py`/`bootstrap.py`/`run.py` — **stdlib-only** (системный python, вне venv). Никаких импортов из agentmon.
- **Регрессии нет**: docker-PG путь (`AI1C_PG_MODE=docker`), SQLite-фолбэк и `AI1C_MONITOR_MODE` не меняются.
- Весь внешний I/O (скачивание, распаковка, initdb/pg_ctl/psql) через инъектируемые callable — тесты НЕ ходят в сеть и НЕ запускают реальную PG.
- Идемпотентность: повторный bootstrap/run переиспользует бинарники/datadir/роль/БД.
- Данные/бинарники в `.ai1c/` (уже в .gitignore). Слушать только 127.0.0.1, auth trust.
- Тесты из `app/`: `-k "not install_stops_on_dump_error"` для быстрого полного прогона. Тесты импортируют корневые модули через sys.path (как существующие).
- Русские docstring; коммиты атомарные в master после двухстадийного ревью.

## Файлы
- `pg_portable.py` — новый (корень).
- `bootstrap.py` — ветка AI1C_PG_MODE + env_file_contents.
- `run.py` — ensure_host_pg + вызов в host-режиме.
- `.ai1c.env.example`, `docs/DEPLOY-DOCKER.md`.
- Тесты: `app/tests/test_pg_portable.py`, `app/tests/test_bootstrap_env.py`, `app/tests/test_run_launcher.py`.

---

## Task 1: `pg_portable.py` — ядро портативной PG

**Files:** Create `pg_portable.py`; Test `app/tests/test_pg_portable.py`.

**Interfaces (stdlib, всё I/O инъектируемо):**
- Константы: `PG_VERSION` (напр. `"16.4-1"`), `EDB_BASE_URL`, шаблоны имён архива (windows-x64/linux-x64/osx), `PG_DIR=.ai1c/pg`, `PGDATA=.ai1c/pgdata`, `SUPERUSER="postgres"`, DB/role `ai1c`.
- `binaries_url(system: str, arch: str) -> str`.
- `ensure_binaries(root, *, download, extract) -> str` (bin dir; скип если `bin/initdb*` есть).
- `initdb(bin_dir, datadir, *, run)` (скип если `datadir/PG_VERSION` есть; `-A trust -U postgres --encoding=UTF8`).
- `start(bin_dir, datadir, port, logfile, *, run)` (`pg_ctl … -o "-p <port> -h 127.0.0.1" -w start`).
- `status(bin_dir, datadir, *, run) -> bool`; `stop(bin_dir, datadir, *, run)`.
- `ensure_role_db(bin_dir, port, *, user, password, db, run)` (идемпотентно).
- `dsn(port, *, user="ai1c", password="ai1c", db="ai1c") -> str`.
- `provision(root, *, port=None, download, run, extract=...) -> str` (оркестрация, идемпотентная; порт из `.ai1c/pgdata/ai1c.port` или free_port — вынести `free_port` сюда или продублировать stdlib).

**Steps:**
- [ ] Step 1: платформа/URL + константы + `dsn` + `free_port`/порт-файл.
- [ ] Step 2: `ensure_binaries` (download+extract, идемпотентно, chmod на posix).
- [ ] Step 3: `initdb`/`start`/`status`/`stop`/`ensure_role_db` (argv через инъект-run; идемпотентность).
- [ ] Step 4: `provision` (оркестрация: binaries→initdb→start→role_db→dsn; переиспользование).
- [ ] Step 5: Тесты с фейк-download/extract/run: URL по платформам; argv каждой команды; скип при наличии; dsn; provision happy-path + повторный (идемпотентный); НИ сети, НИ реального pg.

**Verification:** `… pytest tests/test_pg_portable.py -v`; полный фильтрованный без регрессий.

---

## Task 2: `bootstrap.py` — ветка AI1C_PG_MODE + SQLite-фолбэк

**Files:** Modify `bootstrap.py`; Test `app/tests/test_bootstrap_env.py` (+ возможно новый bootstrap-тест).

**Interfaces:**
- `setup_database()`: читать `AI1C_PG_MODE` (env, дефолт `host`). `docker` → текущее. `host` → `pg_portable.provision(ROOT, download=..., run=...)`; при исключении/сбое — `warn` + SQLite-путь (вернуть sqlite DSN/путь, как сейчас при отсутствии docker). Поставить `psycopg[binary]` при PG-DSN.
- `env_file_contents(dsn, db, monitor_mode="host", pg_mode="host")` — добавить `AI1C_PG_MODE=<pg_mode>`; `write_env` прокинуть выбранный pg_mode.

**Steps:**
- [ ] Step 1: ветвление `setup_database` по AI1C_PG_MODE (host=provision+fallback, docker=как есть).
- [ ] Step 2: `env_file_contents`/`write_env` + `AI1C_PG_MODE`.
- [ ] Step 3: Тесты: host → provision(мок) → его DSN; provision бросил → SQLite-фолбэк + warn; docker → старый путь (мок compose); `env_file_contents` содержит `AI1C_PG_MODE=host`; round-trip-parse.

**Verification:** `… pytest tests/test_bootstrap_env.py -v`; полный фильтрованный.

---

## Task 3: `run.py` — поднять портативную PG в host-режиме монитора

**Files:** Modify `run.py`; Test `app/tests/test_run_launcher.py`.

**Interfaces:** `ensure_host_pg(env, *, run=subprocess.run) -> None` — если `resolve `AI1C_PG_MODE`(env, дефолт host)==host И существует `.ai1c/pgdata`: `pg_portable.status`→при простое `pg_portable.start` (bin dir из `.ai1c/pg`). Ошибку логировать, не прерывать. В `main()` host-ветке монитора вызвать `ensure_host_pg(env)` перед запуском. docker-режим монитора / pg_mode!=host / нет pgdata — ничего.

**Steps:**
- [ ] Step 1: `ensure_host_pg` (stdlib, инъекция run; импорт pg_portable).
- [ ] Step 2: вызвать в host-ветке `main()` перед `os.execve`/subprocess; host-инвариант прочего кода сохранить.
- [ ] Step 3: Тесты: mode host + pgdata есть + PG не запущена → start вызван; запущена → start НЕ вызван; pg_mode=docker / нет pgdata → no-op; ошибка start не прерывает; docker-режim монитора не зовёт ensure_host_pg.

**Verification:** `… pytest tests/test_run_launcher.py -v`; полный фильтрованный.

---

## Task 4: Документация

**Files:** Modify `.ai1c.env.example`, `docs/DEPLOY-DOCKER.md`.
- [ ] `.ai1c.env.example`: добавить `AI1C_PG_MODE=host` с комментарием (host=портативная PG на хосте, скачивается bootstrap-ом; docker=контейнер ai1c-postgres); пометка «актуально для Windows без Docker».
- [ ] `docs/DEPLOY-DOCKER.md` (или раздел): режимы БД — портативная (host, дефолт) vs docker; где лежит (`.ai1c/pg`, `.ai1c/pgdata`); что процесс долгоживущий, run.py поднимает при старте; SQLite-фолбэк.

**Verification:** полный фильтрованный прогон зелёный.

---

## Финал
- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` зелёный.
- [ ] Финальное ревью (opus): stdlib-only; docker-PG/SQLite/AI1C_MONITOR_MODE не задеты; весь I/O инъектируем (тесты без сети/реальной PG); идемпотентность; фолбэк на SQLite при сбое; явно отражено, что живая проверка на Windows — за пользователем.
- [ ] Коммиты в master по задаче после двухстадийного ревью.

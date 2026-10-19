# Спека: портативная PostgreSQL на хосте (AI1C_PG_MODE=host, без Docker)

Дата: 2026-10-19. Фаза: 3, фича. Для Windows-машин без Docker.

## Контекст и мотивация

Сейчас `bootstrap.py` поднимает PostgreSQL **только через Docker** (`ai1c-postgres`),
иначе откатывается на SQLite. Нужна симметрия: так же, как мы «устанавливаем и
создаём базу в Docker», уметь **установить и создать базу прямо на хосте, без Docker**
— актуально для Windows без Docker.

Решение пользователя: **портативная PostgreSQL** — скачать портативную сборку PG (zip,
без админ-прав и системной установки), `initdb` в каталог проекта, поднять через
`pg_ctl`, создать роль/БД `ai1c`, записать DSN. Самодостаточно и воспроизводимо, как
Docker.

Новая настройка **`AI1C_PG_MODE=host|docker`** (в `.ai1c.env`), **дефолт `host`**
(портативная PG), независима от `AI1C_MONITOR_MODE` (не путать: та — про сам монитор).

> **Важно (ограничение проверки):** живой прогон (особенно на Windows) в этой среде
> невозможен. Весь слой работает через **инъектируемые** `download`/`run`/`opener` →
> полностью покрыт юнит-тестами (команды, флоу, идемпотентность) БЕЗ сети и реальной
> PG. URL/версия EDB вынесены в константы. Живая валидация на Windows — за
> пользователем.

## Текущее состояние

- `bootstrap.py` (stdlib, системный python): `setup_database()` → docker-PG или
  SQLite; `main()` → `write_env(dsn)`; `env_file_contents(dsn, db, mode)` пишет
  `AGENTMON_DSN`/`AGENTMON_DB`/`AI1C_MONITOR_MODE`. `free_port()` есть.
- `run.py` (stdlib): host-режим монитора `os.execve`/subprocess; docker-режим
  `compose up`. Про БД run.py сейчас ничего не делает (docker держит PG сам).
- `.ai1c/` — в `.gitignore` (портативная PG туда и ляжет).
- `deploy/postgres/docker-compose.yml` — docker-PG (остаётся для `AI1C_PG_MODE=docker`).

## Архитектура решения

### Новый модуль `pg_portable.py` (корень репо, stdlib-only)

Импортируется и `bootstrap.py`, и `run.py` (оба — системный python из корня). Весь
ввод-вывод инъектируем.

Константы: `PG_VERSION` (напр. `"16.4-1"`), базовый URL EDB-бинарников, шаблон имени
архива по ОС/арх (windows-x64 / linux-x64 / osx). Каталоги: `.ai1c/pg/<version>/`
(бинарники), `.ai1c/pgdata/` (данные).

Функции:
- `binaries_url(system, arch) -> str` — URL портативного zip под платформу.
- `ensure_binaries(dest, *, download, extract) -> bin_dir` — скачать+распаковать, если
  `bin/initdb[.exe]` ещё нет (идемпотентно); вернуть путь к `bin`.
- `initdb(bin_dir, datadir, *, run) -> None` — `initdb -D <datadir> -U <superuser>
  -A trust --encoding=UTF8` (+ locale); пропустить, если `datadir/PG_VERSION` уже есть.
- `start(bin_dir, datadir, port, logfile, *, run) -> None` — `pg_ctl -D <datadir>
  -o "-p <port> -k '' -h 127.0.0.1" -l <logfile> -w start` (listen только 127.0.0.1).
- `status(bin_dir, datadir, *, run) -> bool` — `pg_ctl -D <datadir> status` → rc 0.
- `stop(bin_dir, datadir, *, run) -> None` — `pg_ctl … stop` (не вызывается
  автоматически; на будущее/CLI).
- `ensure_role_db(bin_dir, port, *, user="ai1c", password="ai1c", db="ai1c", run)` —
  создать роль+БД идемпотентно (psql `DO`/`CREATE ROLE IF NOT EXISTS`-паттерн или
  createuser/createdb с терпимостью к «уже есть»); выставить пароль.
- `dsn(port, *, user="ai1c", password="ai1c", db="ai1c") -> str` →
  `postgresql://ai1c:ai1c@127.0.0.1:<port>/ai1c`.
- `provision(root, *, port=None, download, run, extract=...) -> str` — оркестрация:
  ensure_binaries → initdb(если нет datadir) → start(если не запущен) →
  ensure_role_db → вернуть dsn. Идемпотентно: повторный запуск переиспользует
  существующие бинарники/datadir/порт (порт хранить в `.ai1c/pgdata/ai1c.port` или
  вычислять из запущенного; при отсутствии — `free_port()`).

Аутентификация: `-A trust` на 127.0.0.1 (локальный dev-инструмент; пароль в DSN
игнорируется trust-ом, но DSN держим `ai1c:ai1c` для симметрии с docker). Слушаем
только loopback.

### `bootstrap.py` — ветка AI1C_PG_MODE

- Читать `AI1C_PG_MODE` из окружения (дефолт `host`).
- `setup_database()`:
  - `docker` → текущее поведение (compose `ai1c-postgres`).
  - `host` (дефолт) → `pg_portable.provision(ROOT, download=urllib, run=subprocess.run)`;
    при успехе вернуть портативный DSN. При ЛЮБОМ сбое (нет сети, initdb/pg_ctl
    упал) — `warn(...)` + **фолбэк на SQLite** (setup не должен бриковаться).
  - Поставить драйвер `psycopg[binary]` в venv (как сейчас для docker).
- `write_env`/`env_file_contents` — добавить `AI1C_PG_MODE=<mode>` (+ оставить
  `AI1C_MONITOR_MODE`). Записать выбранный DSN.

### `run.py` — поднять портативную PG перед монитором (host-режим)

- В host-режиме монитора, если `AI1C_PG_MODE=host` и каталог `.ai1c/pgdata` существует:
  перед запуском монитора гарантировать, что портативная PG запущена
  (`pg_portable.status` → при простое `pg_portable.start`). Вынести в тестируемую
  функцию `ensure_host_pg(env)` (stdlib, инъекция run). Ошибку старта логировать, но не
  блокировать (монитор поднимется, БД-операции дадут понятную ошибку).
- docker-режим монитора и `AI1C_PG_MODE=docker`/sqlite — run.py БД не трогает.
- Портативная PG — долгоживущий процесс (как docker unless-stopped); при выходе
  монитора не останавливаем (документируем; остановка — `pg_ctl stop` вручную/CLI).

## Границы (YAGNI)

- Не ставим системную PG и не требуем админ-прав — только портативная сборка.
- Не реализуем автоперезапуск PG после ребута хоста (портативный процесс); `run.py`
  при следующем старте монитора поднимет её снова.
- Linux/macOS поддерживаем в коде (URL есть), но главный таргет — Windows; при
  недоступности портативной сборки — SQLite-фолбэк.
- Миграция данных между docker-PG и портативной PG — вне скоупа (разные базы).
- Пароль/trust: локальный loopback, trust-auth — приемлемо для dev-инструмента.

## Обработка ошибок

- Нет сети/не скачалось/initdb/pg_ctl упал → `warn` + SQLite-фолбэк (bootstrap).
- `run.py`: PG не стартовала → предупреждение, монитор всё равно поднимается.
- Повторный bootstrap/run: идемпотентно (бинарники/datadir/роль/БД не пересоздаём).

## Тестируемость

- `pg_portable`: `binaries_url` по (system,arch); `ensure_binaries` — скип при наличии
  bin, иначе download+extract (фейки); `initdb`/`start`/`status`/`stop`/`ensure_role_db`
  — верные argv через фейк-run; идемпотентность (datadir есть → initdb скип; запущена →
  start скип); `dsn` формат; `provision` — полный флоу на фейках + фолбэк-путь.
- `bootstrap`: `AI1C_PG_MODE=host` → зовёт `pg_portable.provision` (мок) → DSN;
  провал provision → SQLite-фолбэк + warn; `AI1C_PG_MODE=docker` → старое поведение;
  `env_file_contents` содержит `AI1C_PG_MODE`.
- `run.py`: `ensure_host_pg` — при mode=host и наличии pgdata зовёт status→start;
  при docker/sqlite/отсутствии pgdata — ничего; host-режим монитора вызывает её,
  docker-режим — нет; ошибка старта не прерывает запуск.
- Регрессия: docker-PG путь и SQLite-фолбэк, `AI1C_MONITOR_MODE` — без изменений.

## Единицы

- `pg_portable.py` — **новый** (корень, stdlib): весь портативный-PG слой.
- `bootstrap.py` — ветка `AI1C_PG_MODE`; `env_file_contents(+AI1C_PG_MODE)`.
- `run.py` — `ensure_host_pg(env)` + вызов в host-режиме монитора.
- `.ai1c.env.example` — `AI1C_PG_MODE=host` + комментарий (host=портативная PG,
  docker=контейнер); пометка про Windows без Docker.
- `docs/DEPLOY-DOCKER.md` (или новый краткий раздел) — режимы БД: портативная vs docker.
- Тесты: `app/tests/test_pg_portable.py`, обновить `test_bootstrap_env.py`/
  `test_run_launcher.py`.

## Открытые вопросы

Нет. Портативная EDB-сборка PG в `.ai1c/pg`, данные в `.ai1c/pgdata`, trust-auth на
127.0.0.1, `AI1C_PG_MODE=host` по умолчанию, SQLite-фолбэк при сбое, всё через
инъекции (живая проверка на Windows — за пользователем). URL/версия EDB — константы.

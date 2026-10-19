# Спека: монитор в Docker — опциональный режим развёртывания

Дата: 2026-10-19. Фаза: 3 (Удалённый доступ). Третья (последняя) спека серии после
«Provisioner за backend + ssh» и «docker-бэкенд».

## Контекст и мотивация

Завершающий шаг дорожной карты Фазы 3 (`рефакторинг → ssh → docker → монитор`):
упаковать **control plane** (сам AgentMon: FastAPI + БД + PTY агентов + чтение JSONL +
запуск MCP/контейнеров) в Docker — для простого деплоя и многопользовательского
сценария.

**Ключевое требование пользователя:** режим «монитор в Docker» — это **ОПЦИЯ, а не
единственный сценарий**. По умолчанию монитор запускается **как сейчас** (прямо на
хосте через `python run.py` → `python -m agentmon`). Выбор режима — через **`.ai1c.env`**
(единая точка конфигурации, уже используется `run.py`/`bootstrap.py`).

## Текущее состояние (точка отсчёта)

- `run.py` (корень репо): читает `.ai1c.env` в окружение (`load_env`), печатает URL и
  **всегда** запускает хост-режим — `os.execve(venv_python, "-m", "agentmon")`.
- `bootstrap.py`: генерирует `.ai1c.env` (`AGENTMON_DSN`, `AGENTMON_DB`); поднимает
  PostgreSQL в Docker (`deploy/postgres`, контейнер `ai1c-postgres`, публикует на
  `127.0.0.1:<port>`) или SQLite, если докер недоступен.
- `config.py`: `AGENTMON_DSN/DB/HOST/PORT/CLAUDE_CMD/TG_*`. HOST по умолчанию
  `127.0.0.1`, PORT `8765`. Конфиг = только env (файл грузит `run.py`).
- `app/Dockerfile` + `app/docker-compose.yml`: **уже есть** образ `agentmon-debian`
  (debian:12 + python + node + claude CLI + fake-claude) и compose, который запускает
  `python -m agentmon` в контейнере. НО это dev-вариант: env захардкожен, монтируется
  только `app/` (`./:/app`), нет `.ai1c.env`-интеграции, нет docker-сокета, и
  **`template/` внутри не резолвится** (см. ниже).
- Резолвинг путей в пакете: `template/` = `Path(__file__).parents[4] / "template"`
  (из `env/content.py`/`project_checks.py`); web = `parents[2] / "web"` (из `api.py`).
  Это **относительно расположения пакета**, не от CWD.

## Проблемы текущего compose (которые надо закрыть, чтобы режим реально работал)

1. **`template/` не виден в контейнере.** Compose монтирует `./:/app` (контекст
   `app/`), пакет живёт в `/app/src/agentmon`, `parents[4]` = `/` → `template` ищется в
   `/template`, которого нет. → монтировать **корень репо**, а не `app/`.
2. **БД на хосте недостижима из контейнера.** `AGENTMON_DSN` указывает на
   `postgresql://…@127.0.0.1:<port>` (Postgres `ai1c-postgres` на хосте). Внутри
   контейнера `127.0.0.1` — сам контейнер. → в docker-режиме хост DSN переписываем на
   `host.docker.internal` + `extra_hosts: host.docker.internal:host-gateway` (как в
   docker-бэкенде и песочнице).
3. **Нет docker-сокета.** Монитор запускает MCP-контейнеры (`env/mcp_docker.py`) и
   docker-бэкенд (`backends/docker.py`) через CLI `docker`. В контейнере нужен
   `/var/run/docker.sock` (docker-out-of-docker).
4. **Env не из `.ai1c.env`.** Единая точка конфигурации должна управлять и контейнером.

## Архитектура решения

### Переключатель режима — `.ai1c.env`

Новый ключ `AI1C_MONITOR_MODE=host|docker` (по умолчанию `host`). `bootstrap.py` пишет
`AI1C_MONITOR_MODE=host` в `.ai1c.env`. Пользователь меняет на `docker`, чтобы монитор
поднимался в контейнере. Всё остальное (`AGENTMON_DSN/PORT/CLAUDE_CMD/TG_*`) берётся из
того же `.ai1c.env` в обоих режимах.

### `run.py` — выбор режима

Вынести чистые, **stdlib-only** (run.py исполняется системным python до venv) функции,
пригодные для юнит-тестов:

- `resolve_mode(env) -> "host"|"docker"` — из `AI1C_MONITOR_MODE`, дефолт `host`,
  нераспознанное значение → `host` (с предупреждением).
- `host_plan(env) -> (argv, env)` — как сейчас: `[venv_python, "-m", "agentmon", *extra]`.
- `docker_env(env) -> dict` — окружение для compose: копия env, где в `AGENTMON_DSN`
  loopback-хост (`127.0.0.1`/`localhost`) заменён на `host.docker.internal` (только для
  передачи в контейнер; файл `.ai1c.env` не трогаем). SQLite-DSN не трогаем (он будет в
  примонтированном volume).
- `docker_plan(env) -> (argv, env)` — `["docker","compose","-f",<app/docker-compose.yml>,
  "up","--build"]` + `docker_env`. Ctrl+C → `compose` получает SIGINT и штатно гасит
  (down не делаем автоматически; контейнер `restart: unless-stopped` переживёт).
- `main()`: `load_env`; `mode = resolve_mode`; host → `execve`/subprocess как сейчас;
  docker → запустить `docker_plan` (блокирующе, стримит логи compose).

Инъекция `runner`/`which` для тестов (проверяем argv и переписанный DSN без докера).

### compose/Dockerfile — рабочий опциональный образ

`app/docker-compose.yml`:
- `environment:` берёт значения из окружения процесса (его наполнит `run.py` из
  `.ai1c.env`) через интерполяцию `${AGENTMON_DSN}`, `${AGENTMON_PORT:-8765}`,
  `${AGENTMON_CLAUDE_CMD:-claude --dangerously-skip-permissions .}`, `${AGENTMON_TG_*}`;
  фиксированно `AGENTMON_HOST=0.0.0.0` (бинд на все интерфейсы), `IS_SANDBOX=1`.
- `extra_hosts: ["host.docker.internal:host-gateway"]`.
- `volumes:`
  - **корень репо** → `/opt/ai1c` (чтобы `template/`, `app/`, `web/` резолвились);
    `working_dir: /opt/ai1c/app`, `PYTHONPATH: /opt/ai1c/app/src`;
  - `/var/run/docker.sock:/var/run/docker.sock` (DinD для MCP/docker-бэкенда);
  - именованный `agentmon_claude:/root/.claude` (auth агента, переживает рестарт);
  - для SQLite-режима — каталог БД на volume (как сейчас `agentmon_data:/data`),
    если DSN sqlite.
- `ports: "${AGENTMON_PORT:-8765}:8765"`; `command: ["python","-m","agentmon"]`;
  `restart: unless-stopped`.

`app/Dockerfile`: по сути уже готов (python+node+claude+deps). Правки минимальны:
убедиться, что он не COPY-ит код (код монтируется), оставить установку зависимостей по
`requirements.txt`; `WORKDIR`/`PYTHONPATH` задаёт compose. (Если `requirements.txt`
отстал от `pyproject.toml` — синхронизировать зависимости.)

### Граница host-режима (регрессия)

`AI1C_MONITOR_MODE` не задан или `host` → поведение `run.py` **байт-в-байт как сейчас**.
Контейнер не трогается. Это инвариант.

## Поток (docker-режим)

1. `python bootstrap.py` → `.ai1c.env` c `AGENTMON_DSN=…` и `AI1C_MONITOR_MODE=host`.
2. Пользователь правит `.ai1c.env`: `AI1C_MONITOR_MODE=docker`.
3. `python run.py` → `resolve_mode=docker` → `docker_env` (DSN loopback→
   host.docker.internal) → `docker compose -f app/docker-compose.yml up --build`.
4. Контейнер: `python -m agentmon`, HOST=0.0.0.0, PORT из env; `template/`/`web/`
   видны через `/opt/ai1c`; БД — Postgres хоста через `host.docker.internal` (или
   SQLite на volume); MCP/docker-бэкенд — через примонтированный docker.sock.
5. UI на `http://127.0.0.1:<port>` (проброс порта). Авторизация claude:
   `docker compose exec agentmon claude` (как в текущем доке compose).

## Границы (YAGNI)

- Не меняем execution-модель: в docker-мониторе `local`-проекты исполняются ВНУТРИ
  контейнера монитора (claude в образе) — для реального 1С используют ssh/docker
  execution-бэкенды. Это документируем, нового кода нет.
- Не поднимаем Postgres внутри compose монитора (остаётся отдельный `ai1c-postgres` из
  bootstrap; тянемся к нему через host.docker.internal). Общая docker-сеть — возможная
  будущая оптимизация.
- Windows docker-режим не прорабатываем (host-режим на Windows как сейчас);
  `host.docker.internal` на Docker Desktop работает и так.
- Не добавляем push образа в реестр / CI.

## Тестируемость

- `run.py`: чистые функции `resolve_mode`/`docker_env`/`host_plan`/`docker_plan`
  тестируются без докера (инъекция env; проверяем argv, выбор режима, DSN-rewrite,
  дефолт host, нераспознанный режим→host). Тест импортирует `run.py` из корня репо
  (как ssh/docker-тесты уже делают sys.path-вставки).
- `bootstrap.py`: вынести `env_file_contents(dsn, db, mode)` (чистая), проверить, что
  пишет `AI1C_MONITOR_MODE=host` и DSN/DB.
- compose: тест читает `app/docker-compose.yml` и проверяет ключевую обвязку
  (extra_hosts host-gateway, монтаж docker.sock, монтаж корня репо `/opt/ai1c`,
  PYTHONPATH, AGENTMON_HOST=0.0.0.0, интерполяция `${AGENTMON_DSN}`/порт). Парс —
  текстом или `yaml` если доступен; без запуска докера.
- Регрессия host-режима: `resolve_mode({})=="host"`, `host_plan` даёт прежний argv.

## Единицы (модульность)

- `run.py` — `resolve_mode`/`host_plan`/`docker_env`/`docker_plan` + диспетчеризация в
  `main`.
- `bootstrap.py` — `env_file_contents(...)` + `AI1C_MONITOR_MODE=host` в `write_env`.
- `app/docker-compose.yml` — env из `.ai1c.env`, extra_hosts, docker.sock, монтаж корня
  репо, PYTHONPATH/workdir, HOST=0.0.0.0, порт из env.
- `app/Dockerfile` — минимальные правки (deps-синхрон при необходимости).
- `app/src/agentmon/config.py` — без изменений логики; возможно docstring про режим.
- `docs/PHASES.md` — «Упаковка монитора в Docker» → «Реализовано».
- `docs/DEPLOY-DOCKER.md` (новый, краткий) — как включить docker-режим, что
  монтируется, авторизация claude, Postgres через host.docker.internal.
- Тесты: `app/tests/test_run_launcher.py`, `app/tests/test_bootstrap_env.py`,
  `app/tests/test_monitor_compose.py`.

## Открытые вопросы

Нет. Переключатель `.ai1c.env::AI1C_MONITOR_MODE` (дефолт host), DSN loopback→
host.docker.internal в docker-режиме, монтаж корня репо + docker.sock, Postgres через
host.docker.internal — зафиксированы по образцу docker-бэкенда/песочницы.

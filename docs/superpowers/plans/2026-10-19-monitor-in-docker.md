# Монитор в Docker (опциональный режим) — План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Сделать запуск монитора (control plane AgentMon) в Docker **опциональным режимом**, управляемым `.ai1c.env` (`AI1C_MONITOR_MODE=host|docker`, по умолчанию `host`). Host-режим по поведению не меняется. Docker-режим реально работает: `template/`/`web/` видны, БД хоста достижима, MCP/docker-бэкенд работают через примонтированный docker-сокет.

**Architecture:** `run.py` (stdlib, исполняется системным python) получает чистые функции выбора режима и построения команд запуска; host-режим = как сейчас (`-m agentmon` в venv), docker-режим = `docker compose up` с окружением из `.ai1c.env` (DSN loopback→`host.docker.internal`). `app/docker-compose.yml` переписан под единый источник конфигурации (`.ai1c.env`), монтаж корня репо в `/opt/ai1c` (чтобы работала резолвинг-математика путей `parents[4]`/`parents[2]`), `extra_hosts` host-gateway, docker.sock. `bootstrap.py` пишет `AI1C_MONITOR_MODE=host`.

**Tech Stack:** Python 3.10+ (stdlib в run.py/bootstrap.py), docker compose (v2), pytest. Реальный docker в тестах не нужен — проверяем построение команд/окружения/содержимое compose-файла.

## Global Constraints

- **Host-режим не меняется**: при отсутствии `AI1C_MONITOR_MODE` или значении `host` `run.py` ведёт себя байт-в-байт как сейчас (`os.execve`/subprocess → venv `-m agentmon`). Это инвариант, покрыть тестом.
- `run.py` и `bootstrap.py` — **только stdlib** (исполняются системным python до/вне venv). Никаких импортов из `agentmon`.
- Единый источник конфигурации — `.ai1c.env`. Docker-режим не вводит второй конфиг-файл.
- Docker-режим: DSN с loopback-хостом (`127.0.0.1`/`localhost`) переписывается на `host.docker.internal` ТОЛЬКО для окружения контейнера (файл `.ai1c.env` не меняем). SQLite-DSN/путь не переписываем.
- Сеть контейнера: `extra_hosts: host.docker.internal:host-gateway` (как в docker-бэкенде/песочнице). HOST внутри = `0.0.0.0`.
- Монтаж КОРНЯ репо в контейнер (не только `app/`) — иначе `template/` (`parents[4]`) не резолвится.
- Тесты: из `app/` — `/home/uam/projects/ai_template/.venv/bin/python -m pytest -q`. Быстрый полный прогон: добавить `-k "not install_stops_on_dump_error"` (тот тест делает реальный sleep ~900с). Baseline зелёный, не регрессировать.
- Русскоязычные docstring/комментарии в стиле репозитория.
- Коммиты — атомарные по задаче, в локальный `master`, после двухстадийного ревью.

---

## Файловая структура

- `run.py` — **+** `resolve_mode`/`host_plan`/`docker_env`/`docker_plan`; `main()` диспетчеризует режим.
- `bootstrap.py` — **+** `env_file_contents(dsn, db, mode)`; `write_env` пишет `AI1C_MONITOR_MODE=host`.
- `app/docker-compose.yml` — env из `.ai1c.env` через `${...}`, `extra_hosts`, docker.sock, монтаж корня репо `/opt/ai1c`, `PYTHONPATH`/`working_dir`, `AGENTMON_HOST=0.0.0.0`, порт из env.
- `app/Dockerfile` — минимальные правки (без COPY кода; deps по `requirements.txt`, синхрон при необходимости).
- `docs/PHASES.md` — «Упаковка монитора в Docker» → «Реализовано».
- `docs/DEPLOY-DOCKER.md` — **новый**, краткая инструкция.
- Тесты: `app/tests/test_run_launcher.py`, `app/tests/test_bootstrap_env.py`, `app/tests/test_monitor_compose.py`.

---

## Task 1: `run.py` — выбор режима host/docker (чистые функции + тесты)

**Files:** Modify `run.py`; Test `app/tests/test_run_launcher.py`.

**Interfaces (produces, stdlib-only):**
- `resolve_mode(env: dict) -> str` — `env.get("AI1C_MONITOR_MODE","host").strip().lower()`; `"docker"`→`"docker"`; всё иное (включая пусто/мусор) → `"host"` (для мусора — печать предупреждения в stderr).
- `host_plan(env, extra_args) -> (argv, env)` — `([str(venv_python()), "-m", "agentmon", *extra_args], env)` (текущее поведение).
- `docker_env(env) -> dict` — копия env; если `AGENTMON_DSN` начинается с `postgres`/`postgresql` и содержит `@127.0.0.1:` или `@localhost:`, заменить хост на `@host.docker.internal:`. Иначе (sqlite / иной) без изменений. Не мутировать вход.
- `COMPOSE_FILE = ROOT / "app" / "docker-compose.yml"`.
- `docker_plan(env, extra_args) -> (argv, env)` — `(["docker","compose","-f",str(COMPOSE_FILE),"up","--build"], docker_env(env))` (extra_args в compose-режиме игнорируем или прокидываем в `agentmon` через env — игнорируем, зафиксировать в docstring).

**Steps:**
- [ ] Step 1: Реализовать `resolve_mode`/`host_plan`/`docker_env`/`docker_plan` как модульные функции (принимают `env` явно; `venv_python` уже есть).
- [ ] Step 2: Переписать `main()`: `env=dict(os.environ); load_env(env); mode=resolve_mode(env)`. host → как сейчас (`os.execve`/subprocess с `host_plan`). docker → `argv,denv=docker_plan(env,sys.argv[1:])`; печать URL; `subprocess.run(argv, env=denv)` (блокирующе, стримит), `sys.exit(rc)`. Инъекция runner (параметр по умолчанию `subprocess.run`) для тестов — или держать `main` тонким, тестировать чистые функции.
- [ ] Step 3: Тесты (`app/tests/test_run_launcher.py`, импорт `run` из корня репо через sys.path): `resolve_mode` host/docker/default/мусор; `docker_env` переписывает postgres loopback → host.docker.internal, НЕ трогает sqlite и внешний хост; `host_plan` даёт прежний argv; `docker_plan` строит `docker compose -f app/docker-compose.yml up --build` с переписанным env.

**Verification:** `… pytest tests/test_run_launcher.py -v` зелёные; host-argv не изменился.

---

## Task 2: `bootstrap.py` — писать `AI1C_MONITOR_MODE=host` в `.ai1c.env`

**Files:** Modify `bootstrap.py`; Test `app/tests/test_bootstrap_env.py`.

**Interfaces:**
- `env_file_contents(dsn: str, db: str, mode: str = "host") -> str` — чистая функция, возвращает текст `.ai1c.env` (комментарий-заголовок + `AGENTMON_DSN=`/`AGENTMON_DB=`/`AI1C_MONITOR_MODE=` + краткий комментарий про host|docker). `write_env` использует её.

**Steps:**
- [ ] Step 1: Вынести `env_file_contents`; `write_env(dsn)` → пишет `env_file_contents(dsn, str(ROOT/'app'/'agentmon.db'), "host")`. Добавить строку-комментарий, что сменить на `docker` для запуска монитора в контейнере.
- [ ] Step 2: Тест (`app/tests/test_bootstrap_env.py`, импорт `bootstrap` из корня): `env_file_contents(...)` содержит `AGENTMON_DSN=`, `AGENTMON_DB=`, `AI1C_MONITOR_MODE=host`; идемпотентно-разумный формат (KEY=value, парсится `run.load_env`).

**Verification:** `… pytest tests/test_bootstrap_env.py -v`.

---

## Task 3: `app/docker-compose.yml` (+ Dockerfile) — рабочий опциональный образ

**Files:** Modify `app/docker-compose.yml`, `app/Dockerfile`; Test `app/tests/test_monitor_compose.py`.

**Interfaces (compose service `agentmon`):**
- `environment:`: `AGENTMON_HOST: "0.0.0.0"`, `AGENTMON_PORT: "${AGENTMON_PORT:-8765}"`, `AGENTMON_DSN: "${AGENTMON_DSN}"`, `AGENTMON_DB: "${AGENTMON_DB:-/data/agentmon.db}"`, `AGENTMON_CLAUDE_CMD: "${AGENTMON_CLAUDE_CMD:-claude --dangerously-skip-permissions .}"`, `IS_SANDBOX: "1"`, прокинуть `AGENTMON_TG_TOKEN/CHAT_IDS/API_BASE` через `${...:-}`.
- `extra_hosts: ["host.docker.internal:host-gateway"]`.
- `volumes:`: `../:/opt/ai1c` (корень репо), `/var/run/docker.sock:/var/run/docker.sock`, `agentmon_claude:/root/.claude`, `agentmon_data:/data`.
- `working_dir: /opt/ai1c/app`; добавить `PYTHONPATH: /opt/ai1c/app/src` в environment.
- `ports: ["${AGENTMON_PORT:-8765}:8765"]`; `command: ["python","-m","agentmon"]`; `restart: unless-stopped`.
- Dockerfile: не COPY-ить код (монтируется); оставить установку deps; при расхождении синхронизировать `app/requirements.txt` с `pyproject.toml` зависимостями (fastapi, uvicorn[standard], paramiko, psycopg[binary], httpx).

**Steps:**
- [ ] Step 1: Переписать compose под интерфейс выше (env из `${...}`, extra_hosts, docker.sock, монтаж корня, PYTHONPATH/workdir, порт из env).
- [ ] Step 2: Проверить Dockerfile: deps присутствуют (сверить `app/requirements.txt`); убрать возможный COPY кода; EXPOSE оставить.
- [ ] Step 3: Тест (`app/tests/test_monitor_compose.py`): прочитать `app/docker-compose.yml` (yaml если доступен, иначе текст) и утвердить: `extra_hosts` содержит `host.docker.internal:host-gateway`; смонтирован `/var/run/docker.sock`; смонтирован корень репо в `/opt/ai1c`; `working_dir: /opt/ai1c/app`; `PYTHONPATH` = `/opt/ai1c/app/src`; `AGENTMON_HOST` = `0.0.0.0`; `AGENTMON_DSN` интерполируется из `${AGENTMON_DSN}`; порт из `${AGENTMON_PORT...}`.

**Verification:** `… pytest tests/test_monitor_compose.py -v`.

---

## Task 4: Документация (PHASES + DEPLOY-DOCKER)

**Files:** Modify `docs/PHASES.md`; Create `docs/DEPLOY-DOCKER.md`.

**Steps:**
- [ ] Step 1: `docs/PHASES.md`: перенести «Упаковка монитора в Docker» из «Следующих шагов» в «Реализовано» Фазы 3 с описанием: опциональный режим (`AI1C_MONITOR_MODE=docker` в `.ai1c.env`, дефолт host), что монтируется (корень репо, docker.sock, `~/.claude`), Postgres через host.docker.internal; execution local-проектов идёт внутри контейнера монитора (для реального 1С — ssh/docker бэкенды).
- [ ] Step 2: `docs/DEPLOY-DOCKER.md` (кратко, по-русски): как включить (`AI1C_MONITOR_MODE=docker` → `python run.py`), что произойдёт (compose up), авторизация claude (`docker compose exec agentmon claude`), порт/URL, требования (docker, доступный `ai1c-postgres`), и что host-режим остаётся дефолтом.
- [ ] Step 3: (опц.) мелкая проверка-тест, что PHASES упоминает docker-режим монитора (если легко) — иначе пропустить.

**Verification:** `… pytest -q -k "not install_stops_on_dump_error"` — полный прогон зелёный.

---

## Финал

- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` из `app/` — зелёный (регрессия host-режима и всего остального).
- [ ] Финальное ревью всей ветки (opus): инвариант host-режима; корректность DSN-rewrite и compose-обвязки (template/web резолвятся, docker.sock, host-gateway); отсутствие второго конфиг-файла; stdlib-only в run.py/bootstrap.py.
- [ ] Каждая задача — атомарный коммит в локальный `master` после двухстадийного ревью.

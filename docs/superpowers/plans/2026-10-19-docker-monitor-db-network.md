# docker-режим монитора — связь с PG через общую сеть — План

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Починить docker-режим монитора: монитор-контейнер достаёт PostgreSQL через общую сеть `ai1c-net` по `ai1c-postgres:5432`, а не через недостижимый loopback-publish. host-режим не меняется.

**Architecture:** `deploy/postgres` и `app/docker-compose.yml` делят сеть `ai1c-net` (postgres создаёт, монитор присоединяется как external). `run.py::docker_env` переписывает loopback-postgres-DSN → `@ai1c-postgres:5432`; `run.py` идемпотентно создаёт `ai1c-net` перед `compose up`.

**Tech Stack:** Python (stdlib run.py), docker compose, pytest. Без реального docker — инъекция runner + текстовые проверки compose.

## Global Constraints
- **host-режим байт-в-байт**: `docker_host`/host-DSN/host_plan не меняются; loopback publish PG сохранён.
- `run.py` — stdlib.
- Тесты из `app/`: `-k "not install_stops_on_dump_error"` для быстрого полного прогона.
- Русские комментарии; коммиты атомарные в master после двухстадийного ревью.

## Файлы
- `deploy/postgres/docker-compose.yml` — сеть `ai1c-net`.
- `app/docker-compose.yml` — external `ai1c-net` + agentmon в ней.
- `run.py` — `docker_env` rewrite + ensure-network.
- `docs/DEPLOY-DOCKER.md`, `.ai1c.env.example`.
- Тесты: `app/tests/test_run_launcher.py`, `app/tests/test_monitor_compose.py`.

---

## Task 1: `run.py::docker_env` — loopback PG → `ai1c-postgres:5432`

**Files:** Modify `run.py`; Test `app/tests/test_run_launcher.py`.

**Interfaces:** `docker_env(env)` — для `AGENTMON_DSN`, начинающегося с `postgres://`/`postgresql://` и содержащего loopback-authority (`@127.0.0.1:<port>` или `@localhost:<port>`), заменить весь `@<host>:<port>` на `@ai1c-postgres:5432` (userinfo до `@` и путь/`/db` после — сохранить). Не-postgres, не-loopback, отсутствие DSN — без изменений. Вход не мутировать (копия).

**Steps:**
- [ ] Step 1: заменить прежний rewrite (`→ host.docker.internal:<port>`) на `→ ai1c-postgres:5432`. Регекс по `@(127\.0\.0\.1|localhost):\d+` → `@ai1c-postgres:5432` (count=1), только для postgres-DSN.
- [ ] Step 2: обновить существующие docker_env-тесты (ждали host.docker.internal) + добавить: `@127.0.0.1:5433`→`@ai1c-postgres:5432`; `@localhost:5432`→`@ai1c-postgres:5432`; порт действительно становится 5432; внешний хост/sqlite/нет DSN — без изменений; вход не мутирован.

**Verification:** `… pytest tests/test_run_launcher.py -v`; полный фильтрованный без регрессий.

---

## Task 2: compose `ai1c-net` + `run.py` ensure-network

**Files:** Modify `deploy/postgres/docker-compose.yml`, `app/docker-compose.yml`, `run.py`; Test `app/tests/test_monitor_compose.py`, `app/tests/test_run_launcher.py`.

**Interfaces:**
- `deploy/postgres/docker-compose.yml`: top-level `networks: { ai1c-net: { name: ai1c-net } }`; `postgres` service → `networks: [ai1c-net]`; publish `127.0.0.1:${AI1C_PG_PORT:-5432}:5432` **оставить**.
- `app/docker-compose.yml`: top-level `networks: { ai1c-net: { name: ai1c-net, external: true } }`; `agentmon` → `networks: [ai1c-net]`; `extra_hosts` оставить.
- `run.py` docker-режим: перед `docker compose up` выполнить идемпотентный `docker network create ai1c-net` (подавить ошибку, если уже есть). Вынести в тестируемую форму: напр. `docker_prep_cmds() -> list[list[str]]` возвращает `[["docker","network","create","ai1c-net"]]`, которые `main` выполняет (ошибку игнорирует) перед `compose up`. Либо отдельная функция, которую `main` зовёт; важно — тестируемо и ошибка создания существующей сети не фатальна.

**Steps:**
- [ ] Step 1: правки обоих compose (сеть + подключения; publish PG сохранён).
- [ ] Step 2: `run.py` — ensure-network перед compose up (идемпотентно, ошибка не фатальна), тестируемая форма.
- [ ] Step 3: Тесты: compose-текст — `app/docker-compose.yml` объявляет external `ai1c-net` и agentmon в ней; `deploy/postgres` — `ai1c-net` + postgres в ней + loopback publish сохранён. run.py — ensure-network в docker-подготовке; host-режим её НЕ вызывает.

**Verification:** `… pytest tests/test_monitor_compose.py tests/test_run_launcher.py -v`; полный фильтрованный.

---

## Task 3: Документация

**Files:** Modify `docs/DEPLOY-DOCKER.md`, `.ai1c.env.example`.
- [ ] `DEPLOY-DOCKER.md`: в разделе про БД/docker-режим — монитор-контейнер коннектится к PG по общей сети `ai1c-net` (`ai1c-postgres:5432`); сначала `python bootstrap.py` (поднимает `ai1c-postgres` + создаёт сеть); `run.py` досоздаёт сеть идемпотентно.
- [ ] `.ai1c.env.example`: у `AGENTMON_DSN` — комментарий, что в docker-режиме DSN внутри контейнера переписывается автоматически на `ai1c-postgres:5432` (вручную менять не нужно).

**Verification:** полный фильтрованный прогон зелёный.

---

## Финал
- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` зелёный.
- [ ] Финальное ревью (opus): host-режим не задет; docker_env корректно переписывает только loopback-PG; compose-сеть согласована (postgres создаёт, монитор external); ensure-network идемпотентна.
- [ ] Коммиты в master по задаче после двухстадийного ревью.

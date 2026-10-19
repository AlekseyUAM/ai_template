# Спека: docker-режим монитора — связь с PostgreSQL через общую сеть

Дата: 2026-10-19. Фаза: 3, фикс-спека (баг docker-режима монитора).

## Проблема

В `AI1C_MONITOR_MODE=docker` монитор-контейнер **не может достучаться до PostgreSQL**.
`ai1c-postgres` (`deploy/postgres/docker-compose.yml`) публикует порт как
`127.0.0.1:${AI1C_PG_PORT}:5432` — **только на loopback хоста**. `run.py::docker_env`
переписывает DSN `@127.0.0.1:<port>` → `@host.docker.internal:<port>`, но
`host.docker.internal` из контейнера резолвится в **gateway-IP хоста** (напр.
172.17.0.1), а DNAT-правило docker для publish на `127.0.0.1` на трафик к gateway-IP
**не срабатывает** → connection refused.

Не поймали: docker-режим вживую не гоняли; тесты коннект к БД не делают (фейки).

## Решение (общая docker-сеть — «правильный» вариант)

Монитор-контейнер и `ai1c-postgres` подключаются к одной пользовательской сети
`ai1c-net`; монитор ходит к БД по **имени контейнера** `ai1c-postgres:5432`
(внутренний порт контейнера), а не через host-gateway/опубликованный порт.

- **host-режим не меняется**: PG по-прежнему публикует `127.0.0.1:<port>`, монитор на
  хосте коннектится на `127.0.0.1:<port>` (работает). Loopback-publish оставляем.
- **docker-режим**: оба контейнера в `ai1c-net`; DSN в контейнере →
  `postgresql://ai1c:ai1c@ai1c-postgres:5432/ai1c`.

### Детали

1. `deploy/postgres/docker-compose.yml`:
   - объявить сеть `ai1c-net` (`networks: { ai1c-net: { name: ai1c-net } }`);
   - сервис `postgres` подключить к `ai1c-net`;
   - publish `127.0.0.1:${AI1C_PG_PORT}:5432` **оставить** (host-режим).
   `container_name: ai1c-postgres` → в сети резолвится как `ai1c-postgres`.
2. `app/docker-compose.yml` (монитор):
   - объявить сеть `ai1c-net` как **external** (`{ name: ai1c-net, external: true }`);
   - сервис `agentmon` подключить к `ai1c-net`;
   - `extra_hosts: host.docker.internal:host-gateway` **оставить** (нужен для прочих
     ресурсов хоста/MCP, не для БД).
3. `run.py` (docker-режим): перед `docker compose up` идемпотентно гарантировать сеть:
   `docker network create ai1c-net` (подавить ошибку «уже есть»), чтобы external-ссылка
   не падала, даже если `deploy/postgres` ещё не поднимался в этой среде.
4. `run.py::docker_env`: для **postgres-DSN с loopback-хостом** переписывать весь
   authority `@<loopback>:<port>` → `@ai1c-postgres:5432` (имя контейнера + внутренний
   порт), сохраняя userinfo/БД/query. Не-loopback хост и sqlite — не трогаем.
   (Старое правило `→ host.docker.internal:<port>` для DSN заменяется этим.)

### Почему имя контейнера, а не имя сервиса

Через общую **external**-сеть между двумя compose-проектами (`deploy/postgres` и
`app/docker-compose`) имя-алиас сервиса (`postgres`) видно только внутри своего
проекта; кросс-проектно контейнер резолвится по `container_name` → `ai1c-postgres`.
Поэтому хост в DSN — `ai1c-postgres`.

## Границы (YAGNI)

- host-режим и локальный/ssh/docker-бэкенды проектов не трогаем.
- SQLite в docker-режиме вне скоупа (bootstrap при доступном Docker выбирает PG —
  это и есть сценарий docker-режима; sqlite-путь документируем как неподдерживаемый в
  docker-режиме, если всплывёт).
- Внешний (не-loopback) PG в DSN — оставляем как есть (монитор-контейнер идёт к нему
  напрямую, если сеть позволяет).
- Авто-перенастройка `bootstrap.py` под docker-режим — не требуется (сеть создаётся
  compose-ом `deploy/postgres` и/или `run.py`).

## Обработка ошибок / поведение

- Если `ai1c-net` не существует и `deploy/postgres` не поднят — `run.py` создаёт сеть
  (шаг 3), но без запущенного `ai1c-postgres` коннект всё равно упадёт → монитор
  поднимется, но БД-операции дадут ошибку подключения (ожидаемо: сначала `bootstrap`).
- host-режим: без изменений.

## Тестируемость

- `run.py::docker_env`: postgres loopback DSN (`@127.0.0.1:5433`, `@localhost:5432`) →
  `@ai1c-postgres:5432` (порт тоже меняется на 5432!); внешний хост/sqlite/отсутствие
  DSN — без изменений; вход не мутируется. Обновить существующие docker_env-тесты
  (они сейчас ждут host.docker.internal).
- `docker_plan`/`main` docker-ветка: перед `compose up` вызывается `docker network
  create ai1c-net` (идемпотентно) — проверить в тесте построения шагов/инъекцией
  runner.
- compose (текстовый тест `test_monitor_compose.py`): `app/docker-compose.yml`
  объявляет external-сеть `ai1c-net` и `agentmon` к ней подключён; (опц.) тест на
  `deploy/postgres/docker-compose.yml` — сеть `ai1c-net` + postgres в ней + loopback
  publish сохранён.
- Регрессия host-режима: `resolve_mode`/host_plan и host-DSN не меняются.

## Единицы

- `deploy/postgres/docker-compose.yml` — сеть `ai1c-net` + подключение postgres.
- `app/docker-compose.yml` — external-сеть `ai1c-net` + подключение agentmon.
- `run.py` — `docker_env` (loopback PG → `ai1c-postgres:5432`) + ensure-network перед
  `compose up` в docker-режиме.
- `docs/DEPLOY-DOCKER.md` — заметка: docker-режим коннектится к PG по общей сети
  `ai1c-net` (`ai1c-postgres:5432`); сначала `bootstrap.py` (поднимает PG+сеть).
- `.ai1c.env.example` — короткий комментарий у AGENTMON_DSN про docker-режим (DSN в
  контейнере переписывается автоматически; менять руками не нужно).
- Тесты: `test_run_launcher.py`, `test_monitor_compose.py`.

## Открытые вопросы

Нет. Общая сеть `ai1c-net`; DSN в контейнере → `ai1c-postgres:5432` (имя контейнера +
внутренний порт); loopback-publish оставлен для host-режима; `run.py` идемпотентно
создаёт сеть перед `compose up`.

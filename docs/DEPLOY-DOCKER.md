# Деплой монитора в Docker

По умолчанию монитор (control plane AgentMon) запускается **на хосте** (`AI1C_MONITOR_MODE=host`).
Docker-режим — опциональный: монитор упаковывается в контейнер, но логика ядра не меняется.

## Как включить

В файле `.ai1c.env` задайте:

```
AI1C_MONITOR_MODE=docker
```

Затем запустите:

```bash
python run.py
```

`run.py` поднимет `docker compose -f app/docker-compose.yml up --build`.
UI будет доступен по адресу `http://127.0.0.1:${AGENTMON_PORT:-8765}`.

Чтобы вернуться на хост-режим — удалите строку или задайте `AI1C_MONITOR_MODE=host`.

## Что монтируется и почему

| Монтирование | Зачем |
|---|---|
| `../:/opt/ai1c` (корень репо) | Монитор резолвит `template/`, `web/` и прочие пути внутри репо |
| `/var/run/docker.sock` | Монитор запускает MCP- и docker-бэкенд-контейнеры |
| том `agentmon_claude` → `/root/.claude` | Авторизация агента (`claude`) переживает рестарт контейнера |
| том `agentmon_data` → `/data` | Данные SQLite, если `AGENTMON_DSN` указывает на SQLite |

`working_dir` внутри контейнера — `/opt/ai1c/app`, `PYTHONPATH=/opt/ai1c/app/src`.

## База данных

Postgres (`ai1c-postgres`) запускается на хосте через `bootstrap.py`.
Из контейнера он доступен как `host.docker.internal` (прописан через `extra_hosts: host.docker.internal:host-gateway`).
`run.py` автоматически переписывает loopback-адрес (`127.0.0.1` / `localhost`) в DSN на `host.docker.internal` перед запуском compose.

SQLite также поддерживается: путь к файлу должен быть внутри тома `agentmon_data` (`/data/...`).

## Авторизация claude

Авторизация сохраняется в именованном томе — вводить токен после каждого рестарта не нужно.
Чтобы авторизоваться (один раз):

```bash
docker compose -f app/docker-compose.yml exec agentmon claude
```

Введите токен по инструкции CLI. Состояние переживает пересборку образа.

## Требования

- Установленный **Docker** + **Docker Compose v2** (`docker compose`, не `docker-compose`).
- Доступный `ai1c-postgres` на хосте (или SQLite-DSN в `AGENTMON_DSN`).

## Execution-модель и бэкенды

`local`-проекты (бэкенд «Локально» в мастере) исполняются **внутри контейнера монитора**.
Для реальной 1С-разработки используйте `ssh`- или `docker`-бэкенды: они исполняют агента
на отдельном хосте или в отдельном контейнере, независимо от контейнера монитора.

## Опциональный Telegram

`httpx` намеренно не включён в дефолтный образ.
Чтобы активировать Telegram-бота в docker-режиме, добавьте строку в `app/requirements.txt`:

```
httpx
```

Затем пересоберите образ:

```bash
docker compose -f app/docker-compose.yml up --build
```

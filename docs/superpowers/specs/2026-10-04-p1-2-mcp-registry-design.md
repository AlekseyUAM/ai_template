# P1.2 — Справочник MCP — дизайн

Дата: 2026-10-04
Статус: утверждён (Фаза 1; спеки/планы фазы одобрены заранее)

## Контекст

Справочник MCP-серверов поверх `McpRepo` (P1.1). Позволяет добавить произвольный MCP
(имя, назначение, подключение-json как в `.mcp`) и стандартные серверы с кнопкой
подъёма в Docker (порт/токен) и логом. Источник требований — `tmp/NOTE.md`.

## Стандартные пресеты

Пять стандартных MCP (расширяем существующий `env/mcp_catalog`):

| id | назначение | тип | подъём |
|----|-----------|-----|--------|
| `1c-md` | запросы к метаданным | **extension** | не Docker: 1С-расширение `deps/mcp_tools_cfe/MCP_Сервер.cfe` (ссылка на скачивание + инструкция) |
| `1c-syntax-checker-mcp` | статический анализ BSL | docker | кнопка подъёма + порт |
| `bsl-platform-context` | справка по методам платформы | docker | кнопка + порт |
| `1c-naparnic` | любые вопросы по 1С | docker | кнопка + порт + токен |
| `code-index` | индексированная кодовая база | docker | кнопка + порт |

Пресет несёт: `id, title/purpose, kind (docker|extension), image, default_port,
needs_token, download` (для extension).

## Компоненты

### `env/mcp_catalog.py` (расширение)
Добавить к `McpSpec`: `purpose`, `kind` ("docker"|"extension"), `needs_token`,
`download` (путь к cfe для extension). Сохранить обратную совместимость
(`build_mcp_json`/`build_compose` не ломать). `1c-md` → kind=extension.

### `mcp_docker.py` (подъём в Docker)
- `launch(name, image, port, *, token_env=None, token=None, run=subprocess.run) -> str`
  — `docker run -d --name <name> -p 127.0.0.1:port:port [-e NAME=token] image`;
  вернуть container id/имя. Инъекция `run` для тестов.
- `status(name, run=subprocess.run) -> str` — running|absent (через `docker inspect`/`ps`).
- `stop(name, run=subprocess.run)` — `docker rm -f <name>`.
- `logs_command(name) -> list` — команда `docker logs -f <name>` для SSE-стрима.
Кросс-платформенно (docker CLI). Ошибки докера — текст в лог.

### API-роутер `env/mcp_api.py` (в create_app)
- `GET /api/mcp` — список (McpRepo).
- `GET /api/mcp/standard` — стандартные пресеты (из каталога).
- `POST /api/mcp` — добавить (custom: name/purpose/connection_json; или standard: по
  `standard_key` — заполнить из пресета, порт/токен из тела).
- `PUT /api/mcp/{id}` / `DELETE /api/mcp/{id}`.
- `POST /api/mcp/{id}/launch` — поднять в Docker; **стримить лог** (SSE:
  `text/event-stream`) — запуск + `docker logs`. Для extension (`1c-md`) — 400/подсказка
  «это расширение, скачайте cfe», без докера.
- `POST /api/mcp/{id}/stop` — остановить контейнер.
- `GET /api/mcp/{id}/download` — отдать `MCP_Сервер.cfe` (FileResponse) для `1c-md`.

### Web-страница «Справочник MCP» (`/mcp`)
Список MCP; форма добавления произвольного (имя/назначение/connection json); кнопки
«добавить стандартный» (пресеты); у docker-MCP — порт (+токен для naparnic) и кнопка
«Поднять» с показом лога (SSE) + «Остановить»; у `1c-md` — ссылка «Скачать расширение».
Тёмная тема GitHub. Ссылка из верхнего меню.

## Границы
- Генерация `.mcp.json` проекта из выбранных MCP — в P1.3 (мастер проекта), используя
  этот справочник. Здесь — только справочник + подъём/лог.
- Реальные docker-образы MCP уточняются при интеграции; подъём тестируется через
  инъекцию `run` (без живого докера).

## Тестирование
- Каталог: 5 пресетов, `1c-md` kind=extension с `download`; остальные kind=docker с
  портом; naparnic needs_token.
- `mcp_docker`: `launch` формирует корректную `docker run`-команду (порт на 127.0.0.1,
  `-e` при токене) через фейковый `run`; `stop`/`status` команды; ошибка докера → текст.
- API: CRUD через McpRepo (на sqlite); `/standard` отдаёт пресеты; `launch` для
  extension → 400; `launch` для docker со фейковым runner → 200/stream начинается;
  download для 1c-md отдаёт файл (или 404 если нет).
- Страница `/mcp` отдаётся (заголовок «Справочник MCP»).
- Полный набор зелёный.

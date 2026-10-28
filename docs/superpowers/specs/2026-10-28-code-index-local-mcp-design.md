# Вид MCP «Индексированная кодовая база (локально)» + переименование docker-вида

Дата: 2026-10-28

## Проблема

Сейчас есть единственный вид MCP для индексатора кода — `code-index`, который
разворачивается только в Docker (кнопка «Развернуть в Docker локально»). Нужен
второй способ: развернуть bsl-indexer **нативно** (без Docker) — скачать готовый
бинарь с GitHub Releases, положить рядом `daemon.toml` и поставить индексатор и
MCP-сервер в автозапуск ОС.

## Цель

1. Переименовать существующий вид в «Индексированная кодовая база (в Docker
   локально)». Обязательные поля — «Каталог кодовой базы» и «Имя проекта».
   Кнопка «Развернуть в Docker локально» (поведение не меняется).
2. Добавить вид «Индексированная кодовая база (локально)». Обязательные поля —
   «Каталог кодовой базы», «Имя проекта», «Каталог code_index», «Порт code_index».
   Кнопка «Развернуть локально» скачивает bsl-indexer под текущую платформу,
   кладёт его в «Каталог code_index», пишет там же `daemon.toml` и ставит в
   автозапуск (под ОС) индексатор и MCP-сервер.

## Решения, принятые при обсуждении

- **ОС автозапуска:** Windows + Linux + macOS.
- **Реализация:** своя, на Python, единообразно (без переиспользования upstream-
  скриптов). Скачивание — через GitHub API; автозапуск — свои per-OS функции.
- **Уровень автозапуска:** user-level (без root/admin). Кнопка регистрирует
  автозапуск **и** сразу стартует оба процесса (не ждём перелогина/ребута).

## Архитектура

Два вида MCP делят **ядро** code-index (`daemon.toml`, строка подключения,
образ/бинарь) и различаются только способом развёртывания.

| | docker-вид (существующий) | локальный вид (новый) |
| --- | --- | --- |
| `standard_key` | `code-index` | `code-index-local` |
| `title` | «Индексированная кодовая база (в Docker локально)» | «Индексированная кодовая база (локально)» |
| `action` | `docker` | `local` |
| `kind` | `docker` | `local` |
| обяз. поля | `catalog_dir`, `project_name` | `catalog_dir`, `project_name`, `code_index_dir`, `port` |
| кнопка | «Развернуть в Docker локально» | «Развернуть локально» |
| запуск | контейнер `bsl-indexer:local` (как сейчас) | нативный бинарь + автозапуск |

`daemon.toml` и `connection` (`http://localhost:<port>/mcp`, шаблон `_HTTP_PORT`)
одинаковы у обоих. Отличается только `path` в `daemon.toml`:

- docker: `path = "/repos/src"` (точка монтирования тома в контейнере),
- локальный: `path = <каталог кодовой базы>` (реальный путь на хосте).

Поэтому генератор обобщается: `_daemon_toml(alias)` → `_daemon_toml(alias, path)`.
`alias` в обоих случаях — имя проекта (источник истины, см.
[docs/mcp/code_index/ALIAS.md](../../mcp/code_index/ALIAS.md)).

### Нативная модель запуска bsl-indexer (два процесса)

По документации upstream (`deps/code-index-mcp/README_EN.md`):

1. **Фоновый daemon** — единственный писатель индекса: `bsl-indexer daemon run`,
   читает список путей из `daemon.toml`, держит `.code-index/index.db`
   актуальным. Требует переменную окружения `CODE_INDEX_HOME`.
2. **MCP-сервер** — read-only клиент: `bsl-indexer serve`, по HTTP на порту
   (`MCP_HTTP_HOST`, `MCP_HTTP_PORT`). Без запущенного daemon инструменты
   отвечают `daemon_offline`.

Оба процесса ставятся в автозапуск с env `CODE_INDEX_HOME=<Каталог code_index>`.

## Компоненты

### 1. Схема БД — `app/src/agentmon/store/schema.py`

- Новая колонка `code_index_dir TEXT` в `mcp_servers` (в `CREATE TABLE` и в
  `_ensure_columns` для миграции существующих БД).
- Переиспользуем существующие `port`, `catalog_dir`, `project_name`.

### 2. Репозиторий — `app/src/agentmon/store/mcp.py`

- Параметр `code_index_dir=None` в `add()`, добавить в `columns`/`params`.

### 3. Виды MCP — `app/src/agentmon/env/mcp_types.py`

- У `code-index`: сменить `title` на «Индексированная кодовая база (в Docker
  локально)». Поля и `required` без изменений.
- Новый `McpType` `code-index-local`:
  - `title` = «Индексированная кодовая база (локально)»;
  - `fields = ("name", "mcp_name", "purpose", "url", "port", "catalog_dir",
    "project_name", "code_index_dir", "connection")`;
  - `connection_template = _HTTP_PORT`;
  - `defaults = {"mcp_name": "code_index", "url": "localhost", "port": 8005,
    "purpose": <та же строка, что у docker-вида>}` (порт 8005 ≠ docker-8004,
    чтобы при одновременной работе не конфликтовали);
  - `action = "local"`;
  - `required = ("catalog_dir", "project_name", "code_index_dir", "port")`;
  - `field_labels = {"project_name": "Имя проекта (alias репозитория)",
    "code_index_dir": "Каталог code_index", "port": "Порт code_index"}`.

### 4. API — `app/src/agentmon/env/mcp_api.py`

- `create_mcp`: читать `code_index_dir`, передавать в `repo.add`.
- `update_mcp`: добавить `"code_index_dir"` в `allowed`.
- Новые маршруты (зеркало docker `launch`/`launch/stream`):
  - `POST /api/mcp/{mid}/deploy-local` — блокирующе, лог целиком;
  - `POST /api/mcp/{mid}/deploy-local/stream` — построчный стрим лога.
  - Оба валидируют, что вид = `code-index-local` и заданы `catalog_dir`,
    `project_name`, `code_index_dir`, `port`; затем вызывают оркестратор (ниже).

### 5. Скачивание релиза — `app/src/agentmon/env/code_index_release.py` (новый)

- `host_asset_key() -> str | None` — по `sys.platform` + `platform.machine()`
  возвращает маркеры нужного ассета или `None` (неподдерживаемая платформа).
  Поддерживаем ровно то, что публикует upstream: Windows x64, Linux x64,
  macOS arm64.
- `resolve_asset(release_json, markers) -> (name, url)` — из JSON
  `releases/latest` выбирает ассет `bsl-indexer` под платформу. Чистая функция
  (тестируется на фикстуре JSON).
- `download_binary(code_index_dir, *, fetch=..., runner=...) -> Path` —
  скачать архив (`releases/latest` через GitHub API), распаковать (`.zip`/
  `.tar.gz`) в «Каталог code_index», вернуть путь к исполняемому `bsl-indexer`
  (на Windows — `.exe`), выставить +x на unix. `fetch`/`runner` инъектируются для
  тестов. Стримит прогресс строками.

### 6. Автозапуск — `app/src/agentmon/env/autostart.py` (новый)

- `install_and_start(name, argv, *, env, workdir, run=subprocess.run) ->
  list[str]` — user-level регистрация + немедленный старт; возвращает лог-строки.
  Диспетчеризация по `sys.platform`:
  - **Windows:** `schtasks /Create /SC ONLOGON /TN <name> /TR "<wrapper.cmd>" /F`
    (+ `/Run`). `wrapper.cmd` рядом с бинарём выставляет env и запускает процесс.
  - **Linux:** юнит `~/.config/systemd/user/<name>.service` (`Environment=`,
    `ExecStart=`), `systemctl --user daemon-reload && systemctl --user
    enable --now <name>`. `loginctl enable-linger $USER` — best-effort (чтобы
    переживать ребут без входа), при неудаче — предупреждение в лог, не блокируем.
  - **macOS:** plist `~/Library/LaunchAgents/<name>.plist`
    (`ProgramArguments`, `EnvironmentVariables`, `RunAtLoad`, `KeepAlive`),
    `launchctl load -w <plist>`.
- Имена задач: `ai1c-code-index-daemon-<mid>`, `ai1c-code-index-mcp-<mid>`.
- Генераторы текста юнита/plist/cmd — чистые функции (тестируются без ФС/ОС).

### 7. Оркестратор локального развёртывания — `app/src/agentmon/env/code_index_local.py` (новый)

`_daemon_toml(alias, path)` остаётся в `mcp_docker_recipes.py` (общий генератор) и
импортируется сюда. Оркестратор (`deploy_local(row, *, stream=...)`) выполняет
шаги (стрим лога):

1. `download_binary(code_index_dir)` → путь к `bsl-indexer`.
2. Записать `daemon.toml` в `code_index_dir`: `_daemon_toml(project_name,
   path=catalog_dir)`.
3. `install_and_start("…daemon-<mid>", [bin, "daemon", "run"],
   env={"CODE_INDEX_HOME": code_index_dir})`.
4. `install_and_start("…mcp-<mid>", [bin, "serve"],
   env={"CODE_INDEX_HOME": code_index_dir, "MCP_HTTP_HOST": "127.0.0.1",
   "MCP_HTTP_PORT": str(port)})`.

Повторный запуск идемпотентен: перекачать бинарь, перезаписать `daemon.toml`,
переустановить/перезапустить автозапуск.

### 8. Фронтенд — `app/web/mcp.js`, `app/web/mcp.html`

- `renderTypeFields`: ветка `t.action === "local"` → кнопка «Развернуть локально»
  (`onclick="deployLocalFromForm()"`).
- `showMcpCard`: для `action === "local"` → кнопка «Развернуть локально»
  (`onclick="deployLocal('<id>')"`); показать поля «Каталог code_index».
- `createMcp`: `kind` для `action === "local"` → `"local"`; собрать
  `code_index_dir` в `body`.
- `FIELD_LABELS`: `code_index_dir: "Каталог code_index"` (подпись «Порт
  code_index» приходит из `field_labels` вида).
- `deployLocalFromForm()` / `deployLocal(id)` — по аналогии с `deployFromForm`/
  `launchMcp`, но на новые эндпоинты `deploy-local/stream`.

## Поток данных

```
Форма (вид code-index-local)
  → POST /api/mcp {catalog_dir, project_name, code_index_dir, port, …}
  → mcp_servers (строка карточки)
Кнопка «Развернуть локально»
  → POST /api/mcp/{id}/deploy-local/stream
      → download_binary(code_index_dir)                 [GitHub Releases]
      → write daemon.toml (alias=project_name, path=catalog_dir)
      → autostart.install_and_start(daemon run)
      → autostart.install_and_start(serve, MCP_HTTP_PORT=port)
  → connection: http://localhost:{port}/mcp  (в .mcp.json как и docker-вид)
```

## Обработка ошибок

- Неподдерживаемая платформа/арх (`host_asset_key() is None`) — внятная ошибка
  со списком поддерживаемых (Win x64 / Linux x64 / macOS arm64).
- Ассет не найден в релизе — ошибка с перечнем доступных имён.
- Сбой скачивания/распаковки — ошибка с текстом, автозапуск не трогаем.
- Отсутствие `schtasks`/`systemctl`/`launchctl` — ошибка с подсказкой.
- `loginctl enable-linger` упал — предупреждение, развёртывание продолжается.
- Валидация обязательных полей — `400` с указанием недостающего поля (как у
  docker-вида).

## Тестирование

Юнит-тесты (pytest, как в `app/tests/env`):

- `code_index_release`: `host_asset_key` под разные `sys.platform`/`machine`
  (monkeypatch); `resolve_asset` на фикстуре JSON релиза (выбор bsl-indexer под
  платформу, ошибка при отсутствии); `download_binary` с инъекцией `fetch`/
  `runner` (без сети/ФС-ОС).
- `autostart`: генераторы `.service`/`.plist`/`.cmd` — проверка содержимого;
  `install_and_start` под каждую ОС (monkeypatch `sys.platform`, инъекция `run`)
  — проверка состава команд, без реального исполнения.
- `mcp_docker_recipes`/ядро: `_daemon_toml(alias, path)` — alias и path для обоих
  видов (docker `/repos/src`, локальный — путь каталога; с кириллицей).
- `mcp_types`: новый вид, `required`, `field_labels`, title docker-вида.
- `store/test_mcp`, `env/test_mcp_api`: roundtrip `code_index_dir`; эндпоинты
  `deploy-local`/`deploy-local/stream` с инъекцией оркестратора (мок
  скачивания/автозапуска), стрим лога.

JS-логика юнит-тестами не покрывается — держим согласованной с docker-веткой.

## Вне области (YAGNI)

- System-level автозапуск (root/admin), мультиарх сверх публикуемого upstream.
- Пиннинг версии релиза (всегда `latest`).
- Мультирепо в `daemon.toml` (остаётся один `[[paths]]`; см. ALIAS.md).
- Остановка/удаление автозапуска из UI (можно добавить позже; сейчас — только
  развёртывание, как у docker-вида, где контейнер тоже не удаляется из карточки).

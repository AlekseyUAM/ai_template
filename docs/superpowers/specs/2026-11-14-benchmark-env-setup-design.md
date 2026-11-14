# Подготовка benchmark-окружения одной командой

Дата: 2026-11-14
Статус: согласовано с пользователем (дизайн), готово к плану реализации

## Цель

Скрипт, который по одному `test.env` создаёт готовый к прогону benchmark-проект,
аналогичный `/home/uam/projects/test2/`:

- каталог проекта с окружением `.claude/`, `.mcp.json`, `.1c-devbase.json`, `.venv`;
- база 1С: восстановлена из `.dt` **или** собрана из `benchmark/cf` и двух
  расширений (`ЮнитТесты.cfe`, `1c-mcp-tools-1.0.6.cfe`);
- выгрузка `src/cf` и `src/cfe` из базы;
- задачи из `benchmark/tasks` в каталоге `tasks/` и в БД AgentMon;
- проект и задачи зарегистрированы в БД AgentMon и реестре диспетчера — видны
  в UI и запускаемы;
- MCP: общие `bsl_ls` и `1c_platform` по адресам из `test.env`, `1c-md` при
  наличии адреса, `code_index` в Docker с полной индексацией `src/cf`;
- git: коммиты `init` и `baseline before task#<идентификатор первой задачи>`.

## Не входит в Scope

- Настройка веб-публикации `1c-md` и прав кластера 1С.
- Запуск прогона benchmark и сбор метрик.
- Изменение `test2` и существующих общих MCP-карточек.
- Автоматическое удаление/пересоздание успешно созданного проекта.

## Файлы

| Путь | Назначение |
|---|---|
| `benchmark/test.env` | реальные значения (секреты), в `.gitignore` |
| `benchmark/example.test.env` | образец с комментариями, без секретов |
| `benchmark/setup_benchmark.py` | тонкий CLI: `python benchmark/setup_benchmark.py [--env PATH]` |
| `app/src/agentmon/env/bench_setup.py` | оркестрация, переиспользует штатные модули `agentmon.env` |
| `app/tests/env/test_bench_setup.py` | юнит-тесты с фейками store/registry/1С/Docker |
| `.gitignore` | правило `/benchmark/test.env` |
| `benchmark/README.md` | раздел «Подготовка окружения» |

## Контракт test.env

Формат `KEY=value`, `#` — комментарий, пустые строки игнорируются. Пути
раскрываются (`~`), значения не раскрывают переменные окружения. Неизвестные
ключи — предупреждение. Пустое значение обязательного ключа = ошибка конфигурации.

### Обязательные

| Ключ | Смысл |
|---|---|
| `BENCH_PROJECT_NAME` | имя проекта; валидация `project_checks.validate_name` |
| `BENCH_PROJECT_DIR` | абсолютный путь нового каталога (после `expanduser`) |
| `BENCH_DEVELOPER_ID` | git `user.name` и `projects.identifier` |
| `BENCH_DEVELOPER_EMAIL` | git `user.email` и `projects.email` |
| `BENCH_PLATFORM_PATH` | каталог платформы или сам бинарник `1cv8`/`1cv8.exe` |
| `BENCH_DB_CONNECTION` | `Srvr=host;Ref=base` (серверная) или путь к файловой ИБ |
| `BENCH_DB_USER` | пользователь 1С |
| `BENCH_DB_PASSWORD` | пароль 1С; ключ обязателен, значение может быть пустым |
| `MCP_BSL_LS_URL` | полный URL, напр. `http://localhost:8001/mcp` |
| `MCP_1C_PLATFORM_URL` | SSE-адрес, напр. `http://localhost:8002/sse` |
| `MCP_CODE_INDEX_PORT` | целое 1..65535, порт code_index |

### Необязательные

| Ключ | По умолчанию | Смысл |
|---|---|---|
| `MCP_1C_MD_URL` | — | URL http-сервиса, напр. `http://localhost/t_bench/hs/mcp` |
| `BENCH_DT_PATH` | — | локальный путь к `.dt`; задан → cf/расширения не грузятся |
| `MCP_CODE_INDEX_HOST` | `localhost` | хост code_index в `.mcp.json` |
| `CODE_INDEX_WAIT_MINUTES` | `360` | таймаут ожидания полной индексации |

### Пример адресов

- `MCP_BSL_LS_URL=http://localhost:8001/mcp`
- `MCP_1C_PLATFORM_URL=http://localhost:8002/sse`
- `MCP_1C_MD_URL=http://localhost/t_bench/hs/mcp`
- `MCP_CODE_INDEX_PORT=8004`

## Архитектура

`bench_setup.py` — библиотека без побочных эффектов на импорте. CLI:

1. Загружает `.ai1c.env` репозитория (тот же парсер, что `run.py`) **до** импорта
   `agentmon.config`, чтобы `AGENTMON_DSN`/`AGENTMON_DB` были актуальны.
2. Разбирает `test.env`, строит `BenchConfig`.
3. Вызывает `run_setup(...)` с инъектируемыми зависимостями:
   `store`, `registry`, `prov`, `run_cmd`, `docker`, `sleep`, `clock`, `log`.
   `bench_setup` не импортирует `agentmon.config` на уровне модуля: DSN и путь
   реестра передаются аргументами (CLI читает их из `agentmon.config` после
   загрузки `.ai1c.env`).
4. Печатает шаги `▶/✓/✗` и итоговую сводку; код возврата 1 при ошибке.

Подключение к БД:

- store — `agentmon.store.db.connect(agentmon.config.DSN)` + `init_schema`
  (идемпотентно). DSN берётся из `.ai1c.env`; при недоступности PG — ошибка, без
  тихого переключения на SQLite (монитор не увидел бы запись).
- реестр — `agentmon.registry.open_db(agentmon.config.DB_PATH)`.
- Относительные пути БД разрешаются от корня репозитория (скрипт делает `chdir`).

## Поток выполнения

### 0. Preflight (fail fast, ничего не менять)

- Все обязательные ключи присутствуют и непусты; порт и таймаут — числа;
- `BENCH_PROJECT_DIR` не существует или пуст;
- в store нет проекта с таким `name` или `path`; в реестре нет проекта с таким `path`;
- `validate_name` проходит;
- платформа найдена (`devbase._platform_path`);
- версия платформы извлекается из пути регуляркой `\d+\.\d+\.\d+\.\d+`;
- существуют `benchmark/cf` (когда нет `.dt`), оба `.cfe` (когда нет `.dt`),
  `BENCH_DT_PATH` (когда задан);
- TCP-доступны хосты/порты `MCP_BSL_LS_URL` и `MCP_1C_PLATFORM_URL`.

### 1. Каталог и стаб в БД

- Создать каталог проекта.
- В store добавить `projects` (name, path, identifier, email, platform_dir =
  бинарник, platform_version, db_kind, db_connection, web_publication="",
  env_version=`current_env_version()`).
- Разрешить MCP-карточки и связать с проектом (`project_mcp`):
  - **Переиспользование**: карточка с тем же `standard_key`, тем же
    `connection_json` и (для code-index) теми же `catalog_dir`/`project_name` —
    связывается как есть.
  - **Создание**: имя `<project>: <mcp_name>`; поля по виду MCP:
    - `bsl-ls` / `kind=docker` / `mcp_name=bsl_ls`;
    - `1c-platform` / `kind=docker` / `mcp_name=1c_platform`;
    - `1c-md-queries` / `kind=extension` / `mcp_name=1c-md` — только если задан URL;
    - `code-index` / `kind=docker` / `mcp_name=code_index`, `url=host`,
      `port`, `catalog_dir=<project>/src/cf`, `project_name=<project name>`.
- Фрагменты `connection_json`:
  - `bsl_ls`: `{"type":"http","url":"<MCP_BSL_LS_URL>"}`;
  - `1c_platform`: `{"type":"stdio","command":"python3","args":[
    ".claude/mcp/sse_stdio_bridge.py","<MCP_1C_PLATFORM_URL>"]}`;
  - `1c-md`: `{"type":"http","url":"<MCP_1C_MD_URL>"}`;
  - `code_index`: `{"type":"http","url":"http://<host>:<port>/mcp"}`.

### 2. Окружение проекта

`install_environment(config, update=False, register=noop, git_init=False,
dump_cf=False, dump_cfe=False, db_user=..., db_password=..., prov=...)`:

- шаблон `.claude` (`deploy_content`), `.mcp.json`, `.1c-devbase.json`,
  `.venv` (`provision_venv`);
- агенты рендерятся с моделями по умолчанию (`claude-sonnet-4-6` / `medium`);
- при отсутствии `1c-md` условные блоки шаблона вырезаются, MCP-инструменты
  `1c-md` не попадают в allow-list агентов;
- `register` — пустой callback: реестр пополняется только в конце.

### 3. База 1С

Независимо от ветки (`.dt` или cf/расширения), если базы нет — попытаться
создать:

- файловая: `1cv8 CREATEINFOBASE File="<path>"`;
- серверная: `1cv8 CREATEINFOBASE "Srvr=<host>;Ref=<base>"`.

Ненулевой код возврата `CREATEINFOBASE` не фатален (база могла уже
существовать); лог печатается, реальная ошибка проявится на следующем шаге.
Затем — команды через развёрнутый в проекте `1c-batch` (интерпретатор `.venv`
проекта, cwd = каталог проекта, `.1c-devbase.json` уже записан):

- `BENCH_DT_PATH` задан: `restore-ib <abs path>`;
- иначе:
  1. `load-config <benchmark/cf>` (включает `/UpdateDBCfg`);
  2. `load-cfg-extension <app/web/assets/ЮнитТесты.cfe> --name ЮнитТесты`;
     `update-db-cfg --extension ЮнитТесты`;
  3. `load-cfg-extension <deps/mcp_tools_cfe/1c-mcp-tools-1.0.6.cfe>
     --name mcp_tools`; `update-db-cfg --extension mcp_tools`.

Имена расширений `ЮнитТесты` и `mcp_tools` — константы (совпадают с
`test2/src/cfe`). При заданном `MCP_1C_MD_URL` после загрузки — HTTP-проверка
доступности URL: недоступен → ошибка (до тяжёлой индексации).

### 4. Выгрузка

- `dump-config src/cf`;
- `dump-config src/cfe --all-extensions`.

### 5. code_index (сразу после выгрузки, индексация в фоне)

- `docker rm -f -v ai1c-mcp-code_index` — если контейнер есть (удаляет и
  non-persistent volumes; bind-монтирование проекта не трогается);
- параметры через `mcp_docker_recipes.launch_params("code-index", ...)`:
  образ `bsl-indexer:local`, env `MCP_HTTP_HOST=0.0.0.0`,
  `MCP_HTTP_PORT=<port>`, `CODE_INDEX_HOME=/data/code-index-home`,
  volumes `<project>/src/cf:/repos/src` и
  `<repo>/.ai1c/mcp-state/<mid>:/data/code-index-home`;
  `daemon.toml` генерируется `launch_params` (alias = имя проекта,
  path = `/repos/src`, cache target = `http://127.0.0.1:<port>`);
- если образа нет — собрать штатным рецептом (`mcp_sources.clone` +
  `mcp_docker.build`);
- запуск `mcp_docker.launch` с публикацией `127.0.0.1:<port>`;
- ожидание полной индексации: опрос
  `docker exec ai1c-mcp-code_index env CODE_INDEX_HOME=/data/code-index-home
  bsl-indexer daemon status --json` каждые 15 с; успех — все `paths[].status ==
  "ready"`; `"error"` → немедленная ошибка; таймаут → ошибка с подсказкой
  увеличить `CODE_INDEX_WAIT_MINUTES`. Прогресс (`progress`/`files_done` в
  JSON, если появится) печатается.
- контейнер в этот момент уже готов для `.mcp.json`, но финальная проверка —
  после ожидания.

### 6. Git

- `devbase.git_init_project(prov, project_dir, config=cfg)` +
  `git_commit_all(..., "init")` — после окружения и выгрузки;
- после импорта задач — `git_commit_all(..., "baseline before task<identifier>")`
  (как в истории test2: `baseline before task#001`).

### 7. Импорт задач

- Каталоги `benchmark/tasks/task##*/`, содержащие `task.json`, сортируются по
  имени; требование — хотя бы одна задача.
- Файлы копируются в `tasks/<имя каталога>` **дословно** (сохраняются правки
  `TASK.md`, например текущая правка task##002).
- В БД добавляется задача: поля `name/goal/plan/constraints/tests` — из
  `task.json`; `stages_json` — из массива `stages` без изменений;
  `status="planned"`, `stage=NULL`, `kind`, `update_db`, `max_minutes`,
  `mark_changes`, `interactive=0`, `created_at=now`.
- В скопированном `task.json` переписываются: `id` → новый id БД, `project_id`
  → новый проект, `developer_id` → `BENCH_DEVELOPER_ID`, `status`, `stage`,
  `started_at`/`finished_at` = null, `created_at` = локальный ISO (`timefmt`),
  `update_db`/`mark_changes` — булевы; `stages` сохраняются.
- В `TASK.md` обновляется только номер в заголовке первой строки
  `# Задача <identifier> (#<old>): ...` → `(#<new>)`; остальной текст не
  трогается. Если шаблон не совпал — файл не меняется.
- Расхождение `TASK.md` и `task.json` (текущая правка task##002) не
  «лечится»: БД получает данные `task.json`, `TASK.md` остаётся источником для
  агентов, как в штатном AgentMon.

### 8. Финал

- `registry.add(name, path, backend="local")` — проект появляется в мониторе
  только после успешного завершения всех шагов;
- сводка: id проекта, id задач, путь, коммиты, MCP-адреса, контейнер и порт;
- проверка, что контейнер code_index запущен и индекс `ready`.

## Откат при ошибке

- Удалить созданные этим запуском строки: задачи, `project_mcp`, MCP-карточки
  (только созданные, не переиспользованные), проект из store.
- Реестр не трогать (запись добавляется последней и только при успехе).
- Если контейнер code_index запускал этот запуск — `docker rm -f -v`.
- Каталог проекта **не удалять** (диагностика); в сообщении — путь и
  необходимость удалить его перед повтором (preflight не пропустит непустой
  каталог).
- Секреты (`BENCH_DB_PASSWORD`) не печатать в лог и не писать в git.

## Ошибки и сообщения

- Ошибки конфигурации — до любых изменений, с перечнем ключей.
- Ошибки 1С: печатать команду, код возврата и хвост лога `1c-batch`; ошибки
  аутентификации не ретраить.
- Ошибка индексации/таймаут: имя контейнера, порт, путь `daemon.json`, совет
  увеличить `CODE_INDEX_WAIT_MINUTES`.
- Ошибка БД: явное сообщение, какой DSN/файл недоступен.

## Тестирование

`app/tests/env/test_bench_setup.py` (pytest, фейки, без 1С/Docker/БД):

1. Парсинг `test.env`: обязательные/необязательные, пустой пароль, `~`,
   неизвестные ключи, отсутствующие значения.
2. Preflight: непустой каталог, дубль имени/пути, отсутствие cf/cfe/dt,
   недоступный общий MCP.
3. MCP: сборка `connection_json`, переиспользование точной карточки, создание
   новой, ветка без `1c-md`.
4. Команды базы: create file/server, restore dt, load cf + два расширения +
   update db, dump cf/cfe; ветка `.dt` не содержит load-команд.
5. Импорт задач: копирование, переписывание `id/project_id`, сохранение тела
   `TASK.md`, обновление заголовка, сохранение stages, требование ≥1 задачи.
6. Git: коммиты `init` и `baseline before task#001`.
7. code_index: `docker rm -f -v`, параметры launch, ожидание `ready`,
   обработка `error` и таймаута.
8. Откат: строки БД удалены, каталог оставлен, контейнер удалён.

## Критерии приёмки

- На чистом окружении валидный `test.env` создаёт проект, видимый в дереве
  AgentMon, с задачами из `benchmark/tasks`.
- `.mcp.json` содержит `bsl_ls`, `1c_platform`, `code_index` и `1c-md` при
  заданном URL; без URL — три сервера.
- `.1c-devbase.json` содержит платформу, подключение и креды; файл в
  `.gitignore`.
- Ветка `.dt` восстанавливает базу и не грузит cf/расширения; ветка без `.dt`
  грузит `benchmark/cf` + `ЮнитТесты` + `mcp_tools`.
- `src/cf` и `src/cfe` выгружены; есть коммиты `init` и
  `baseline before task#001`.
- Контейнер `ai1c-mcp-code_index` пересоздан с `-v`, индекс `src/cf` в статусе
  `ready`.
- Повторный запуск с теми же значениями завершается ошибкой preflight, ничего
  не меняя.
- `benchmark/test.env` не попадает в git; в `example.test.env` нет секретов.

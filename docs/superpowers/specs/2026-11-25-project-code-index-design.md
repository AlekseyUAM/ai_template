# Мастер проекта: code index и docker-проект по схеме benchmark

Дата: 2026-11-25

## Контекст

В benchmark уже работает размещение проекта в Docker (`BENCH_PLACEMENT=docker`,
коммит `cdb25bc6`): проект целиком живёт в томе контейнера (`/workspace`),
code-index — в томе `/code-index` и запускается **внутри** контейнера, контейнер
поднимается с host-сетью и хостовым uid/gid, установка идёт через
`DockerProvisioner`. Проверено вручную: в таком контейнере работают
`claude-ds`, нативный `bsl-indexer` и сессии claude.

Мастер проекта AgentMon создаёт docker-проект иначе: bridge-сеть, root,
том `<name>-claude:/root/.claude`, без тома `/code-index`, без обёртки агента в
контейнере. Нативный code-index в AgentMon умеет несколько баз в одном
`code_index_dir` (несколько `[[paths]]`, обращение по alias = имя проекта), но
разворачивается только на хосте и не видит файлы docker-проекта.

В мастере проекта секция «MCP-серверы» позволяет только выбрать существующие
карточки; отдельной галочки code index и автозагрузки сервиса нет.

## Цели

1. Перенести в AgentMon работающую схему docker-проекта из benchmark (тома,
   code-index внутри контейнера, host-сеть на локальном Docker Linux), не
   монтируя хостовый `/home/uam`.
2. В карточке проекта в секции «MCP-серверы» добавить галочку **code index** и
   два поля: «Каталог кодовой базы» (автозаполнение `<проект>/src/cf`) и
   «Каталог code_index».
3. При создании проекта автоматически создавать/переиспользовать карточку
   code-index, добавлять её в проект (`.mcp.json`) и разворачивать сервис;
   дождаться готовности индекса.
4. Один `code_index_dir` может обслуживать несколько баз; обращение — по
   `alias`, который всегда равен имени проекта.
5. Та же функциональность для docker-проектов; на Windows контейнер
   поднимается по той же схеме, что и на Linux (с учётом ограничений Docker
   Desktop).

## Принятые решения

- **Хостовый `/home/uam` не монтируется.** HOME агента — `/root` внутри
  контейнера; сессии claude лежат в томе `<name>-claude:/root/.claude`.
  `$HOME/.claude.json` (доверие/глобальный конфиг) не входит в том — он
  сидируется при создании контейнера. Пользователь контейнера — `root` на
  Linux и Windows (одинаковая схема, хостового uid/gid нет, потому что нет
  хостовых bind-mount'ов проекта).
- **Тома:** `<name>-work:/workspace`, `<name>-codeindex:/code-index`,
  `<name>-claude:/root/.claude`.
- **Сеть:** локальный Docker на Linux — `--network host` (как benchmark);
  Windows/macOS (Docker Desktop) и удалённый Docker-демон — bridge +
  `host.docker.internal` (host-сеть в Docker Desktop для Linux-контейнеров
  недоступна).
- **Репозиторий template не монтируется** — это benchmark-специфика (эталон
  аналитика, `benchmark/cf`, `.dt`); AgentMon-проект использует собственный
  развёрнутый шаблон.
- **Лицензии 1С.** Если «Сервер лицензий» пуст и backend=docker, в секции
  «Платформа» показывается редактируемое поле «Каталог лицензий 1С»:
  - POSIX — `/var/1C/licenses`;
  - Windows — `C:\ProgramData\1C\licenses` (общий каталог лицензий; путь
    редактируемый, т.к. зависит от установки).
  Указанный каталог монтируется в контейнер как `/var/1C/licenses` (rw).
  Пусто → монтирования нет. Задан сервер лицензий → поле скрыто, монтирования
  нет. Для удалённого Docker-демона путь трактуется как путь на удалённом
  хосте (проверка существования не выполняется).
- **Команда агента** берётся из `AGENTMON_CLAUDE_CMD` (и per-project override
  `claude`, если задан). Для docker в контейнер копируются обёртки из
  `deploy/claude/` (не монтируются, чтобы одинаково работало на Windows, где
  host-обёртка — `.bat`):
  - `claude` (в т.ч. полный путь) — ничего, `claude` уже в образе;
  - `claude-ds` — `/usr/local/bin/claude-ds` + `~/.config/deepseek/key`
    (ключ из `DEEPSEEK_API_KEY` или `~/.config/deepseek/key` на хосте; нет
    ключа — понятная ошибка создания);
  - `claude-local` — `/usr/local/bin/claude-local` + `.claude/settings.local.json`
    из Strata (`fetch_strata_env` → `build_strata_settings`, как в
    `setup_benchmark.py`); `strata` недоступен — ошибка создания;
  - прочее — ошибка: для docker поддерживаются claude/claude-ds/claude-local.
  Обёртки пишутся с LF, `chmod 755`; ключ — `0600`.
- **Галочка code index** в секции «MCP-серверы»; при включении доступны два
  редактируемых поля. Автозаполнение «Каталога кодовой базы»:
  `<каталог проекта>/src/cf` (для Windows-путей — с `\`). Дефолт «Каталога
  code_index»: local — `<каталог проекта>-code-index`, docker — `/code-index`.
  Для backend=ssh блок скрыт (вне области). В режиме `?id=` (update-env) блок
  скрыт: code index управляется только при создании.
- **Порт сервиса:** из `<code_index_dir>/service.json`, иначе первый свободный
  начиная с 8005. Свободность проверяется по TCP на 127.0.0.1 для local и для
  docker на POSIX с host-сетью; на Windows порт внутри контейнера не проверяется.
- **Карточка MCP:** local — `standard_key=code-index`, `kind=local`; docker —
  новый скрытый вид `code-index-docker`, `kind=docker`, `action=None` (кнопка
  host-развёртывания не показывается). Поля: `mcp_name=code_index`,
  `connection` = `{"code_index": {"type": "http", "url": "http://localhost:<порт>/mcp"}}`,
  `catalog_dir`, `project_name` (alias), `code_index_dir`, `port`, `purpose` из
  вида. Карточка добавляется в `project_mcp` и в MCP-выбор проекта — попадает
  в `.mcp.json` с `alwaysLoad` (существующее правило).
- **Переиспользование карточки:** совпадение `standard_key`, `connection_json`,
  `catalog_dir`, `project_name`, `code_index_dir`; иначе создаётся новая с
  уникальным именем `<проект>: code_index`.
- **Мульти-база:** один `code_index_dir` — один сервис; добавление базы —
  `merge_path` по alias (чужие `[[paths]]` и секции сохраняются),
  `daemon reload`, перезапуск `serve`. Порт берётся из `service.json`.
- **Ожидание готовности:** создание проекта не завершается, пока индекс не
  готов (все `[[paths]]` в `ready`). Таймаут — 360 минут (как дефолт benchmark);
  ошибка демона или таймаут — ошибка создания с хвостами `daemon.log`/`serve.log`.
- **Откат:** удаляются созданные в этом запуске карточки, запись проекта и
  регистрация; останавливается code-index, только если сервис был создан этим
  запуском. Общий сервис с другими базами не останавливается. Каталог/том и
  контейнер остаются для диагностики.
- `update-env` code-index не трогает (и `.mcp.json` при update не
  перезаписывается — как сейчас).
- Существующие docker-контейнеры не пересоздаются: новая схема применяется к
  новым проектам/контейнерам. Code-index для уже созданных проектов в этой
  задаче не дооснащается.

## Архитектура

### Новые модули

```
app/src/agentmon/env/
  code_index_project.py   # карточка, порт, выбор способа развёртывания,
                          # локальный wait
  code_index_docker.py    # развёртывание и wait внутри контейнера проекта
  agent_setup.py          # обёртка/ключ/Strata-настройки в контейнере
```

### `code_index_project.py`

- `CodeIndexRequest(catalog_dir: str, code_index_dir: str)` — нормализованный
  запрос из мастера.
- `validate_request(backend, project_dir, request)` — абсолютность путей,
  `code_index_dir` не внутри `project_dir` (для local — `resolve()`, для
  docker — `posixpath.normpath`), непустые значения. Ошибки — пользовательские.
- `pick_port(code_index_dir, *, read_service_port, tcp_ok, host_check, start=8005)`
  — порт из `service.json` либо первый свободный в диапазоне 8005–8104
  (100 попыток, иначе ошибка); `host_check=False` на Windows для docker.
- `resolve_card(mcp_repo, *, project_id, project_name, backend, request, port)`
  → `(mcp_id, McpSelection, created: bool)`. Реализует правило переиспользования
  и `standard_key`/`kind` из «Принятых решений».
- `deploy(prov, backend, *, ...)` — генератор строк журнала: для local вызывает
  `code_index_local.deploy_local`, для docker — `code_index_docker.deploy`.
- `wait_ready(...)` — для local: `bsl-indexer daemon status --json` с
  `CODE_INDEX_HOME`, все пути `ready`, затем TCP-проба порта; для docker —
  `code_index_docker.wait_ready`.
- Константа `CODE_INDEX_WAIT_MINUTES = 360`.

### `code_index_docker.py`

- `deploy(prov, *, code_index_dir, catalog_dir, alias, port, download=..., log)`
  — генератор:
  1. `mkdir -p <code_index_dir>`.
  2. Если бинаря нет — скачать linux-бинарь (`code_index_release.download_binary`
     с `platform_name="linux"`) во временный каталог на хосте и скопировать в
     контейнер (`prov.copy_in`), `chmod +x`.
  3. Прочитать существующий `daemon.toml` (если есть), `merge_path(alias, path)`,
     `ensure_sections(port)`, записать обратно.
  4. Погасить прежние процессы сервиса этого каталога (`pkill -f '[b]sl-indexer'`
     внутри контейнера), запустить detached `daemon run` и `serve` с
     `CODE_INDEX_HOME=<code_index_dir>`; логи — `daemon.log`/`serve.log` в
     каталоге сервиса.
- `wait_ready(prov, *, code_index_dir, port, wait_minutes, ...)` — опрос
  `daemon status --json` через `prov.run(..., env={"CODE_INDEX_HOME": ...})`;
  проверка живости процессов (`pgrep`), ошибки путей `status=error` → сразу
  ошибка; TCP с хоста не проверяется (на Windows порт не опубликован).
- `stop(prov, code_index_dir)` — `pkill` (best-effort; откат).

### `agent_setup.py`

- `container_command(command) -> str` — команда для `docker exec`: basename
  (`claude`, `claude-ds`, `claude-local`) + исходные аргументы; хостовый путь к
  бинарнику отбрасывается (в контейнере его нет). `DockerRunner` использует
  нормализованную команду; local/ssh — исходную.
- `prepare(prov, project_dir, command, *, repo_root, log)`:
  - разбирает команду (`shlex`, правила Windows/backslash как в
    `registry._validate_claude_cmd`) → basename;
  - basename `claude` — no-op (в контейнере используется `claude` + аргументы);
  - `claude-ds` / `claude-local` — копирование обёртки из
    `<repo>/deploy/claude/*.sh` в `/usr/local/bin/<имя>` (LF, 755);
  - `claude-ds` — чтение ключа (`DEEPSEEK_API_KEY` или
    `~/.config/deepseek/key`), запись в `<HOME контейнера>/.config/deepseek/key`
    (0600); `<HOME>` определяется через `prov.run(["sh","-c","printf %s \"$HOME\""])`,
    fallback `/root`;
  - `claude-local` — `fetch_strata_env("strata")` → `build_strata_settings` →
    запись `<project>/.claude/settings.local.json`;
  - неизвестная команда — `ValueError`.

### Изменения в `backends/docker.py`

- `_DockerContainer.exec_run(..., env=None)` → добавляет `-e K=V`;
  `exec_detached(argv, cwd=None, env=None)` → `docker exec -d ...`.
- `DockerProvisioner`:
  - `run(..., env=None)`, `exec_detached(...)`, `copy_in(local_path, dst)`
    (`docker cp`);
  - `seed_trust_project: str | None` — после `ensure()` один раз (флаг на
    экземпляр, best-effort) дописать `/root/.claude.json` (или `$HOME/.claude.json`)
    `projects[<project>].hasTrustDialogAccepted = true`, сохранив остальное.
- `DockerBackend`/фабрика:
  - в контейнер всегда добавляется том `<name>-codeindex:/code-index`;
  - `extra_run_args`: `--network host` только для локального демона на POSIX;
  - если в `conn` есть `license_dir` — bind-mount `<license_dir>:/var/1C/licenses`;
  - `DockerProvisioner(..., seed_trust_project=project.path)`.
- `DockerRunner` для docker-проекта запускает нормализованную команду
  (`agent_setup.container_command`), а не хостовый путь.
- Протоколы Provisioner не меняются (новые методы — расширение, не обязательные
  для local/ssh).

### API мастера (`env/project_api.py`)

- Новые поля тела создания:
  - `code_index: {enabled: bool, catalog_dir: str, code_index_dir: str}`;
  - `license_dir: str | None` (только docker, при пустом `license_server`).
- Валидация до записи в БД (400 с понятным текстом): `code_index` запрещён для
  backend=ssh; `license_dir` принимается только для docker. Для docker
  `license_dir` при локальном демоне проверяется на существование; для
  удалённого — без проверки.
- `conn` docker-проекта расширяется `license_dir` (фабрика читает его при
  создании контейнера); значение попадает в реестр.
- Перед установкой окружения — `_attach_code_index`: выбрать порт,
  создать/переиспользовать карточку, добавить `McpSelection` в `EnvConfig`,
  `mcp_repo.set_for_project(...)`. Для local шаг выполняется в
  `_prepare_install` (`service.json` читается с хоста); для docker — в
  `_create_produce`/блокирующем create **после** сборки образа и `ensure`
  контейнера (тогда `service.json` можно прочитать из тома).
- После установки окружения: `agent_setup.prepare`, затем
  `code_index_project.deploy` + `wait_ready` (только если включено).
- Возвращаемое значение и события создания дополняются строкой журнала
  `[code-index] ...`; для блокирующего эндпоинта — сводкой порта/alias.
- `_rollback_project` принимает созданные карточки и признак «сервис создан
  этим запуском»; останавливает/удаляет только своё.

### Виды MCP (`env/mcp_types.py`, `env/mcp_catalog.py`, `web/mcp.js`)

- Новый скрытый `McpType` `code-index-docker` с теми же полями/дефолтами, что
  `code-index`, `action=None`, `hidden=True`.
- `_PRELOAD_IDS` в `mcp_catalog` дополняется `code-index-docker` (правило
  `alwaysLoad` по имени `code_index` уже действует).
- `mcp.js`: для карточки `standard_key=code-index-docker` не показывать кнопку
  развёртывания. Скрытый вид не попадает в `/api/mcp/types`, поэтому текущий
  фолбэк `isDocker = mcp.kind === "docker"` иначе показал бы «Развернуть в
  Docker локально»; нужен явный пропуск действия.

### Документация

- `docs/running-web-ui.md` — мастер проекта: code index, каталог лицензий,
  docker-схема.
- `docs/mcp/code-index-common.md`, `docs/mcp/code-index-local.md` — code-index
  docker-проекта (в контейнере, alias = имя проекта).
- `.ai1c.env.example` — уже исправлен: обёртки задаются только глобально.

### Мастер (`app/web/project-wizard.html`, `project-wizard.js`)

- Секция «MCP-серверы»: чекбокс `codeIndexEnabled` «code index»; скрытый блок
  с полями `codeIndexCatalogDir` и `codeIndexDir` и подсказками
  («в контейнере» для docker).
- Автозаполнение каталога кодовой базы от поля «Каталог проекта» (с учётом
  разделителя Windows); при правке пользователем автозаполнение больше не
  затирает значение.
- Дефолт «Каталога code_index» зависит от backend; при переключении backend
  обновляется, если пользователь не менял.
- Блок скрыт для ssh и в режиме `?id=`.
- Секция «Платформа»: поле `licenseDir` видно только для docker и пустого
  «Сервера лицензий»; дефолт приходит с сервера
  (`GET /api/env/projects/requirements` → `license_dir`).
- В тело создания добавляются `code_index` и `license_dir`; клиентская
  валидация обязательности/абсолютности путей.

## Потоки

### Создание local-проекта с code index

1. Мастер валидирует поля, шлёт `code_index`.
2. `_prepare_install`: проверка путей; порт из `service.json` или свободный;
   карточка создана/переиспользована и связана с проектом; `McpSelection`
   добавлен в `EnvConfig`; проект записан в БД.
3. `install_environment`: создаёт `src/cf`, пишет `.mcp.json` с `code_index`,
   git-коммит.
4. `code_index_local.deploy_local`: бинарь, `service.json`, merge `[[paths]]`,
   autostart daemon+serve (или reload/restart для существующего сервиса).
5. `wait_ready`: `daemon status` = ready + TCP; создание завершается.

### Создание docker-проекта с code index

1. Мастер шлёт `code_index` и `license_dir`; `_prepare_install` пишет проект,
   `conn = {image, license_dir}`.
2. `_create_produce`: сборка образа (если нужна) → `ensure` контейнера
   (тома `/workspace`, `/code-index`, `/root/.claude`; сеть по ОС; лицензии) →
   порт/карточка → `install_environment` (через `DockerProvisioner`).
3. `agent_setup.prepare`: обёртка и ключ/Strata-настройки в контейнере.
4. `code_index_docker.deploy`: linux-бинарь в `/code-index`, `daemon.toml` с
   `path=/workspace/src/cf`, alias = имя проекта, detached daemon+serve.
5. `wait_ready` (внутри контейнера); затем регистрация проекта и завершение.

### Вторая база в тот же `code_index_dir`

1. Второй проект указывает тот же каталог; порт берётся из `service.json`.
2. Карточка второго проекта создаётся заново (другие `catalog_dir`/alias).
3. `merge_path` добавляет `[[paths]]` второго alias, сохраняя первый.
4. `daemon reload`, перезапуск `serve`; wait ждёт готовности всех путей.
5. Агенты обращаются к нужной базе через `repo="<alias>"`.

### Обновление окружения (`?id=`)

- Блок code index скрыт; `update-env` не меняет карточки/`.mcp.json`/сервис.

## Обработка ошибок

- Некорректные пути/команда агента/нет ключа/нет `strata` — 400 или событие
  `error` в журнале создания с понятным текстом; откат.
- Ошибка скачивания бинаря/запуска процессов/индексации — событие `error`,
  хвосты логов, откат.
- Таймаут ожидания — ошибка с указанием `daemon.log`/`serve.log`.
- Общий сервис с другими базами при откате не останавливается; удаляется
  только карточка, созданная этим запуском.
- Docker-контейнер/тома после отката не удаляются — диагностика; повторное
  создание допускается (тома переиспользуются, установка идемпотентна).

## Критерии приёмки

- В мастере есть галочка «code index» и два поля; каталог кодовой базы
  автозаполняется `<проект>/src/cf`; дефолты code_index зависят от backend;
  для ssh и `?id=` блок скрыт.
- Создание local-проекта с галочкой: карточка `code-index` создана (или
  переиспользована), связана с проектом, `.mcp.json` содержит
  `code_index` c `alwaysLoad`; сервис запущен; `daemon.toml` содержит
  `alias = <имя проекта>`; создание завершается после `ready`.
- Создание docker-проекта: контейнер с томами `<name>-work`, `<name>-codeindex`,
  `<name>-claude`; на POSIX с локальным демоном — `--network host`; бинарь и
  процессы `bsl-indexer` — внутри контейнера; карточка `code-index-docker`,
  сервис ready; на Windows контейнер поднимается с той же раскладкой томов и
  bridge-сетью. Карточка `code-index-docker` не предлагает host-развёртывание.
- `AGENTMON_CLAUDE_CMD=claude-ds`: в контейнере есть
  `/usr/local/bin/claude-ds` и `/root/.config/deepseek/key`; `claude` —
  без изменений; `claude-local` — есть обёртка и `settings.local.json` из
  Strata; неизвестная команда — понятная ошибка.
- Лицензии: при пустом сервере лицензий и заданном каталоге контейнер видит
  `<каталог>:/var/1C/licenses`; при заданном сервере — поле скрыто и
  монтирования нет.
- Второй проект с тем же `code_index_dir`: в `daemon.toml` два `[[paths]]`,
  первый сохранён, порт из `service.json`, обе базы доступны по alias.
- Откат при ошибке: карточки/проект/регистрация удалены, общий сервис жив,
  новый сервис остановлен, контейнер и тома оставлены.
- `pytest app/tests -q` и `pytest benchmark/tests -q` зелёные.
- Изменения закоммичены локально в `main`, push не выполняется.

## Тестирование

- `app/tests/env/test_code_index_project.py` — валидация путей, выбор порта,
  создание/переиспользование карточки, локальный wait.
- `app/tests/env/test_code_index_docker.py` — deploy (fake `DockerProvisioner`:
  `copy_in`, `exec_detached`, `run`), merge `daemon.toml`, wait ready/error/timeout,
  stop.
- `app/tests/env/test_agent_setup.py` — claude/claude-ds/claude-local/прочее,
  копирование ключа, Strata-настройки, LF/права.
- `app/tests/test_backend_docker.py` — argv контейнера (тома, сеть по ОС,
  лицензии), `exec_run(env=...)`, `exec_detached`, `copy_in`, seed trust.
- `app/tests/env/test_project_api.py` — создание local/docker с code index,
  валидация (ssh/license_dir), дефолт каталога лицензий в
  `/api/env/projects/requirements` для Linux/Windows (monkeypatch `os.name`/
  `platform.system()`), откат, отсутствие изменений при update-env.
- `app/tests/env/test_project_wizard_page.py` — чекбокс, поля, автозаполнение,
  дефолты по backend, скрытие для ssh/update, поле лицензий.
- `app/tests/env/test_mcp_types.py` — скрытый вид `code-index-docker`, нет
  host-действия; `test_mcp_page.py` — карточка без кнопки развёртывания.
- `app/tests/env/test_bench_setup.py` — не ломается от расширений
  `DockerProvisioner` (benchmark использует его же).

## Вне области

- Code index для SSH-проектов.
- Дооснащение code index уже созданных проектов и update-env.
- Управление сервисом code-index docker-проекта со страницы MCP (кнопки
  остановки/перезапуска) — сервис управляется созданием проекта.
- Изменения `deps/code-index-mcp` (upstream).
- Пересоздание существующих docker-контейнеров под новую схему.
- Монтирование репозитория template и хостового `/home/uam`.
- UC/только-чтение лицензий: каталог лицензий монтируется rw, как в benchmark.
- Доступность MCP-серверов, запущенных на хосте, из docker-контейнера на
  Windows: bridge-сеть требует `host.docker.internal` в URL карточки; это
  существующее поведение и в задачу не входит.
- Жизненный цикл code-index при удалении проекта: карточка и сервис остаются
  (удаление проекта и сейчас не трогает контейнер).
- Отдельный контейнер на проект при совпадающем пути: как и сейчас, путь
  docker-проекта должен быть уникальным (по умолчанию `/workspace`); схема
  `/workspace/<имя проекта>` не вводится.

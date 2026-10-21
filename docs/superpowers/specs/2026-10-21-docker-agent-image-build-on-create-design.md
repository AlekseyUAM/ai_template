# Сборка docker-образа агента «по кнопке» при создании проекта

Дата: 2026-10-21
Статус: согласован

## Проблема

При создании проекта с размещением в Docker пользователь (запускающий agent
monitor) ничего не знает про то, что где-то заранее нужно собрать образ
`ai1c-agent:latest`. Сейчас:

- образ один на всех (константа `DEFAULT_IMAGE = "ai1c-agent:latest"`,
  `app/src/agentmon/backends/docker.py:23`), платформа 1С вшита в него;
- хук сборки `_DockerContainer._build()` (`docker.py:248`) просто кидает
  ошибку «образ не найден; соберите тулкит-образ из deps/docker_1c_sandbox»;
- путь к дистрибутиву платформы задаётся только в `deps/docker_1c_sandbox/.env`
  (`ONEC_DISTR_PATH`) и используется ручным скриптом `setup_sandbox.py` +
  VS Code DevContainers — вне флоу agent monitor.

Итог: в мастере создания проекта негде указать дистрибутив, а сборка образа —
отдельный ручной ритуал, про который пользователь не осведомлён.

Дополнительно обнаружено (портируемость на другой компьютер):

- весь каталог `deps/docker_1c_sandbox` исключён из репозитория `ai_template`
  правилом `.gitignore:4: /deps/*` и не является сабмодулем — на чистом клоне
  его нет вовсе;
- внутри `deps/docker_1c_sandbox` нужные Dockerfile'у сабмодули
  (`1c-agent-based-dev-framework`, `mcp-bsl-lsp-bridge`, `1c-batch-py`) не
  выкачаны.

## Решение (общая идея)

Фича живёт целиком в `ai_template` и **не зависит** от `deps/docker_1c_sandbox`.
Пишем собственный минимальный Dockerfile, который умеет ровно одно: установить
платформу 1С из указанного дистрибутива и дать рантайм для запуска агента. Сам
проект заезжает в контейнер в рантайме (уже делает `DockerProvisioner.put_tree`),
а не в образ.

По кнопке «Создать проект»:

- если образ нужной версии платформы уже есть — используется готовый (секунды);
- если образа нет — сначала собирается образ из указанного дистрибутива (лог
  льётся в тот же поток, что и лог создания проекта), затем разворачивается проект.

Образ тегируется версией платформы (`ai1c-agent:<версия>`) и переиспользуется
между проектами с той же версией.

## Решённые развилки (зафиксированы с пользователем)

1. **Стратегия образа:** переиспользовать по версии платформы. Тег
   `ai1c-agent:<версия>`; собираем только если образа этой версии нет.
2. **Обязательность поля дистрибутива:** обязательно только если образа нужной
   версии ещё нет; есть образ — поле скрыто/неактивно.
3. **Docker-демон:** поддержать и локальный, и удалённый (`docker -H ssh://...`).
4. **Зависимость от deps:** убрать полностью. Свой Dockerfile в `ai_template`.
5. **Объём образа:** лёгкий — только платформа 1С и рантайм агента. Без
   фреймворка, bsl-lsp-bridge, test-runner, Vanessa, без вшитого template.

## Компоненты

### 1. Собственный Dockerfile — `app/docker/agent-image/Dockerfile`

Минимальный, без зависимостей от `deps`:

- базовый образ Ubuntu 22.04;
- apt: системные библиотеки платформы 1С (libwebkit2gtk, libfontconfig1,
  libfreetype6, libcups2, libgtk-3-0, libglu1-mesa, libodbc2, шрифты и прочее —
  выжимка из текущего sandbox-Dockerfile), `xvfb`, `locales`, `curl`, `unzip`,
  `nodejs` (NodeSource 20.x), `python3`, `python-is-python3`;
- генерация локали `ru_RU.UTF-8` + `LANG`/`LC_ALL`;
- `npm install -g @anthropic-ai/claude-code` (агент запускается командой
  `claude` внутри контейнера через `DockerRunner`);
- `COPY` дистрибутива из build-контекста → `unzip` → поиск `*.run` →
  `*.run --mode unattended --enable-components server,server_admin,client_full,ru`
  → очистка;
- симлинк `/opt/1cv8/current -> /opt/1cv8/<arch>/<версия>`;
- `ENV PATH="/opt/1cv8/current:$PATH"`, `LANG`, `LC_ALL`.

Содержимое образа: ОС + системные зависимости + `xvfb` + `ru`-локаль +
Claude Code CLI + установленная платформа 1С. Больше ничего.

### 2. Модуль сборки — `app/src/agentmon/env/docker_image.py` (новый)

Функции:

- `image_tag(platform_version) -> str` — `ai1c-agent:<sanitized_version>`
  (нормализация: только `[a-z0-9_.-]`, по аналогии с `container_name`).
- `image_exists(tag, docker_host=None) -> bool` — через
  `docker [-H <host>] images -q <tag>` (паттерн уже есть в
  `_DockerContainer.ensure`, `docker.py:280`).
- `build_agent_image(distr_path, platform_version, docker_host=None, log_cb=None)`
  — выполняет сборку:
  - build-контекст = каталог, содержащий дистрибутив (многогигабайтный `.zip`
    не копируется; при необходимости — временный каталог с hardlink на
    дистрибутив, чтобы не раздувать контекст);
  - `docker [-H <host>] build -t <tag> -f app/docker/agent-image/Dockerfile <context>`;
  - стрим stdout/stderr построчно через `log_cb` (для `create/stream`);
  - ретраи на транзиентных сетевых ошибках (паттерн из
    `setup_sandbox.run_docker_with_retry` — переносится как своя функция, без
    импорта из deps).

Модуль не импортирует ничего из `deps/docker_1c_sandbox`.

### 3. API — `app/src/agentmon/env/project_api.py`

- Новый эндпоинт `POST /api/env/projects/check-image`:
  - вход: `platform_version`, `backend`, `conn`;
  - выход: `{ "exists": bool, "tag": str }`;
  - мастер по нему решает, обязательно ли поле дистрибутива.
- `_prepare_install` (для `backend == "docker"`):
  - `tag = image_tag(platform_version)`; записать `conn["image"] = tag` (фабрика
    подхватит — `factory.py:23`);
  - `platform_dir` остаётся дефолтным `/opt/1cv8/current` (текущий шим
    `project_api.py:110-113` сохраняется);
  - вычислить `docker_host` из `conn`;
  - если `not image_exists(tag, docker_host)` и `not body.get("distr_path")` →
    `HTTPException(400, "для docker нужно указать путь к дистрибутиву ...")`.
- Шаг сборки: если образа нет — вызвать `build_agent_image(...)` первым шагом
  создания (и в блокирующем `create`, и в `create/stream`), до разворачивания
  контейнера. В стриминговом варианте вывод сборки идёт в тот же генератор лога.

### 4. Мастер (web)

- При выборе docker-бэкенда — поле «Путь к дистрибутиву платформы (.zip)».
- После ввода версии платформы (и выбора демона) мастер дёргает
  `check-image`; `exists:false` → поле обязательно; `exists:true` →
  поле скрыто/неактивно.
- `distr_path` уходит в теле запроса `create` / `create/stream`.

### 5. Бэкенд — `app/src/agentmon/backends/`

- Тег образа уже течёт через `project.conn["image"]` (`factory.py:23`) —
  правок в `factory.py`/`docker.py` по сути нет.
- Хук `_DockerContainer._build()` оставляем предохранителем с понятным
  сообщением (к моменту `ensure()` образ уже собран явным шагом создания).

## Что НЕ меняется

- `deps/docker_1c_sandbox`, `setup_sandbox.py`, VS Code DevContainers-путь —
  не трогаем (остаются для ручного сценария, но фича от них не зависит).
- Local/ssh-бэкенды — не затрагиваются.
- Схема БД проекта — без изменений (`platform_version` уже есть; `image`
  хранится в `conn` реестра).

## Потоки данных

```
Мастер (web)
  ├─ ввод версии платформы + выбор демона
  ├─ POST check-image ──────────► {exists, tag}
  │     exists:false → показать обязательное поле «дистрибутив»
  └─ POST create/stream { backend:"docker", platform_version, distr_path, conn, ... }
         │
         ▼
project_api._prepare_install
  ├─ conn["image"] = image_tag(platform_version)
  ├─ если образа нет и distr_path пуст → 400
  ▼
create/stream.gen()
  ├─ если образа нет: build_agent_image(distr_path, version, docker_host, log_cb=yield)
  │       docker [-H] build -t ai1c-agent:<ver> -f app/docker/agent-image/Dockerfile <ctx>
  ├─ install_environment(...) → put_tree проекта в контейнер (существующий флоу)
  ▼
registry.add(conn={..., image:"ai1c-agent:<ver>"})
  ▼
BackendRegistry.get(project) → DockerBackend(image=conn["image"])  # factory.py:23
```

## Обработка ошибок

- `distr_path` указан, но файла нет / не `.zip` → `400` до начала сборки.
- `docker build` упал (не транзиентно) → в стрим идёт stderr, создание помечается
  ошибкой (ветка `failed = True` уже есть в `create_project_stream`).
- Транзиентные сетевые ошибки apt/npm/docker pull → ретраи в `build_agent_image`.
- Удалённый демон недоступен → ошибка `docker -H ...` пробрасывается в лог.

## Тестирование

- `image_tag` — нормализация версий (пробелы, спецсимволы, пустая строка).
- `image_exists` — парсинг вывода `images -q` (есть/нет), прокидывание `-H`.
- `build_agent_image` — сборка команды `docker build` (контекст, `-f`, `-t`,
  `-H`), стрим в `log_cb`, ретраи (через инъекцию `run`/фейкового процесса,
  как в существующих тестах бэкендов — без реального докера).
- `check-image` эндпоинт — `exists` true/false, формат ответа.
- `_prepare_install` для docker — проставление `conn["image"]`, `400` при
  отсутствии образа и пустом `distr_path`, `platform_dir` по умолчанию.
- Dockerfile — собираемость проверяется вручную/в интеграционном прогоне
  (юнит-тестами не покрываем).

## Открытые вопросы

Нет.

# Спека: backend `docker` — проект 1С в контейнере

Дата: 2026-10-18. Фаза: 3 (Удалённый доступ). Вторая спека серии (после
«Provisioner за backend + создание проекта по SSH»).

## Контекст и мотивация

Драйвер тот же, что у всей Фазы 3 — многопользовательность/масштаб и изоляция.
Три целевые топологии (монитор в Docker; проект в Docker-контейнере; проект на
удалённом хосте по SSH) — опциональные режимы поверх локального. **Локальный режим
остаётся дефолтом и не меняется по поведению.**

Эта спека покрывает **второй** шаг дорожной карты (`рефакторинг → ssh → docker →
монитор`):

1. (сделано) Рефакторинг: `Provisioner` за backend + создание проекта по SSH.
2. **(эта спека)** Backend `docker` — **execution plane проекта 1С в контейнере**.
3. (следующая спека) Упаковка монитора в Docker.

Плоскости: **control plane** (AgentMon) остаётся на хосте; **execution plane**
(каталог проекта 1С + платформа 1С + агент `claude`) переезжает в Docker-контейнер;
**внешние ресурсы** (тестовая база 1С, сервер лицензий, MCP) — по сети.

## Решения (ответы пользователя)

1. **Чистый контейнер, симметрично SSH.** Файлы 1С-проекта живут **внутри
   контейнера** (в именованном volume `/workspace`), хост их не видит напрямую;
   все операции — через `docker exec`/`docker cp`. `project.path` для docker —
   путь **внутри контейнера** (`/workspace`).
2. **Локальный демон.** Контейнер на том же хосте, что AgentMon; `docker …`
   напрямую. Docker-поверх-SSH — вне скоупа.
3. **В контейнере: проект + тулкит (включая платформу 1С); тулкит берём откуда
   удобно.** → **Переиспользуем готовый образ песочницы `deps/docker_1c_sandbox`**
   (не пишем свой Dockerfile, не кодируем установку платформы). Проект
   разворачивает **свой слой AgentMon** через `Provisioner` (scaffold/content/
   .mcp.json/.venv/git) — ровно как для local/ssh.

## Что переиспользуем из `deps/docker_1c_sandbox` (велосипед не изобретаем)

Песочница — зрелое решение «1С-проект в dev-контейнере». Берём её **тулкит-образ**
и сетевые/томовые соглашения; её VS Code-lifecycle (`init-workspace.sh`/
`start-services.sh` через devcontainer) **не используем** — AgentMon драйвит
контейнер headless сам.

- **Образ** (`project_template/Dockerfile`): платформа 1С установлена headless из
  дистрибутива в `/opt/1cv8/current` (в PATH), **Xvfb** (Конфигуратор 1С требует
  X-дисплей даже headless), `claude` (npm `@anthropic-ai/claude-code`), Node, Java,
  BSL LS, locale `ru_RU.UTF-8`. База образа — `mcr.microsoft.com/devcontainers/
  base:ubuntu-22.04`. Это и есть «тулкит + платформа в образе».
- **Сеть**: bridge + `--add-host=host.docker.internal:host-gateway` (+ при нужде
  hostname хоста / `EXTRA_HOSTS`). База 1С, сервер лицензий, MCP достаются через
  `host.docker.internal`. (Поправка к первоначальной идее `--network=host`: у
  песочницы bridge+add-host, так и делаем.)
- **Том**: именованный, `/workspace` (переживает пересоздание контейнера).
- **Платформа внутри**: фиксированный путь `/opt/1cv8/current` → `platform_dir`
  для docker-проекта известен и не зависит от хоста.
- **Headless**: `DISPLAY=:99` + фоновый `Xvfb :99` обязателен до любого запуска
  `1cv8` (проверка базы, выгрузки). Поднимаем его сами при старте контейнера
  (аналог Xvfb-части `start-services.sh`).

**Источник образа — «откуда удобно»:** `DEFAULT_IMAGE` — фиксированный тег
(напр. `ai1c-agent:latest`), переопределяемый через `conn.image`. Сборку тяжёлого
образа **не переизобретаем**: образ должен быть собран пользователем из
`docker_1c_sandbox` (там дистрибутив платформы, submodule'ы, build-пайплайн). Если
образа нет — `ensure` бросает понятную ошибку с инструкцией собрать его из
песочницы. (Build-from-context — возможный follow-up, не в этой спеке.)

## Текущее состояние (точка отсчёта)

- Backend-абстракция (`backends/__init__.py`): протоколы `AgentRunner`,
  `SessionFiles`, `Provisioner` + `RunResult`; класс `Backend`
  (`runner`/`files`/`provisioner`/`key`, `is_broken`, `check`, `close`).
- `LocalBackend`/`SshBackend` — образцы для зеркала. `SshBackend` особенно:
  `_Connection` (ленивое подключение, окно повторных попыток, `mark_broken`/
  `broken`), `SshProvisioner` (SFTP+exec), `SshRunner` (PTY-канал), `SshFiles`
  (ленивое определение `home` через `normalize(".")`).
- `BackendRegistry` (`backends/factory.py`): `key_for`/`get`; `local`→один на всё,
  `ssh`→один на `user@host:port`. Неизвестный backend → `ValueError`.
- `Project` (`models.py`): `backend` (`local|ssh`), `conn`, `claude_cmd`;
  `key=f"{backend}|{host or ''}|{path}"`.
- Установка (`env/project_api.py` + `env/installer.py`): `_provisioner_for(backend,
  conn)` достаёт provisioner из backend проекта (через `monitor.backends.get`,
  **probe-`Project` c `path=""`**), `install_environment(...)` разворачивает всё
  через `prov`: scaffold→content→venv (+mcp/prepare-src/devbase/git при создании).
- Гейтинг: `dump_cf/dump_cfe/install_tools` — только при `backend=="local"` →
  **для docker пропускаются автоматически** (ничего отключать не нужно).
- `pty_process.spawn(cmd, cwd)` проверяет `isdir(cwd)` на **хосте** → PTY
  docker-агента спавнится с хостовым cwd, каталог проекта задаётся `docker exec -w`.
- `env/mcp_docker.py`: `image_exists`/`status`/`build_cmd`/`iter_output` — берём
  `image_exists`/`status` для инспекции; построение docker-команд контейнера — свои.
- `env/project_checks.py`: `platform_binary(prov, platform_dir)` найдёт
  `/opt/1cv8/current/1cv8`; `check_db(prov, …)` запускает `1cv8 DESIGNER` через
  `prov.run` и пишет лог в `prov.tempdir()`.

## Архитектура решения

Новый модуль `backends/docker.py` — зеркало `ssh.py`: `_DockerContainer`
(идентичность/жизненный цикл) + `DockerProvisioner`/`DockerRunner`/`DockerFiles`/
`DockerBackend`. Один **`DockerBackend` на проект** (ключ реестра включает путь).

### `_DockerContainer` — идентичность и жизненный цикл

Аналог `_Connection`. Держит имя, образ, спецификацию запуска (volume, сеть, env)
и инъектируемый `run=subprocess.run` (тесты — без докера).

- `container_name(path)` — детерминированное имя `ai1c-<slug>` (безопасный слаг +
  короткий хеш пути; `[a-z0-9_.-]`); имя volume — `ai1c-<slug>-work`.
- `ensure()` — лениво (при первой операции provisioner'а и в `start` раннера):
  1. образ есть (`image_exists`)? нет → `RuntimeError` с инструкцией собрать образ
     из `deps/docker_1c_sandbox` (тяжёлую сборку не делаем);
  2. контейнер: `absent` → `docker run -d --name <name> --restart unless-stopped
     --add-host=host.docker.internal:host-gateway -e DISPLAY=:99 -v <vol>:/workspace
     <image> sleep infinity`; `exited` → `docker start`; `running` → ничего;
  3. **Xvfb**: `docker exec -d <name> sh -c 'pgrep -f "Xvfb :99" || setsid Xvfb :99
     -screen 0 1024x768x24 …'` — чтобы `1cv8` работал headless. Идемпотентно.
  При rc≠0 на run/start — `mark_broken()` + `RuntimeError` с логом.
- `exec_run(argv, cwd=None)` → `docker exec [-w cwd] <name> <argv>`; `DISPLAY=:99`
  приходит из env контейнера. Для stdin-ввода (write_bytes) — `exec_input(argv,
  data)` (`docker exec -i … sh -c 'cat > …'`).
- `status()` → `"running"|"exited"|"absent"` (через `docker inspect`).
- `mark_broken`/`broken` — как `_Connection` (окно повторных попыток, `clock`).
- `remove()` → `docker rm -f` (используется в `close`? — **нет**, см. ниже).

### `DockerProvisioner` (протокол `Provisioner`)

Зеркало `SshProvisioner`, транспорт — `docker exec`/`exec_input`. Держит
`_DockerContainer`; пути — внутри контейнера (POSIX). Гарантирует `ensure()` при
первой операции.

- `mkdirs`→`mkdir -p`; `exists`→`test -e`; `is_file`→`test -f`; `is_empty_dir`→
  `test -d`+`ls -A`; `read_text`→`cat`; `write_bytes`→`exec_input sh -c 'cat >
  <quoted>'`; `write_text`=bytes utf-8.
- `put_tree(local_src, dst, skip)` — обход дерева на хосте, фильтр `is_cruft`+
  `skip`, перенос по файлам (симметрично SSH).
- `run(cmd, cwd)`→`exec_run`; `which`→`command -v`; `python_cmd`→`["python3"]`;
  `venv_python`→`<dir>/.venv/bin/python`; `tempdir`→`/tmp`.

### `DockerRunner` (протокол `AgentRunner`)

Агент — внутри контейнера через `docker exec`, PTY локальный. Переиспользуем
`pty_process.spawn`, обернув команду.

- `start(project)`: `container.ensure()`; `spawn("docker exec -it -w /workspace
  <name> <claude_cmd>", cwd=<валидный ХОСТОВЫЙ каталог>)` (дефолт cwd —
  `tempfile.gettempdir()`, **не** `project.path`). `<claude_cmd>` —
  `project.claude_cmd` или дефолт бэкенда.
- `send_input`/`stop`/`is_alive`/`tail_output`/`shutdown_all` — как `LocalRunner`
  (буфер/`_pump`, схлопывание `\r\n`→пробел). `stop(kill)` убивает PTY-процесс
  (`docker exec`); **контейнер не трогаем**. `shutdown_all` — убить PTY агентов.

### `DockerFiles` (протокол `SessionFiles`)

Журналы — `~/.claude/projects` внутри контейнера; через `docker exec`.

- `home` определяется **лениво** (`docker exec <c> sh -c 'echo $HOME'`, кеш при
  успехе), как `SshFiles` через `normalize(".")`: дефолтный пользователь образа
  не угадываем молча.
- `home_projects_dir()`→`<home>/.claude/projects`.
- `list_files(dir)`→`docker exec <c> find <dir> -name '*.jsonl' -printf '%p\t%s\t
  %T@\n'` → `FileRef`. Недоступен контейнер → `[]` (+ `mark_broken`).
- `read_from(path, offset)`→`docker exec <c> tail -c +<offset+1> <path>` →
  `(data, offset+len)`.

### `DockerBackend` + реестр

- `DockerBackend(project_path, *, claude_cmd, image=DEFAULT_IMAGE, run=…,
  spawn_fn=…)`: собирает `_DockerContainer`+Provisioner+Runner+Files;
  `key=f"docker||{project_path}"`; `is_broken`→container.broken; `check`→`ensure`;
  `close`→`shutdown_all` (**контейнер не удаляем** — переживает рестарт монитора).
- `BackendRegistry`: `docker_factory`; `key_for("docker")`→`f"docker||{path}"`
  (один контейнер на проект); `get` ветка docker.

### Интеграция с установкой (`project_api`)

- `_provisioner_for(backend, conn, path)` — **+аргумент `path`**; probe-`Project`
  с реальным путём, чтобы per-project docker-ключ дал provisioner нужного
  контейнера (для local/ssh путь в ключе не участвует — регрессии нет). Обновить
  оба вызова (`check-db`, `_prepare_install`).
- Для `backend="docker"` путь создания работает: валидации (`is_empty_dir`,
  `platform_binary`, `requirements`, `check_db`) и scaffold/content/venv/git — через
  `DockerProvisioner` (в контейнере, Xvfb поднят `ensure`). Контейнер стартует при
  первой операции.
- `platform_dir` для docker — по умолчанию `/opt/1cv8/current` (фикс. в образе).
- `db_connection` для docker: сервер 1С указывается через `host.docker.internal`
  (мастер подсказывает). `license_server`/`nethasp.ini` — как для ssh, через prov.
- `dump_cf/dump_cfe/install_tools` — остаются выключенными (гейт `is_local`),
  **без изменений**; включение по docker — follow-up.

### Мастер (web)

- «Размещение»: + `В Docker-контейнере` (`value="docker"`). `syncBackend`
  показывает docker-поля (опц. образ) и скрывает ssh-поля; `platform_dir`
  предзаполняется `/opt/1cv8/current`; `path` — `/workspace`.
- `readConn()`: docker → `{image?}` или `{}`.

## Границы (YAGNI)

- **Сборку тулкит-образа не переизобретаем** — образ готовит пользователь из
  `deps/docker_1c_sandbox`; `ensure` при отсутствии даёт понятную ошибку.
- **VS Code-lifecycle песочницы (init-workspace/start-services через
  devcontainer) не используем** — берём только Xvfb-часть вручную.
- **Docker-поверх-SSH**, **выгрузка cf/cfe и tools по docker**, **update-env для
  docker**, **персистентность `~/.claude` между пересозданиями контейнера** —
  вне скоупа (follow-up).

## Поток данных (создание docker-проекта)

1. Мастер: `backend="docker"`, `conn={image?}`, `path="/workspace"`,
   `platform_dir="/opt/1cv8/current"`, `db_*` (сервер через host.docker.internal),
   `license_server`.
2. `project_api` → `_provisioner_for("docker", conn, path)` → `DockerBackend` →
   `DockerProvisioner`.
3. Первая операция → `ensure`: образ есть? контейнер run/start; Xvfb up.
4. Валидации через `docker exec` в контейнере; лог в UI.
5. scaffold→content→.mcp.json→.venv→devbase→nethasp→git — через `docker exec`/cp.
6. Регистрация; запуск агентов (`docker exec -it … claude`) и JSONL (`find/tail`).

## Обработка ошибок

- Демон/контейнер недоступен: `_DockerContainer` → `broken` (окно повторов),
  `is_broken` наверх; `list_files`→`[]`, `is_alive`→`False`.
- Образа нет → `ensure` бросает с инструкцией собрать из песочницы → лог создания.
- `run` rc≠0 (venv/git/check в контейнере) → stderr в лог, установка прервана.

## Тестируемость

- Весь слой — через инъекции `run`/`spawn_fn`, **без реального докера** (`FakeRun`
  из `tests/env/test_mcp_docker.py`, fake spawn из `tests/test_backend_local.py`).
- `_DockerContainer`: ensure absent→`docker run` с верными argv (add-host, `-v
  vol:/workspace`, `sleep infinity`) + Xvfb-exec; exited→start; running→ничего;
  образа нет→`RuntimeError`; `mark_broken`/окно; `exec_run`/`exec_input` argv.
- `DockerProvisioner`: команды exec; put_tree фильтрует cruft/skip; is_empty_dir.
- `DockerRunner`: обёрнутая команда `docker exec -it -w /workspace <name>
  <claude>` + хостовый cwd; буфер/kill.
- `DockerFiles`: ленивый home (`echo $HOME`), разбор `find -printf`, `read_from`.
- `DockerBackend`/реестр: `key_for` per-path; кеш; `close` не вызывает `docker rm`.
- Создание: `tests/env/test_docker_create.py` по образцу `test_ssh_create.py`
  (фейковый docker-backend/контейнер): scaffold/deploy/venv/git через `docker
  exec`, dumps/tools пропущены, проект зарегистрирован.

## Единицы (модульность)

- `app/src/agentmon/backends/docker.py` — **новый**: `_DockerContainer`,
  `DockerProvisioner`, `DockerRunner`, `DockerFiles`, `DockerBackend`,
  `DEFAULT_IMAGE="ai1c-agent:latest"`, `WORKDIR="/workspace"`, `container_name`.
- `app/src/agentmon/backends/factory.py` — docker_factory, `key_for`/`get`.
- `app/src/agentmon/models.py` — docstring `backend` (`local|ssh|docker`).
- `app/src/agentmon/env/project_api.py` — `_provisioner_for(..., path)`; docker-ветка.
- `app/web/project-wizard.html`/`.js` — опция docker, поля, дефолты.
- `docs/PHASES.md` — «Docker-бэкенд» → «Реализовано» (+ ссылка на образ песочницы).
- Тесты: `app/tests/test_backend_docker.py`, `app/tests/env/test_docker_create.py`.

## Открытые вопросы

Нет. Тулкит-образ (включая платформу) — из `deps/docker_1c_sandbox`, готовит
пользователь; сборку не переизобретаем. Сеть/том/Xvfb/путь платформы зафиксированы
по образцу песочницы.

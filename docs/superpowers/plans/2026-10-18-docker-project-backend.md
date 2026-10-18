# Backend `docker` — проект 1С в контейнере — План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend `docker` — execution plane проекта 1С (каталог + платформа + агент `claude`) в Docker-контейнере на **локальном** демоне, модель «чистый контейнер» (файлы в контейнере, всё через `docker exec`/`cp`), симметрично SSH. Тулкит-образ (включая платформу 1С, Xvfb, claude) **переиспользуем из `deps/docker_1c_sandbox`** — свой Dockerfile не пишем. Проект разворачивает **свой слой AgentMon** через `Provisioner`. Local и ssh по поведению не меняются.

**Architecture:** Новый модуль `backends/docker.py` — зеркало `ssh.py`: `_DockerContainer` (идентичность/жизненный цикл, аналог `_Connection`, + headless Xvfb) + `DockerProvisioner`/`DockerRunner`/`DockerFiles`/`DockerBackend`. Один `DockerBackend` на проект (ключ реестра включает путь). Образ — готовый тег `ai1c-agent:latest` (переопределяется `conn.image`), собирается пользователем из песочницы; при отсутствии `ensure` бросает понятную ошибку (тяжёлую сборку не переизобретаем). Сеть bridge + `--add-host=host.docker.internal:host-gateway`, том `/workspace`, платформа `/opt/1cv8/current`. Создание проекта для docker проходит через тот же `install_environment`, provisioner — `DockerProvisioner`.

**Tech Stack:** Python 3.10+, dataclasses, `typing.Protocol`, subprocess (docker CLI), `pty_process.spawn` (PTY поверх `docker exec -it`), pytest. Реальный Docker в тестах не нужен — `run`/`spawn_fn` инъектируются фейками.

## Global Constraints

- Python **3.10+** (`str | None`).
- **Local и ssh не меняются** — docker добавляется третьей веткой (регрессия — зелёные прежние тесты).
- Цель контейнера — **Linux**: POSIX-пути, `python3`, venv `.venv/bin/python`.
- **Сеть**: bridge + `--add-host=host.docker.internal:host-gateway` (НЕ `--network=host`). База/лицензии/MCP — через `host.docker.internal`.
- **Том** именованный → `/workspace`; `project.path` для docker = `/workspace`.
- **Платформа** в образе: `/opt/1cv8/current` (фикс.), `platform_dir` по умолчанию для docker.
- **Xvfb обязателен**: `1cv8` (DESIGNER) требует X-дисплей даже headless. `ensure` поднимает `Xvfb :99` (`DISPLAY=:99` в env контейнера) до любых 1cv8-команд.
- `project.path` — путь в контейнере; каталог задаётся `docker exec -w`, а PTY спавнится с **хостовым** cwd (`_PosixPty` проверяет `isdir(cwd)` на хосте).
- Контейнер — **служебный долгоживущий** (`docker run -d … sleep infinity`); агент/команды входят через `docker exec`. `close`/`shutdown_all` **не удаляют** контейнер.
- **Тулкит-образ не собираем**: `ensure` при отсутствии образа бросает `RuntimeError` с инструкцией собрать его из `deps/docker_1c_sandbox`.
- Русскоязычные docstring в стиле кода. Переиспользовать `mcp_docker.image_exists`/`status`.
- Тесты: из `app/` — `/home/uam/projects/ai_template/.venv/bin/python -m pytest -q`. Один файл: `… -m pytest tests/<файл> -v`. Baseline ~771 green, не регрессировать.
- Коммиты — атомарные по задаче, русские сообщения в стиле репозитория; коммит в локальный `master` после двухстадийного ревью.

---

## Файловая структура

- `app/src/agentmon/backends/docker.py` — **новый**: `_DockerContainer`, `DockerProvisioner`, `DockerRunner`, `DockerFiles`, `DockerBackend`, `DEFAULT_IMAGE="ai1c-agent:latest"`, `WORKDIR="/workspace"`, `container_name(path)`.
- `app/src/agentmon/backends/factory.py` — docker_factory, `key_for`/`get` для docker.
- `app/src/agentmon/models.py` — docstring `backend` (`local|ssh|docker`).
- `app/src/agentmon/env/project_api.py` — `_provisioner_for(backend, conn, path)`; docker-ветка; `platform_dir` по умолчанию.
- `app/web/project-wizard.html`, `app/web/project-wizard.js` — опция docker.
- `docs/PHASES.md` — «Docker-бэкенд» → «Реализовано» (ссылка на образ песочницы).
- Тесты: `app/tests/test_backend_docker.py`, `app/tests/env/test_docker_create.py`.

---

## Task 1: `_DockerContainer` — идентичность, жизненный цикл, Xvfb

**Files:** Create `app/src/agentmon/backends/docker.py` (начало); Test `app/tests/test_backend_docker.py` (класс контейнера).

**Interfaces (produces):**
- `DEFAULT_IMAGE = "ai1c-agent:latest"`, `WORKDIR = "/workspace"`.
- `container_name(path) -> str` — `ai1c-<slug>` (безопасный слаг basename + короткий hashlib-хеш полного пути; только `[a-z0-9_.-]`); volume — `f"{name}-work"`.
- `class _DockerContainer(name, image, *, volume, workdir=WORKDIR, run=subprocess.run, clock=time.monotonic, retry_seconds=10.0)`:
  - `status() -> "running"|"exited"|"absent"` (через `docker inspect -f '{{.State.Status}}'`; rc≠0 → absent).
  - `ensure()`: (1) `mcp_docker.image_exists(image, run=...)` False → `RuntimeError` с текстом «образ <image> не найден; соберите тулкит-образ из deps/docker_1c_sandbox»; (2) по статусу: absent → `docker run -d --name <name> --restart unless-stopped --add-host=host.docker.internal:host-gateway -e DISPLAY=:99 -v <volume>:<workdir> <image> sleep infinity`; exited → `docker start <name>`; running → ничего; rc≠0 → `mark_broken()`+`RuntimeError(log)`; (3) Xvfb: `docker exec -d <name> sh -c 'pgrep -f "Xvfb :99" >/dev/null 2>&1 || setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1'` (идемпотентно).
  - `exec_run(argv, cwd=None) -> RunResult` — `docker exec [-w cwd] <name> <argv>`.
  - `exec_input(argv, data: bytes) -> RunResult` — `docker exec -i <name> <argv>`, подать `data` в stdin (для write_bytes).
  - `mark_broken()`/`broken` — как `_Connection.mark_broken` (идемпотентно, окно повторов на `clock`/`retry_seconds`).
  - `remove()` — `docker rm -f <name>` (НЕ вызывается из close; только явно).

**Steps:**
- [ ] Step 1: Модуль, импорты (`from . import RunResult, is_cruft, BUFFER_LIMIT`; `from ..env import mcp_docker`), константы, `container_name`.
- [ ] Step 2: `__init__` + `status` + `mark_broken`/`broken`.
- [ ] Step 3: `ensure` (образ-гард → run/start → Xvfb), обработка rc≠0.
- [ ] Step 4: `exec_run`/`exec_input`/`remove`.
- [ ] Step 5: Тесты (`FakeRun`, различает `docker inspect`/`images -q`/`run`/`start`/`exec`): absent→run c верными argv + Xvfb-exec; exited→start; running→ничего; нет образа→RuntimeError; mark_broken/окно; exec_run `-w`; exec_input stdin.

**Verification:** `… pytest tests/test_backend_docker.py -v` зелёные.

---

## Task 2: `DockerProvisioner` (протокол `Provisioner`)

**Files:** Modify `backends/docker.py`; Test — класс provisioner.

**Interfaces:** `class DockerProvisioner(container, workdir=WORKDIR)` — методы `Provisioner`: `mkdirs`(`mkdir -p`), `exists`(`test -e`), `is_file`(`test -f`), `is_empty_dir`(`test -d`+`ls -A`), `read_text`(`cat`), `write_text`/`write_bytes`(`exec_input sh -c 'cat > <quoted>'`), `put_tree(local_src, dst, skip=None)` (обход на хосте, `is_cruft`+skip, перенос по файлам), `run(cmd, cwd=None)`(`exec_run`), `which`(`command -v`), `python_cmd`→`["python3"]`, `venv_python`→`"{dir}/.venv/bin/python"`, `tempdir`→`"/tmp"`. Первая операция вызывает `container.ensure()`.

**Steps:**
- [ ] Step 1: файловые операции через exec/exec_input.
- [ ] Step 2: `put_tree` (симметрично `SshProvisioner.put_tree`, фильтр `is_cruft`+skip).
- [ ] Step 3: `run`/`which`/`python_cmd`/`venv_python`/`tempdir` + `ensure` на входе.
- [ ] Step 4: Тесты (фейк-контейнер пишет argv+stdin): команды верные; put_tree пропускает `__pycache__`/`.egg-info`/skip; is_empty_dir пусто/непусто/файл.

**Verification:** `… pytest tests/test_backend_docker.py -v`.

---

## Task 3: `DockerRunner` (протокол `AgentRunner`)

**Files:** Modify `backends/docker.py`; Test — класс runner.

**Interfaces:** `class DockerRunner(container, claude_cmd, workdir=WORKDIR, spawn_fn=pty_process.spawn, host_cwd=None)` — `AgentRunner`. `start(project)`: `container.ensure()`; `spawn(f"docker exec -it -w {workdir} {name} {claude_cmd}", cwd=host_cwd or tempfile.gettempdir())` (НЕ `project.path`). Остальное — как `LocalRunner` (буфер/`_pump`, `\r\n`→пробел; `kill` убивает PTY, контейнер не трогаем).

**Steps:**
- [ ] Step 1: `start` (обёрнутая команда + хостовый cwd; idемпотентность).
- [ ] Step 2: `send_input`/`stop`/`is_alive`/`tail_output`/`shutdown_all` по образцу `LocalRunner`.
- [ ] Step 3: Тесты (fake spawn): команда `docker exec -it -w /workspace <name> <claude>`, хостовый cwd валиден, буфер, kill.

**Verification:** `… pytest tests/test_backend_docker.py -v`.

---

## Task 4: `DockerFiles` (протокол `SessionFiles`)

**Files:** Modify `backends/docker.py`; Test — класс files.

**Interfaces:** `class DockerFiles(container, home=None)` — `home` лениво через `docker exec <c> sh -c 'echo $HOME'` (кеш при успехе, неудачу не кешируем — как `SshFiles`); `home_projects_dir()`→`<home>/.claude/projects`; `list_files(dir)`→`find <dir> -name '*.jsonl' -printf '%p\t%s\t%T@\n'`→`FileRef` (dir_name — подкаталог, session_id — без `.jsonl`); `read_from(path, offset)`→`tail -c +<offset+1>`→`(data, offset+len)`. Недоступность → `[]`/`(b"", offset)` + `mark_broken`.

**Steps:**
- [ ] Step 1: ленивый `home` + `home_projects_dir` + `list_files` (парсинг `find`, аккуратно к `\t`/пустому/rc≠0).
- [ ] Step 2: `read_from` (offset через `tail -c`), отказы.
- [ ] Step 3: Тесты: фейк-вывод `find` → `FileRef`; `read_from` offset; пусто → `[]`; home определяется один раз.

**Verification:** `… pytest tests/test_backend_docker.py -v`.

---

## Task 5: `DockerBackend` + реестр + models docstring

**Files:** Modify `backends/docker.py`, `backends/factory.py`, `models.py`; Test — backend/registry.

**Interfaces:** `class DockerBackend(Backend)` — собирает `_DockerContainer`+Provisioner+Runner+Files; `key=f"docker||{project_path}"`; `is_broken`→container.broken; `check`→`ensure`; `close`→`shutdown_all` (контейнер НЕ удаляем). `BackendRegistry`: `docker_factory` (дефолт `lambda project: DockerBackend(project.path, claude_cmd=self.claude_cmd, image=(project.conn or {}).get("image") or DEFAULT_IMAGE)`); `key_for("docker")`→`f"docker||{project.path}"`; `get` ветка docker.

**Steps:**
- [ ] Step 1: `DockerBackend.__init__`/`is_broken`/`check`/`close`; имя контейнера/volume из `project_path`.
- [ ] Step 2: `factory.py` — `docker_factory`, `key_for`/`get` для docker.
- [ ] Step 3: `models.py` docstring `backend` → `"local" | "ssh" | "docker"`.
- [ ] Step 4: Тесты: `key_for` docker per-path; кеш (один путь → один бэкенд, другой путь → другой); `close` не вызывает `docker rm`.

**Verification:** `… pytest tests/test_backend_docker.py -v` + регрессия `tests/test_backend_*.py`.

---

## Task 6: Интеграция создания проекта (`project_api`) + e2e-тест

**Files:** Modify `env/project_api.py`; Test `app/tests/env/test_docker_create.py`.

**Interfaces:** `_provisioner_for(backend, conn, path)` — +`path`; probe-`Project(path=path)`; обновить оба вызова (`check-db`, `_prepare_install`). Для `backend="docker"` создание работает через `DockerProvisioner`; `platform_dir` по умолчанию `/opt/1cv8/current` если мастер прислал пусто для docker. `dump_cf/dump_cfe/install_tools` — без изменений (гейт `is_local` оставляет их off).

**Steps:**
- [ ] Step 1: сигнатура `_provisioner_for` + probe с путём; оба вызова.
- [ ] Step 2: docker-ветка `get`→`DockerBackend`.provisioner; `platform_dir` дефолт для docker при пустом.
- [ ] Step 3: `test_docker_create.py` по образцу `test_ssh_create.py` (фейковый docker-backend/контейнер через инъекцию `docker_factory`/`run`): создание `backend="docker"` → scaffold/content/venv/git через `docker exec`, dumps/tools пропущены, проект зарегистрирован.

**Verification:** `… pytest tests/env/test_docker_create.py -v` + регрессия `tests/env/test_project_api*.py`.

---

## Task 7: Мастер (web) + PHASES.md

**Files:** Modify `app/web/project-wizard.html`, `app/web/project-wizard.js`, `docs/PHASES.md`; при необходимости `app/tests/env/test_project_wizard_page.py`.

**Interfaces:** «Размещение» → опция `В Docker-контейнере` (`value="docker"`); `syncBackend` для трёх режимов (docker-поля — опц. образ; ssh-поля скрыты); при docker предзаполнить `platform_dir=/opt/1cv8/current` и `path=/workspace`. `readConn()` docker → `{image}` или `{}`. `docs/PHASES.md`: «Docker-бэкенд» → «Реализовано» (чистый контейнер, локальный демон, тулкит-образ из `deps/docker_1c_sandbox`, bridge+host.docker.internal, Xvfb; dumps/tools/docker-over-ssh/update-env — follow-up).

**Steps:**
- [ ] Step 1: HTML — опция + docker-блок (скрываемый, как `sshFields`).
- [ ] Step 2: JS — `syncBackend` на три режима; `readConn` docker; предзаполнение `platform_dir`/`path`.
- [ ] Step 3: PHASES.md.
- [ ] Step 4: тест страницы при необходимости.

**Verification:** `… pytest -q` (полный прогон зелёный).

---

## Финал

- [ ] Полный `… pytest -q` из `app/` — зелёный (включая регрессию local/ssh).
- [ ] Финальное ревью всей ветки (opus): жизненный цикл контейнера (incl. Xvfb), отсутствие регрессий local/ssh, безопасность команд (argv/quoting), обработка отказов docker, соответствие соглашениям песочницы (сеть/том/платформа).
- [ ] Каждая задача — атомарный коммит в локальный `master` после двухстадийного ревью.

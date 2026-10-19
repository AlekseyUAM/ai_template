# Docker-поверх-SSH (контейнер проекта на удалённом демоне) — План

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Позволить docker-бэкенду целиться в УДАЛЁННЫЙ docker-демон через `docker -H ssh://user@host` — контейнер проекта на другом хосте, команды/JSONL/PTY уходят туда по ssh. Локальный docker-режим (`docker_host=None`) не меняется.

**Architecture:** `_DockerContainer` получает опциональный `docker_host`; хелпер `_argv()` вставляет `-H <docker_host>` во все docker-команды; `DockerRunner` — в спавн-строку `docker exec -it`. `DockerBackend`/`factory` выводят `docker_host` из `conn` и включают host в ключ. Мастер — поля удалённого демона.

**Tech Stack:** Python 3.10+, docker CLI ssh-helper, pytest. Без реального docker/ssh — инъекция run/spawn.

## Global Constraints
- **Локальный docker/ssh/local не меняются**: `docker_host=None` → docker-argv и ключ `docker||{path}` байт-в-байт как сейчас (регрессия — зелёные существующие docker-тесты).
- Аутентификация ssh — agent/`~/.ssh/config` (docker ssh-helper); `key_path` в URL не поддерживаем.
- Образ-тулкит — на удалённом демоне (не собираем).
- Русские docstring; коммиты атомарные в master после двухстадийного ревью.
- Тесты из `app/`: `-k "not install_stops_on_dump_error"` для быстрого полного прогона.

## Файлы
- `app/src/agentmon/backends/docker.py` — `_argv`/`docker_host`/замена 8 сайтов/image-check/runner `-H`/DockerBackend docker_host+key/conn→docker_host.
- `app/src/agentmon/backends/factory.py` — docker_factory docker_host; key_for docker с host.
- `app/web/project-wizard.html`/`.js` — поля удалённого демона.
- `docs/PHASES.md`, `docs/DEPLOY-DOCKER.md`.
- Тесты: `test_backend_docker.py`, `test_backend_factory.py`, wizard-тест.

---

## Task 1: `_DockerContainer` — `-H <docker_host>` во всех командах

**Files:** Modify `backends/docker.py`; Test `app/tests/test_backend_docker.py`.

**Interfaces:**
- `__init__(..., docker_host: str | None = None)` → `self._docker_host`; `@property docker_host`.
- `_argv(tail: list[str]) -> list[str]` → `["docker"] + (["-H", self._docker_host] if self._docker_host else []) + tail`.
- Заменить все 8 `["docker", …]` (inspect/run/start/xvfb-exec/exec_run/exec_input/exec_run_bytes/rm) на `self._argv([...])`.
- Проверку образа в `ensure` делать через `self._run(self._argv(["images","-q",self._image]), capture_output=True, text=True)` (rc 0 + непустой stdout → образ есть), вместо `mcp_docker.image_exists`. `_build` остаётся хуком-исключением. (Удалить импорт mcp_docker, если больше не нужен.)

**Steps:**
- [ ] Step 1: `docker_host` + `_argv` + property.
- [ ] Step 2: заменить 8 сайтов; image-check через `_argv`.
- [ ] Step 3: Тесты: с `docker_host="ssh://u@h"` каждая команда содержит `-H ssh://u@h` сразу после `docker` (inspect/run/start/xvfb/exec_run/exec_input/exec_run_bytes/rm/images); с `None` — argv как раньше (регресс существующих ensure-тестов — они строят контейнер без docker_host, должны остаться зелёными).

**Verification:** `… pytest tests/test_backend_docker.py -v`; полный фильтрованный без регрессий.

---

## Task 2: `DockerRunner` — `-H` в PTY-команде

**Files:** Modify `backends/docker.py`; Test `app/tests/test_backend_docker.py`.

**Interfaces:** `start`: `dh = self._container.docker_host`; `host_flag = f" -H {shlex.quote(dh)}" if dh else ""`; спавн-строка `f"docker{host_flag} exec -it -w {shlex.quote(workdir)} {shlex.quote(name)} {cmd}"`. Локально (`dh=None`) — как сейчас.

**Steps:**
- [ ] Step 1: вставить host_flag в start.
- [ ] Step 2: Тесты: удалённый контейнер → спавн-строка `docker -H ssh://u@h exec -it …`; локальный → без `-H` (регресс существующего runner-теста).

**Verification:** `… pytest tests/test_backend_docker.py -v`.

---

## Task 3: `DockerBackend` + factory — conn→docker_host, ключ с host

**Files:** Modify `backends/docker.py`, `backends/factory.py`; Test `app/tests/test_backend_docker.py`, `test_backend_factory.py`.

**Interfaces:**
- Хелпер `docker_host_from_conn(conn: dict | None) -> str | None`: `conn.get("docker_host")` если есть; иначе если `conn.get("host")` → `"ssh://" + (f"{user}@" if user else "") + host + (f":{port}" if port else "")`; иначе None. (Разместить в docker.py.)
- `DockerBackend.__init__(..., docker_host=None)` → прокинуть в `_DockerContainer`; `key`: локально (`docker_host=None`) → `f"docker||{project_path}"` (как сейчас); удалённо → включить host: `f"docker|{host}|{project_path}"` (host из conn/docker_host — чтобы совпадать с `models.Project.key`).
- `factory`: `docker_factory` вычисляет `docker_host = docker_host_from_conn(project.conn)` и передаёт; `key_for(docker)` → `f"docker|{project.host or ''}|{project.path}"` (локально host пуст → `docker||{path}`).

**Steps:**
- [ ] Step 1: `docker_host_from_conn`.
- [ ] Step 2: DockerBackend docker_host + key; factory docker_factory + key_for.
- [ ] Step 3: Тесты: conn-разбор (docker_host / host+user+port / host / пусто); удалённый ключ `docker|{host}|{path}`, локальный `docker||{path}`; два проекта на одном пути разных демонов → разные бэкенды; `DockerBackend(docker_host=...)` строит контейнер с `-H`.

**Verification:** `… pytest tests/test_backend_docker.py tests/test_backend_factory.py -v`; полный фильтрованный.

---

## Task 4: Мастер (web) + проверка project_api

**Files:** Modify `app/web/project-wizard.html`/`.js`; verify `env/project_api.py`; Test wizard.

**Interfaces:**
- docker-блок мастера: + необязательные поля удалённого демона (хост, пользователь, порт — или одно поле `docker_host`). Пусто → локальный демон.
- `readConn` docker → `{image?, host?, user?, port?}` (или `{docker_host?}`), прикрепляется как conn.
- Проверить, что `project_api` создание/валидации удалённого docker проходят через provisioner без доп. правок (вероятно да); если нужен минимум — внести.

**Steps:**
- [ ] Step 1: HTML docker-поля демона.
- [ ] Step 2: JS readConn docker-ветка (демон); предзаполнение/валидация минимум.
- [ ] Step 3: Проверить project_api (smoke: создание docker с conn.host → prov нацелен на remote). Правки при необходимости.
- [ ] Step 4: wizard-тест (поля присутствуют; readConn отдаёт демон).

**Verification:** `… pytest -q -k "not install_stops_on_dump_error"` зелёный.

---

## Task 5: Документация + финальная чистка

**Files:** Modify `docs/PHASES.md`, `docs/DEPLOY-DOCKER.md`; cleanup `env/project_api.py`+`api.py`+тесты.

**Steps:**
- [ ] Step 1: PHASES — «Docker-поверх-SSH» → «Реализовано» (из «Следующих шагов»); описать `conn.docker_host`/`host`, образ на удалённом демоне, ssh-agent.
- [ ] Step 2: DEPLOY-DOCKER.md — краткая заметка про удалённый демон.
- [ ] Step 3: **Отложенная чистка серии** (из финального ревью спеки 1): убрать мёртвый параметр `run=` из `build_project_router` + `create_app` router_kwargs + его передачу (и из тестов, если передают); при желании дедуп `_RecordingProvisioner`/нормализация ssh-таймаут-маркера — опционально.

**Verification:** `… pytest -q -k "not install_stops_on_dump_error"` зелёный.

---

## Финал
- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` зелёный.
- [ ] Финальное ревью ветки (opus): локальный docker/ssh/local не задеты; `-H` во ВСЕХ docker-командах (включая image-check и PTY); ключ/кеш различают демоны; мёртвый код убран.
- [ ] Коммиты в master по задаче после двухстадийного ревью.

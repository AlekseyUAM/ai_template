# Удалённые операции окружения (cf/cfe, tools-install, update-env для ssh/docker) — План

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Прогнать выгрузку cf/cfe, tools-install и update-env через `Provisioner` на целевой машине, сделав ssh/docker-проекты полноценными. Локальное поведение не меняется.

**Architecture:** `Provisioner.run` получает опциональный `timeout` (единообразно транслируется в `RunResult(124)` при истечении — без разнобоя исключений). `platform_dump.dump` и `tools_install.install_tools` исполняются через `prov.run`/`prov.venv_python` вместо `subprocess`/`sys.executable`. `installer`/`project_api` снимают гейт `is_local` и прокидывают `prov`; `update_env*` становятся backend-aware (prov из `registry` по path).

**Tech Stack:** Python 3.10+, pytest. Реальные docker/ssh/1С не нужны — prov/run инъектируются фейками.

## Global Constraints
- **Local не меняется**: `timeout=None` по умолчанию → прежнее поведение; local dump/tools/update-env дают прежний результат.
- Таймаут в `run` → при истечении вернуть `RunResult(124, <stdout-so-far>, "<...timeout...>")`, НЕ бросать исключение бэкенда.
- Цель ssh/docker — Linux (POSIX пути, `prov.venv_python`).
- Тесты: из `app/` — `/home/uam/projects/ai_template/.venv/bin/python -m pytest -q`; быстрый полный прогон: `-k "not install_stops_on_dump_error"`.
- Русские docstring; коммиты атомарные по задаче в локальный `master` после двухстадийного ревью.

## Файловая структура
- `app/src/agentmon/backends/__init__.py` — `Provisioner.run(..., timeout=None)`.
- `app/src/agentmon/backends/local.py`/`ssh.py`/`docker.py` — `run(..., timeout=None)` + трансляция в `RunResult(124)`.
- `app/src/agentmon/env/platform_dump.py` — через `prov.run(timeout=...)`.
- `app/src/agentmon/env/tools_install.py` — через `prov`/`venv_python`.
- `app/src/agentmon/env/installer.py` — `tools-install` с `prov`; `run=` убрать.
- `app/src/agentmon/env/project_api.py` — снять `is_local`; `update_env*` backend-aware.
- `docs/PHASES.md` — убрать реализованные пункты из «Следующих шагов».
- Тесты — обновить существующие + новые (timeout, update-env backend-aware).

---

## Task 1: `Provisioner.run(timeout=None)` во всех бэкендах

**Files:** Modify `backends/__init__.py`, `backends/local.py`, `backends/ssh.py`, `backends/docker.py`; Tests: обновить `tests/test_provisioner_local.py`/`test_backend_ssh*`/`test_backend_docker.py` (или где тестируется run).

**Interfaces:** `run(cmd, cwd=None, timeout=None) -> RunResult`. При истечении таймаута — `RunResult(124, stdout_so_far, stderr_с_пометкой_timeout)`. `timeout=None` → как сейчас.
- Local: `subprocess.run(..., timeout=timeout)`; `except subprocess.TimeoutExpired as e` → `RunResult(124, e.stdout or "", (e.stderr or "")+"\n<timeout>")`.
- Ssh: `chan.settimeout(timeout)` перед чтением; при таймауте чтения/`socket.timeout` → закрыть канал, `RunResult(124, собранное, "<timeout>")`.
- Docker: `exec_run`/`run` → `subprocess.run(docker exec..., timeout=timeout)`, та же трансляция; `exec_input` не трогаем (без таймаута).

**Steps:**
- [ ] Step 1: Протокол в `__init__.py` (+`timeout`).
- [ ] Step 2: Local.run timeout → 124 (+тест c моками subprocess, TimeoutExpired).
- [ ] Step 3: Ssh.run timeout → 124 (settimeout; +тест фейк-канал с таймаутом).
- [ ] Step 4: Docker `_DockerContainer.exec_run`/`DockerProvisioner.run` timeout → 124 (+тест фейк run с TimeoutExpired).
- [ ] Step 5: Убедиться `timeout=None` не меняет существующие тесты.

**Verification:** фокус-тесты бэкендов + провиженеров зелёные; полный фильтрованный прогон без регрессий.

---

## Task 2: `platform_dump.dump` через `prov.run(timeout=...)`

**Files:** Modify `env/platform_dump.py`; Test: `tests/env/test_platform_dump*` (или где `dump`/installer тестируют dump).

**Interfaces:** `dump(config, kind, *, user="", password="", sleep=..., clock=..., max_wait=900, interval=30, prov=None)` — убрать `run=`. DESIGNER через `prov.run(cmd, timeout=max(1.0, remaining))`. `returncode==0`→успех; auth-маркер в логе→`RuntimeError` без ретрая; дедлайн истёк→`RuntimeError`; иначе `sleep(interval)` и ретрай. (Ветка `TimeoutExpired` исчезает — таймаут приходит как rc=124, ретраибельно.)

**Steps:**
- [ ] Step 1: `build_dump_command` без изменений (уже через prov для binary). `dump` — через `prov.run(timeout=...)`, убрать `run=`/`subprocess`-импорт если не нужен.
- [ ] Step 2: Обновить вызовы `dump(...)` (installer) — убрать `run=`.
- [ ] Step 3: Тест фейк-prov: rc 0/занят(ненулевой)/auth/timeout(124) → успех/ретрай/не-ретрай-auth/ретрай; дедлайн → RuntimeError; инъекция sleep/clock (без реального sleep).

**Verification:** фокус-тесты dump зелёные; медленный `test_install_stops_on_dump_error` при желании ускорить инъекцией (если он здесь).

---

## Task 3: `tools_install.install_tools` через `prov`

**Files:** Modify `env/tools_install.py`; Test: `tests/env/test_tools_install*` (или новый).

**Interfaces:** `install_tools(config, *, prov=None)`; `prov = prov or LocalProvisioner()`. `py = prov.venv_python(config.project_dir)`; команды `prov.run([py, "-m", "pip", "install", <scripts-path цели>], ...)` и `prov.run([py, "-m","pip","install","lxml","Pillow","psutil"], ...)`; rc≠0 → `RuntimeError(stderr)`. Путь scripts — POSIX на цели (`f"{project_dir}/.claude/skills/1c-batch/scripts"`; на local — как было).

**Steps:**
- [ ] Step 1: Переписать на prov/venv_python; убрать `run=subprocess`/`sys.executable`.
- [ ] Step 2: Тест фейк-prov: обе pip-команды с venv_python цели через prov.run; rc≠0 → RuntimeError.

**Verification:** фокус-тесты tools зелёные.

---

## Task 4: installer — prov в tools-install, без is_local

**Files:** Modify `env/installer.py`; Test: `tests/env/test_installer.py`.

**Interfaces:** шаг `tools-install` → `install_tools_fn(config, prov=prov)`. `install_environment` — параметр `run=` удалить (dump/tools идут через prov). dump-шаги уже через prov.

**Steps:**
- [ ] Step 1: `tools-install` с prov; `run=` убрать из сигнатуры/вызовов внутри installer.
- [ ] Step 2: Обновить тесты installer (dump/tools через фейк-prov; проверить, что при выбранных флагах шаги выполняются независимо от backend).

**Verification:** `test_installer.py` зелёный; полный фильтрованный прогон.

---

## Task 5: project_api — ungate + backend-aware update-env

**Files:** Modify `env/project_api.py`; Test: `tests/env/test_ssh_create.py`, `test_docker_create.py`, `test_project_api*`, + новый update-env backend-aware.

**Interfaces:**
- `_install_iter`: убрать `and is_local` у `dump_cf`/`dump_cfe`/`install_tools` (оставить галки пользователя и прежние `not update`-условия). `run=` в `install_environment` не передавать.
- `update_env`/`update_env_stream`: найти backend/conn проекта в `registry` по `project["path"]`; `prov = _provisioner_for(backend, conn, project["path"])`; передать `prov=prov` в `install_environment`. Если в registry нет — backend `local` (как сейчас).

**Steps:**
- [ ] Step 1: Снять `is_local`-гейт в `_install_iter`.
- [ ] Step 2: `update_env*` — резолв backend/conn из registry + prov + прокидывание prov в оба эндпоинта.
- [ ] Step 3: Тесты: ssh/docker create с `dump_cf/install_tools=true` → операции прошли через фейк-prov (не пропущены); update-env ssh/docker → prov из registry (смоук с фейк-бэкендом); local create/update — прежнее.

**Verification:** `test_ssh_create`/`test_docker_create`/`test_project_api*` зелёные; полный фильтрованный прогон.

---

## Task 6: docs/PHASES

**Files:** Modify `docs/PHASES.md`.
- [ ] Убрать из «Следующих шагов» пункты: выгрузка cf/cfe по SSH; tools-install по SSH; update-env для SSH; выгрузка cf/cfe и tools-install по docker; update-env для Docker. Кратко отразить в «Реализовано», что эти операции идут через Provisioner на цели для ssh/docker.

**Verification:** полный фильтрованный прогон зелёный.

---

## Финал
- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` из `app/` — зелёный.
- [ ] Финальное ревью ветки (opus): инвариант local; единообразие таймаута (124); отсутствие `is_local`-регрессий; update-env реально backend-aware.
- [ ] Коммиты в локальный master по задаче после двухстадийного ревью.

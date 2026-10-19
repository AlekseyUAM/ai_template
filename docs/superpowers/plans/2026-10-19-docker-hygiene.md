# docker-гигиена (list_files down-vs-empty + персистентность ~/.claude) — План

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Две быстрые правки docker-бэкенда: (1) `list_files`/`read_from` различают «контейнер/демон упал» (→ `mark_broken`) от «сессий ещё нет» (→ `[]`); (2) `~/.claude` контейнера проекта переживает пересоздание (именованный том). Остальные бэкенды не трогаем.

**Architecture:** Helper `_is_container_down(rc, stderr)` в `backends/docker.py`; `DockerFiles.list_files`/`read_from` используют его для разбора ненулевого rc. `_DockerContainer` монтирует `claude_volume:/root/.claude`; `DockerBackend` выводит `{name}-claude`.

**Tech Stack:** Python 3.10+, pytest. Без реального docker — фейк-run/контейнер.

## Global Constraints
- ssh/local не трогаем. Существующие ensure/list_files/read_from тесты — без регрессий (добавляется один `-v` и ветка разбора rc).
- Русские docstring; коммиты атомарные по задаче в master после двухстадийного ревью.
- Тесты из `app/`: `/home/uam/projects/ai_template/.venv/bin/python -m pytest -q`; быстрый полный: `-k "not install_stops_on_dump_error"`.

## Файлы
- `app/src/agentmon/backends/docker.py` — `_is_container_down`; `DockerFiles.list_files`/`read_from`; `_DockerContainer.__init__`/`ensure`; `DockerBackend.__init__`; (при нужде) `exec_run_bytes` возвращает stderr.
- `app/tests/test_backend_docker.py`.
- `docs/PHASES.md`.

---

## Task 1: `list_files`/`read_from` — различать container-down vs нет-сессий

**Files:** Modify `backends/docker.py`; Test `app/tests/test_backend_docker.py`.

**Interfaces:**
- `_is_container_down(rc: int, stderr: str) -> bool` — `rc in (125,126,127)` или `stderr` содержит один из: `"No such container"`, `"is not running"`, `"Cannot connect to the Docker daemon"`, `"No such exec"`, `"error during connect"`.
- `DockerFiles.list_files`: `except Exception`→`mark_broken+[]` (как есть); `rc==0`→парсинг; `rc!=0 and _is_container_down(rc, stderr)`→`mark_broken()+[]`; иначе→`[]` без mark_broken.
- `DockerFiles.read_from`: аналогично через `_is_container_down`. Если `exec_run_bytes` не отдаёт stderr — расширить его, чтобы вернуть `(rc, data, stderr)` или опираться на rc-коды (125/126/127); минимальное изменение, сохранить существующие вызовы.

**Steps:**
- [ ] Step 1: `_is_container_down` (модульная функция).
- [ ] Step 2: `list_files` — ветки down/нет-сессий; захватить stderr из `exec_run` (у `RunResult` есть `.stderr`).
- [ ] Step 3: `read_from` — то же; при необходимости `exec_run_bytes` вернуть stderr (обновить его тесты).
- [ ] Step 4: Тесты: `_is_container_down` таблица; list_files rc=125/маркер→mark_broken+[]; rc=1→[] без mark_broken; rc=0→парсинг; read_from rc=125→mark_broken+(b"",off); rc=1→(b"",off).

**Verification:** `… pytest tests/test_backend_docker.py -v`; полный фильтрованный без регрессий.

---

## Task 2: персистентный `~/.claude` контейнера проекта

**Files:** Modify `backends/docker.py`; Test `app/tests/test_backend_docker.py`.

**Interfaces:**
- `_DockerContainer.__init__(..., claude_volume: str | None = None, claude_home: str = "/root/.claude")`. В `ensure` docker run: если `claude_volume` задан → добавить `-v {claude_volume}:{claude_home}` (рядом с `-v {volume}:{workdir}`).
- `DockerBackend.__init__`: `claude_volume = f"{name}-claude"`, передать в `_DockerContainer`.
- `DockerFiles` дефолт-home/guess остаётся `/root` (совпадает с `claude_home`), `home_projects_dir`=`/root/.claude/projects` — внутри тома.

**Steps:**
- [ ] Step 1: `_DockerContainer` claude_volume/claude_home + `-v` в ensure.
- [ ] Step 2: `DockerBackend` выводит `{name}-claude`, прокидывает.
- [ ] Step 3: Тесты: ensure absent → docker run содержит `-v {name}-claude:/root/.claude`; без claude_volume — прежний набор `-v` (регресс); DockerBackend ставит claude_volume.

**Verification:** `… pytest tests/test_backend_docker.py -v` + регресс ensure-тестов.

---

## Task 3: docs/PHASES

**Files:** Modify `docs/PHASES.md`.
- [ ] Убрать из «Следующих шагов» пункты про `list_files` (down vs нет-сессий) и персистентность `~/.claude`; кратко отразить в «Реализовано» (docker list_files помечает broken при падении контейнера; `~/.claude` контейнера проекта — в именованном томе).

**Verification:** полный фильтрованный прогон зелёный.

---

## Финал
- [ ] Полный `… pytest -q -k "not install_stops_on_dump_error"` зелёный.
- [ ] Финальное ревью ветки (opus): разбор down корректен (не ложный broken на нет-сессий); том `~/.claude` не ломает ensure; ssh/local не задеты.
- [ ] Коммиты в master по задаче после двухстадийного ревью.

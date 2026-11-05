# Автоклонирование deps для MCP-кнопок — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перед сборкой образа MCP-сервера автоматически клонировать нужный исходный репозиторий в `deps/`, если его там ещё нет.

**Architecture:** Источник (`repo_dir` + `repo_url`) описывается в `BuildSpec` рядом с Dockerfile/контекстом сборки. Новый модуль `mcp_sources.py` строит и выполняет `git clone --depth 1`; оба эндпоинта запуска (`/launch` и `/launch/stream`) вызывают его до `docker build` и показывают вывод в общем логе.

**Tech Stack:** Python 3.10+, FastAPI, pytest, subprocess. Новых зависимостей нет.

**Spec:** `docs/superpowers/specs/2026-11-05-mcp-deps-autoclone-design.md`

## Global Constraints

- Клонирование выполняется **только когда `need_build`** (образа ещё нет).
- URL строго:
  - `https://github.com/AlekseyUAM/docker_1c_sandbox.git`
  - `https://github.com/Regsorm/code-index-mcp.git`
- Команда клона: `git clone --depth 1 <url> <dest>`.
- Существующий каталог `deps/...` не трогаем (идемпотентность).
- Виды `bsl-ls`, `1c-naparnic` и кнопку «Развернуть локально» не меняем.
- Все тексты логов — на русском.
- Коммиты — локально в `main`, без push (пользователь явно разрешил).
- Тесты запускаются из корня репозитория: `.venv/bin/python -m pytest app/tests/env/... -q`.

---

### Task 1: Источник сборки в `BuildSpec`

**Files:**
- Modify: `app/src/agentmon/env/mcp_docker_recipes.py`
- Test: `app/tests/env/test_mcp_docker_recipes.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `BuildSpec.repo_dir: str | None` и `BuildSpec.repo_url: str | None`; для рецептов `1c-platform` и `code-index` они заполнены, для `bsl-ls` — `None`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `app/tests/env/test_mcp_docker_recipes.py`:

```python
def test_platform_build_knows_source_repo():
    b = R.recipe_for("1c-platform").build
    assert b.repo_dir == "deps/docker_1c_sandbox"
    assert b.repo_url == "https://github.com/AlekseyUAM/docker_1c_sandbox.git"


def test_code_index_build_knows_source_repo():
    b = R.recipe_for("code-index").build
    assert b.repo_dir == "deps/code-index-mcp"
    assert b.repo_url == "https://github.com/Regsorm/code-index-mcp.git"


def test_bsl_ls_build_has_no_source_repo():
    b = R.recipe_for("bsl-ls").build
    assert b.repo_dir is None
    assert b.repo_url is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_docker_recipes.py -q`

Expected: FAIL — `AttributeError: 'BuildSpec' object has no attribute 'repo_dir'`.

- [ ] **Step 3: Реализовать поля и заполнить рецепты**

В `app/src/agentmon/env/mcp_docker_recipes.py` заменить `BuildSpec`:

```python
@dataclass(frozen=True)
class BuildSpec:
    dockerfile: str     # путь относительно корня репозитория
    context: str        # контекст сборки относительно корня репозитория
    build_args: dict = field(default_factory=dict)
    repo_dir: str | None = None   # каталог исходников относительно корня репозитория
    repo_url: str | None = None   # HTTPS-URL для git clone, если каталога нет
```

В рецепте `1c-platform` заменить `build` на:

```python
        build=BuildSpec(
            dockerfile="deps/docker_1c_sandbox/mcp-bsl-context/Dockerfile",
            context="deps/docker_1c_sandbox/mcp-bsl-context",
            repo_dir="deps/docker_1c_sandbox",
            repo_url="https://github.com/AlekseyUAM/docker_1c_sandbox.git",
        ),
```

В рецепте `code-index` заменить `build` на:

```python
        build=BuildSpec(
            dockerfile="deps/code-index-mcp/deploy/docker/Dockerfile",
            context="deps/code-index-mcp",
            repo_dir="deps/code-index-mcp",
            repo_url="https://github.com/Regsorm/code-index-mcp.git",
        ),
```

Также обновить первый абзац docstring модуля: добавить предложение
«Если каталога исходников нет, он клонируется перед сборкой (см. `mcp_sources`).»

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_docker_recipes.py -q`

Expected: PASS (16 passed).

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/mcp_docker_recipes.py app/tests/env/test_mcp_docker_recipes.py
git commit -m "feat(mcp): источник сборки в BuildSpec рецептов"
```

---

### Task 2: Модуль клонирования `mcp_sources`

**Files:**
- Create: `app/src/agentmon/env/mcp_sources.py`
- Create: `app/tests/env/test_mcp_sources.py`

**Interfaces:**
- Consumes: `BuildSpec` из `mcp_docker_recipes` (Task 1).
- Produces:
  - `clone_cmd(build: BuildSpec | None, repo_root) -> list[str] | None`
  - `clone(build: BuildSpec | None, repo_root, run=subprocess.run) -> dict`
    с ключами `ok: bool`, `cloned: bool`, `log: str`.

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/env/test_mcp_sources.py`:

```python
from types import SimpleNamespace

from agentmon.env import mcp_sources
from agentmon.env.mcp_docker_recipes import BuildSpec


SPEC = BuildSpec(
    dockerfile="deps/repo/docker/Dockerfile",
    context="deps/repo",
    repo_dir="deps/repo",
    repo_url="https://github.com/example/repo.git",
)


def test_clone_cmd_none_without_source(tmp_path):
    assert mcp_sources.clone_cmd(None, tmp_path) is None
    assert mcp_sources.clone_cmd(BuildSpec("d", "c"), tmp_path) is None


def test_clone_cmd_requires_both_fields(tmp_path):
    only_dir = BuildSpec("d", "c", repo_dir="deps/repo")
    only_url = BuildSpec("d", "c", repo_url="https://github.com/example/repo.git")
    assert mcp_sources.clone_cmd(only_dir, tmp_path) is None
    assert mcp_sources.clone_cmd(only_url, tmp_path) is None


def test_clone_cmd_none_if_dir_exists(tmp_path):
    (tmp_path / "deps" / "repo").mkdir(parents=True)
    assert mcp_sources.clone_cmd(SPEC, tmp_path) is None


def test_clone_cmd_builds_git_clone(tmp_path):
    cmd = mcp_sources.clone_cmd(SPEC, tmp_path)
    assert cmd == [
        "git", "clone", "--depth", "1",
        "https://github.com/example/repo.git",
        str(tmp_path / "deps" / "repo"),
    ]


def test_clone_skips_when_present(tmp_path):
    (tmp_path / "deps" / "repo").mkdir(parents=True)
    called = []

    def fake_run(cmd, **kw):
        called.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res == {"ok": True, "cloned": False, "log": ""}
    assert called == []


def test_clone_runs_git_and_reports_success(tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="Cloning into 'repo'...\n",
                               stderr="")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is True
    assert res["cloned"] is True
    assert seen["cmd"] == mcp_sources.clone_cmd(SPEC, tmp_path)
    assert "$ git clone --depth 1" in res["log"]
    assert "Cloning into" in res["log"]


def test_clone_reports_git_failure(tmp_path):
    def fake_run(cmd, **kw):
        return SimpleNamespace(returncode=128, stdout="",
                               stderr="fatal: repository not found\n")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is False
    assert res["cloned"] is True
    assert "fatal: repository not found" in res["log"]


def test_clone_catches_missing_git(tmp_path):
    def fake_run(cmd, **kw):
        raise FileNotFoundError("git not found")

    res = mcp_sources.clone(SPEC, tmp_path, run=fake_run)
    assert res["ok"] is False
    assert "git not found" in res["log"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_sources.py -q`

Expected: FAIL — `ModuleNotFoundError: No module named 'agentmon.env.mcp_sources'`.

- [ ] **Step 3: Реализовать модуль**

Создать `app/src/agentmon/env/mcp_sources.py`:

```python
"""Скачивание исходников MCP-серверов из deps/ при первом развёртывании.

Репозитории из `deps/` не входят в состав ai_template (см. `.gitignore`),
поэтому перед сборкой образа нужный исходник клонируется, если его ещё нет.
"""
import subprocess
from pathlib import Path

from .mcp_docker_recipes import BuildSpec


def clone_cmd(build: BuildSpec | None, repo_root) -> list[str] | None:
    """Команда `git clone` для отсутствующего каталога исходников.

    None — если источника нет, задано только одно из полей repo_dir/repo_url
    или каталог уже существует.
    """
    if build is None or not build.repo_dir or not build.repo_url:
        return None
    dest = Path(repo_root) / build.repo_dir
    if dest.exists():
        return None
    return ["git", "clone", "--depth", "1", build.repo_url, str(dest)]


def clone(build: BuildSpec | None, repo_root, run=subprocess.run) -> dict:
    """Клонирует источник (блокирующе); возвращает {ok, cloned, log}."""
    cmd = clone_cmd(build, repo_root)
    if cmd is None:
        return {"ok": True, "cloned": False, "log": ""}
    log = f"$ {' '.join(cmd)}\n"
    try:
        r = run(cmd, capture_output=True, text=True)
    except OSError as exc:
        return {"ok": False, "cloned": True, "log": log + f"{exc}\n"}
    log += (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "cloned": True, "log": log}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_sources.py -q`

Expected: PASS (8 passed).

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/mcp_sources.py app/tests/env/test_mcp_sources.py
git commit -m "feat(mcp): модуль скачивания исходников deps"
```

---

### Task 3: Клонирование в блокирующем `/launch`

**Files:**
- Modify: `app/src/agentmon/env/mcp_api.py`
- Test: `app/tests/env/test_mcp_api.py`

**Interfaces:**
- Consumes: `mcp_sources.clone(build, repo_root)` из Task 2; `ctx["build_spec"]` и `ctx["repo_root"]` из существующего `_resolve_docker`.
- Produces: блокирующий запуск при `need_build` сначала клонирует deps; при ошибке возвращает `{"ok": False, "log": ...}` и не вызывает `docker build`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_mcp_api.py` после `test_launch_builds_image_when_missing`:

```python
def test_launch_clones_deps_before_build(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker, mcp_sources
    order = []
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: False)

    def fake_clone(build, repo_root, **kw):
        order.append("clone")
        return {"ok": True, "cloned": True, "log": "Cloning into 'repo'..."}

    def fake_build(tag, dockerfile, context, **k):
        order.append("build")
        return {"ok": True, "log": "built"}

    monkeypatch.setattr(mcp_sources, "clone", fake_clone)
    monkeypatch.setattr(mcp_docker, "build", fake_build)
    monkeypatch.setattr(mcp_docker, "launch",
                        lambda **kw: {"ok": True, "container": kw["name"], "log": "run"})

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8004})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert order == ["clone", "build"]
    assert "Cloning into" in r.json()["log"]


def test_launch_clone_failure_aborts_build(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker, mcp_sources
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: False)
    monkeypatch.setattr(
        mcp_sources, "clone",
        lambda build, repo_root, **kw: {
            "ok": False, "cloned": True,
            "log": "fatal: repository not found",
        })

    def fake_build(*a, **k):
        raise AssertionError("docker build не должен вызываться")

    monkeypatch.setattr(mcp_docker, "build", fake_build)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8004})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "fatal: repository not found" in data["log"]


def test_launch_skips_clone_when_image_exists(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker, mcp_sources
    monkeypatch.setattr(mcp_docker, "image_exists", lambda tag, **k: True)
    called = []
    monkeypatch.setattr(
        mcp_sources, "clone",
        lambda *a, **k: called.append(1) or {"ok": True, "log": ""})
    monkeypatch.setattr(mcp_docker, "launch",
                        lambda **kw: {"ok": True, "container": kw["name"], "log": "run"})

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={"port": 8004})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert called == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q -k "clones_deps or clone_failure or skips_clone"`

Expected: FAIL — clone не вызывается, `order == ["build"]`; во втором тесте
`fake_build` поднимает `AssertionError`.

- [ ] **Step 3: Подключить модуль и встроить клонирование**

В `app/src/agentmon/env/mcp_api.py` добавить импорт после `from . import mcp_docker`:

```python
from . import mcp_sources
```

В `launch_mcp` заменить блок `if ctx["need_build"]:` на:

```python
        if ctx["need_build"]:
            b = ctx["build_spec"]
            if b is None:
                return {"ok": False,
                        "log": f"образ {ctx['image']} не найден; сборка недоступна — "
                               "соберите образ заранее"}
            rr = ctx["repo_root"]
            res_c = mcp_sources.clone(b, rr)
            log_parts.append(res_c.get("log", ""))
            if not res_c["ok"]:
                return {"ok": False,
                        "log": "\n".join(x for x in log_parts if x)
                               + "\n✗ Не удалось скачать исходники"}
            res_b = mcp_docker.build(ctx["image"], str(rr / b.dockerfile),
                                     str(rr / b.context), build_args=b.build_args)
            log_parts.append(res_b.get("log", ""))
            if not res_b["ok"]:
                return {"ok": False, "log": "\n".join(p for p in log_parts if p)}
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q -k "clones_deps or clone_failure or skips_clone"`

Expected: PASS (3 passed).

- [ ] **Step 5: Прогнать все тесты API**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q`

Expected: PASS (все, включая прежние).

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_api.py app/tests/env/test_mcp_api.py
git commit -m "feat(mcp-api): clone deps перед блокирующей сборкой"
```

---

### Task 4: Клонирование в стриминговом `/launch/stream`

**Files:**
- Modify: `app/src/agentmon/env/mcp_api.py`
- Test: `app/tests/env/test_mcp_api.py`

**Interfaces:**
- Consumes: `mcp_sources.clone_cmd(build, repo_root)` из Task 2; `mcp_docker.iter_output`/`is_rc`.
- Produces: в теле стрима секция `=== Скачивание исходников ===` до `=== Сборка образа ===`; при ошибке клона сборка не начинается.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_mcp_api.py` после `test_launch_stream_builds_then_runs`:

```python
def test_launch_stream_clones_then_builds(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker, mcp_sources
    monkeypatch.setattr(mcp_docker, "image_exists", lambda t, **k: False)
    monkeypatch.setattr(
        mcp_sources, "clone_cmd",
        lambda b, rr: ["git", "clone", "--depth", "1", "URL", "DEST"])

    def fake_iter(cmd, **k):
        if cmd[:2] == ["git", "clone"]:
            yield "Cloning into 'DEST'..."
            yield mcp_docker.rc_line(0)
            return
        if cmd[:2] == ["docker", "build"]:
            yield "Step 1/1"
            yield mcp_docker.rc_line(0)
            return
        if cmd[:3] == ["docker", "rm", "-f"]:
            yield mcp_docker.rc_line(0)
            return
        yield "cid"
        yield mcp_docker.rc_line(0)

    monkeypatch.setattr(mcp_docker, "iter_output", fake_iter)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    body = c.post(f"/api/mcp/{mid}/launch/stream", json={"port": 8004}).text
    assert "=== Скачивание исходников ===" in body
    assert "Cloning into" in body
    assert body.index("Скачивание исходников") < body.index("Сборка образа")
    assert "Контейнер запущен" in body


def test_launch_stream_clone_failure_aborts_build(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker, mcp_sources
    monkeypatch.setattr(mcp_docker, "image_exists", lambda t, **k: False)
    monkeypatch.setattr(
        mcp_sources, "clone_cmd",
        lambda b, rr: ["git", "clone", "--depth", "1", "URL", "DEST"])

    def fake_iter(cmd, **k):
        if cmd[:2] == ["git", "clone"]:
            yield "fatal: repository not found"
            yield mcp_docker.rc_line(128)
            return
        yield "unexpected"
        yield mcp_docker.rc_line(0)

    monkeypatch.setattr(mcp_docker, "iter_output", fake_iter)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    body = c.post(f"/api/mcp/{mid}/launch/stream", json={"port": 8004}).text
    assert "fatal: repository not found" in body
    assert "Ошибка скачивания исходников" in body
    assert "Сборка образа" not in body


def test_launch_stream_skips_clone_when_image_exists(tmp_path, monkeypatch):
    from agentmon.env import mcp_docker
    monkeypatch.setattr(mcp_docker, "image_exists", lambda t, **k: True)

    def fake_iter(cmd, **k):
        if cmd[:3] == ["docker", "rm", "-f"]:
            yield mcp_docker.rc_line(0)
            return
        yield "cid"
        yield mcp_docker.rc_line(0)

    monkeypatch.setattr(mcp_docker, "iter_output", fake_iter)

    c = make(tmp_path)
    catalog = tmp_path / "cfg"; catalog.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": str(catalog), "project_name": "proj",
    }).json()["mcp"]["id"]
    body = c.post(f"/api/mcp/{mid}/launch/stream", json={"port": 8004}).text
    assert "Скачивание исходников" not in body
    assert "Контейнер запущен" in body
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q -k "stream_clones or stream_clone_failure or stream_skips_clone"`

Expected: FAIL — в теле нет `Скачивание исходников`.

- [ ] **Step 3: Встроить клонирование в генератор**

В `launch_mcp_stream` в функции `gen()` после проверки `if need_build and b is None:`
и перед комментарием `# снять прежний контейнер...` вставить:

```python
            if need_build:
                clone_c = mcp_sources.clone_cmd(b, rr)
                if clone_c is not None:
                    yield "\n=== Скачивание исходников ===\n"
                    yield f"$ {' '.join(clone_c)}\n"
                    try:
                        yield from _stream(clone_c)
                    except OSError as exc:
                        yield f"\n✗ Не удалось запустить git: {exc}\n"
                        return
                    if _stream.rc != 0:
                        yield (f"\n✗ Ошибка скачивания исходников "
                               f"(код {_stream.rc})\n")
                        return
                    yield "✓ Исходники скачаны\n"
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q -k "stream_clones or stream_clone_failure or stream_skips_clone"`

Expected: PASS (3 passed).

- [ ] **Step 5: Прогнать все тесты API**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_api.py -q`

Expected: PASS (все).

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_api.py app/tests/env/test_mcp_api.py
git commit -m "feat(mcp-api): clone deps в стриминговом развёртывании"
```

---

### Task 5: Полный прогон и финальная проверка

**Files:**
- Проверка: `app/tests/env` (весь каталог)
- При необходимости: исправления в файлах Tasks 1–4.

**Interfaces:**
- Consumes: всё из Tasks 1–4.
- Produces: зелёный полный набор тестов `app/tests/env`.

- [ ] **Step 1: Прогнать весь набор env-тестов**

Run: `.venv/bin/python -m pytest app/tests/env -q`

Expected: PASS, без падений.

- [ ] **Step 2: Проверить, что новые тесты действительно покрывают сценарий**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_sources.py app/tests/env/test_mcp_api.py -q -k "clone"`

Expected: PASS, в списке есть тесты `clone_cmd`, `clone`, `clones_deps`,
`clone_failure`, `stream_clones`, `stream_clone_failure`.

- [ ] **Step 3: Коммит (если Step 1 потребовал правок)**

```bash
git add app/src/agentmon/env app/tests/env
git commit -m "fix(mcp): доводка автоклонирования deps по полному прогону"
```

Если правок не было — коммит не нужен.

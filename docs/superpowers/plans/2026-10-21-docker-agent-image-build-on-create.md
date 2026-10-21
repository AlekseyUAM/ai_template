# Сборка docker-образа агента по кнопке — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** При создании docker-проекта пользователь указывает путь к дистрибутиву платформы 1С, и образ `ai1c-agent:<версия>` собирается по кнопке «Создать проект», если его ещё нет.

**Architecture:** Новый самодостаточный Dockerfile в `ai_template` (только платформа 1С + рантайм агента) и модуль `docker_image.py` (тег/проверка/сборка). API мастера проверяет наличие образа и собирает его первым шагом создания. Зависимости от `deps/docker_1c_sandbox` нет.

**Tech Stack:** Python 3, FastAPI, pytest, Docker CLI, ванильный JS (мастер).

## Global Constraints

- Фича не импортирует и не читает ничего из `deps/docker_1c_sandbox`.
- Тег образа: `ai1c-agent:<sanitized_platform_version>`; переиспользуется между проектами.
- Поле дистрибутива обязательно только если образа нужной версии нет.
- Поддержать локальный и удалённый docker-демон (`docker -H <docker_host>`).
- Образ лёгкий: ОС + системные зависимости 1С + `xvfb` + `ru_RU.UTF-8` + Claude Code CLI + платформа из дистрибутива. Ни фреймворка, ни bsl-lsp-bridge, ни test-runner, ни Vanessa, ни template.
- `platform_dir` для docker остаётся `/opt/1cv8/current`.
- Все тесты — без реального Docker (инъекция `run` / `popen` / fake-функций).
- Тесты: `pytest` из каталога `app/` (`cd app && python -m pytest ...`).
- Коммиты — в `main` локально, сообщения на русском, каждый оканчивается:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: `docker_image.py` — тег и проверка наличия образа

**Files:**
- Create: `app/src/agentmon/env/docker_image.py`
- Test: `app/tests/env/test_docker_image.py`

**Interfaces:**
- Consumes: ничего (новый модуль).
- Produces:
  - `image_tag(platform_version: str) -> str` — `"ai1c-agent:<sanitized>"`; пустой/мусорный ввод → `"ai1c-agent:latest"`.
  - `image_exists(tag: str, docker_host: str | None = None, run=subprocess.run) -> bool`.
  - `AGENT_IMAGE_PREFIX = "ai1c-agent"`.
  - `DOCKERFILE_PATH: pathlib.Path` — абсолютный путь к `app/docker/agent-image/Dockerfile`.

- [ ] **Step 1: Написать падающий тест**

Создать `app/tests/env/test_docker_image.py`:

```python
"""Тесты модуля сборки docker-образа агента (docker_image.py).

Реальный Docker не вызывается: subprocess.run подменяется фейком.
"""
from agentmon.env import docker_image as di


class FakeRun:
    """Имитатор subprocess.run: один ответ на все вызовы, запоминает argv."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return self


# ── image_tag ────────────────────────────────────────────────────────────────

def test_image_tag_simple():
    assert di.image_tag("8.3.27.1786") == "ai1c-agent:8.3.27.1786"


def test_image_tag_sanitizes_spaces_and_case():
    assert di.image_tag("  8.3.27 X ") == "ai1c-agent:8.3.27x"


def test_image_tag_empty_falls_back_to_latest():
    assert di.image_tag("") == "ai1c-agent:latest"
    assert di.image_tag("   ") == "ai1c-agent:latest"


# ── image_exists ─────────────────────────────────────────────────────────────

def test_image_exists_true_when_id_printed():
    fake = FakeRun(returncode=0, stdout="deadbeef\n")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is True
    assert fake.calls[0] == ["docker", "images", "-q", "ai1c-agent:8.3.27"]


def test_image_exists_false_when_empty_output():
    fake = FakeRun(returncode=0, stdout="\n")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is False


def test_image_exists_false_when_rc_nonzero():
    fake = FakeRun(returncode=1, stdout="")
    assert di.image_exists("ai1c-agent:8.3.27", run=fake) is False


def test_image_exists_inserts_docker_host():
    fake = FakeRun(returncode=0, stdout="id\n")
    di.image_exists("ai1c-agent:8.3.27", docker_host="ssh://u@h", run=fake)
    assert fake.calls[0] == [
        "docker", "-H", "ssh://u@h", "images", "-q", "ai1c-agent:8.3.27",
    ]
```

- [ ] **Step 2: Запустить тест — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_docker_image.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentmon.env.docker_image'`

- [ ] **Step 3: Минимальная реализация**

Создать `app/src/agentmon/env/docker_image.py`:

```python
"""Сборка самодостаточного docker-образа агента ai1c-agent:<версия>.

Образ содержит только платформу 1С (из указанного дистрибутива) и рантайм
агента. Зависимостей от deps/docker_1c_sandbox нет.
"""
import re
import subprocess
from pathlib import Path

AGENT_IMAGE_PREFIX = "ai1c-agent"

# app/src/agentmon/env/docker_image.py → parents[3] == app/
DOCKERFILE_PATH = Path(__file__).resolve().parents[3] / "docker" / "agent-image" / "Dockerfile"


def _docker_argv(docker_host, tail):
    """["docker"] + опциональный -H <host> + tail."""
    return ["docker"] + (["-H", docker_host] if docker_host else []) + tail


def image_tag(platform_version: str) -> str:
    """Тег образа из версии платформы: ai1c-agent:<sanitized>.

    Нормализация: strip + lower, оставляем только [a-z0-9_.-].
    Пустой результат → ai1c-agent:latest.
    """
    safe = re.sub(r"[^a-z0-9_.\-]", "", (platform_version or "").strip().lower())
    return f"{AGENT_IMAGE_PREFIX}:{safe or 'latest'}"


def image_exists(tag: str, docker_host: str | None = None, run=subprocess.run) -> bool:
    """True, если docker images -q <tag> напечатал непустой id."""
    r = run(_docker_argv(docker_host, ["images", "-q", tag]),
            capture_output=True, text=True)
    return r.returncode == 0 and bool((r.stdout or "").strip())
```

- [ ] **Step 4: Запустить тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/env/test_docker_image.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/docker_image.py app/tests/env/test_docker_image.py
git commit -m "feat(docker-image): image_tag + image_exists для образа агента

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `docker_image.py` — сборка образа (стриминг лога)

**Files:**
- Modify: `app/src/agentmon/env/docker_image.py`
- Test: `app/tests/env/test_docker_image.py`

**Interfaces:**
- Consumes: `image_tag`, `DOCKERFILE_PATH`, `_docker_argv` (Task 1).
- Produces:
  - `build_agent_image(distr_path: str, platform_version: str, docker_host: str | None = None, popen=subprocess.Popen) -> Iterator[str]`
    — генератор: валидирует дистрибутив, собирает временный контекст (hardlink
    дистрибутива под именем `distr.zip`, fallback на copy при EXDEV), запускает
    `docker [-H] build -t <tag> -f <DOCKERFILE_PATH> <ctx>`, построчно отдаёт
    вывод; по завершении при ненулевом коде бросает `RuntimeError`. Временный
    контекст удаляется в `finally`. При некорректном дистрибутиве бросает
    `ValueError` до запуска docker.

- [ ] **Step 1: Написать падающий тест**

Дописать в `app/tests/env/test_docker_image.py`:

```python
import pytest


class FakeProc:
    """Имитатор Popen: отдаёт заранее заданные строки stdout и код возврата."""

    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.returncode = returncode

    def wait(self):
        return self.returncode


class FakePopen:
    """Callable уровня subprocess.Popen: запоминает argv, возвращает FakeProc."""

    def __init__(self, lines, returncode=0):
        self._lines = lines
        self._returncode = returncode
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(list(cmd))
        return FakeProc(self._lines, self._returncode)


def _make_distr(tmp_path):
    p = tmp_path / "server64_8_3_27.zip"
    p.write_bytes(b"PK\x03\x04 fake zip")
    return str(p)


def test_build_rejects_missing_distr(tmp_path):
    gen = di.build_agent_image(str(tmp_path / "нет.zip"), "8.3.27",
                               popen=FakePopen([]))
    with pytest.raises(ValueError):
        list(gen)


def test_build_rejects_non_zip(tmp_path):
    bad = tmp_path / "distr.tar"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        list(di.build_agent_image(str(bad), "8.3.27", popen=FakePopen([])))


def test_build_streams_lines_and_builds_tag(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["Step 1/5\n", "Successfully built\n"], returncode=0)
    lines = list(di.build_agent_image(distr, "8.3.27", popen=fake))
    assert lines == ["Step 1/5\n", "Successfully built\n"]
    argv = fake.calls[0]
    assert argv[0] == "docker"
    assert "build" in argv
    assert "-t" in argv and "ai1c-agent:8.3.27" in argv
    assert "-f" in argv and str(di.DOCKERFILE_PATH) in argv


def test_build_inserts_docker_host(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["ok\n"], returncode=0)
    list(di.build_agent_image(distr, "8.3.27", docker_host="ssh://u@h", popen=fake))
    argv = fake.calls[0]
    assert argv[:3] == ["docker", "-H", "ssh://u@h"]


def test_build_raises_on_nonzero_rc(tmp_path):
    distr = _make_distr(tmp_path)
    fake = FakePopen(["boom\n"], returncode=1)
    with pytest.raises(RuntimeError):
        list(di.build_agent_image(distr, "8.3.27", popen=fake))
```

- [ ] **Step 2: Запустить новые тесты — убедиться, что падают**

Run: `cd app && python -m pytest tests/env/test_docker_image.py -q -k build`
Expected: FAIL — `AttributeError: module 'agentmon.env.docker_image' has no attribute 'build_agent_image'`

- [ ] **Step 3: Реализация**

Дописать в `app/src/agentmon/env/docker_image.py` (импорты — наверх файла):

```python
import os
import shutil
import tempfile
```

```python
def build_agent_image(distr_path, platform_version, docker_host=None,
                      popen=subprocess.Popen):
    """Собрать образ ai1c-agent:<версия> из дистрибутива платформы.

    Генератор: построчно отдаёт вывод docker build. По завершении при
    ненулевом коде — RuntimeError. Некорректный дистрибутив — ValueError.
    """
    if not distr_path or not os.path.isfile(distr_path):
        raise ValueError(f"дистрибутив не найден: {distr_path!r}")
    if not distr_path.lower().endswith(".zip"):
        raise ValueError(f"дистрибутив должен быть .zip: {distr_path!r}")

    tag = image_tag(platform_version)
    ctx = tempfile.mkdtemp(prefix="ai1c-build-")
    try:
        staged = os.path.join(ctx, "distr.zip")
        try:
            os.link(distr_path, staged)      # дёшево: без копирования многогиг .zip
        except OSError:
            shutil.copy2(distr_path, staged)  # другой раздел (EXDEV) — копируем
        argv = _docker_argv(docker_host, [
            "build", "-t", tag, "-f", str(DOCKERFILE_PATH), ctx,
        ])
        proc = popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                     text=True)
        if proc.stdout is not None:
            for line in proc.stdout:
                yield line
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"docker build вернул код {rc} (образ {tag})")
    finally:
        shutil.rmtree(ctx, ignore_errors=True)
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_docker_image.py -q`
Expected: PASS (12 passed)

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/docker_image.py app/tests/env/test_docker_image.py
git commit -m "feat(docker-image): build_agent_image со стримингом лога сборки

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Собственный Dockerfile образа агента

**Files:**
- Create: `app/docker/agent-image/Dockerfile`
- Test: `app/tests/env/test_agent_dockerfile.py`

**Interfaces:**
- Consumes: `di.DOCKERFILE_PATH` (Task 1) указывает на этот файл.
- Produces: build-контекст с фиксированным именем дистрибутива `distr.zip`
  (его кладёт `build_agent_image`). Dockerfile `COPY distr.zip`.

- [ ] **Step 1: Написать падающий content-тест**

Создать `app/tests/env/test_agent_dockerfile.py`:

```python
"""Content-тесты собственного Dockerfile образа агента.

Проверяем ключевые инварианты самодостаточной сборки без реального docker build.
"""
from agentmon.env import docker_image as di


def _text():
    return di.DOCKERFILE_PATH.read_text(encoding="utf-8")


def test_dockerfile_exists():
    assert di.DOCKERFILE_PATH.is_file(), f"нет Dockerfile: {di.DOCKERFILE_PATH}"


def test_copies_fixed_distr_name():
    # build_agent_image кладёт дистрибутив как distr.zip — Dockerfile ждёт это имя
    assert "distr.zip" in _text()


def test_installs_claude_cli():
    assert "@anthropic-ai/claude-code" in _text()


def test_runs_unattended_platform_install():
    t = _text()
    assert "--mode unattended" in t
    assert ".run" in t


def test_creates_current_symlink():
    assert "/opt/1cv8/current" in _text()


def test_sets_ru_locale():
    assert "ru_RU.UTF-8" in _text()


def test_no_deps_sandbox_leftovers():
    t = _text()
    # лёгкий образ: без фреймворка / bridge / test-runner / vanessa
    for forbidden in ("1c-agent-based-dev-framework", "mcp-bsl-lsp-bridge",
                      "mcp-yaxunit-runner", "VanessaExt"):
        assert forbidden not in t, f"лишнее в Dockerfile: {forbidden}"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_agent_dockerfile.py -q`
Expected: FAIL — `test_dockerfile_exists` (файла нет)

- [ ] **Step 3: Создать Dockerfile**

Создать `app/docker/agent-image/Dockerfile`:

```dockerfile
# Самодостаточный образ агента: платформа 1С + рантайм Claude Code.
# Дистрибутив платформы кладётся в build-контекст как distr.zip
# (см. agentmon.env.docker_image.build_agent_image).
FROM ubuntu:22.04

ARG DEBIAN_FRONTEND=noninteractive

# Node.js 20 LTS + системные зависимости платформы 1С + headless-дисплей
RUN apt-get update -o Acquire::ForceIPv4=true -o Acquire::Retries=3 \
  && apt-get install -y --no-install-recommends curl ca-certificates \
  && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
  && apt-get install -y --no-install-recommends \
    locales \
    xvfb \
    libglib2.0-0 \
    libgsf-1-114 \
    libwebkit2gtk-4.0-37 \
    libfontconfig1 \
    libfreetype6 \
    libcups2 \
    libsm6 \
    libx11-6 \
    libxext6 \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxinerama1 \
    libxrandr2 \
    libatk1.0-0 \
    libgtk-3-0 \
    libglu1-mesa \
    libodbc2 \
    fonts-dejavu \
    fonts-liberation \
    nodejs \
    unzip \
    python3 \
    python3-pip \
    python-is-python3 \
  && echo "ru_RU.UTF-8 UTF-8" >> /etc/locale.gen \
  && locale-gen \
  && printf 'LANG=ru_RU.UTF-8\nLC_ALL=ru_RU.UTF-8\n' > /etc/default/locale \
  && rm -rf /var/lib/apt/lists/*

# Claude Code CLI (агент запускается командой `claude` внутри контейнера)
RUN npm install -g @anthropic-ai/claude-code

# Установить платформу 1С из дистрибутива build-контекста
COPY distr.zip /tmp/distr/distr.zip
RUN set -eux; \
  unzip -q /tmp/distr/distr.zip -d /tmp/distr/unpacked; \
  run_file="$(find /tmp/distr/unpacked -name '*.run' | head -1)"; \
  chmod +x "$run_file"; \
  "$run_file" --mode unattended --enable-components server,server_admin,client_full,ru; \
  rm -rf /tmp/distr

# Симлинк /opt/1cv8/current -> установленная версия
RUN arch_dir="$(ls /opt/1cv8 | grep -E 'x86_64|amd64' | head -n1)"; \
    ver="$(ls /opt/1cv8/${arch_dir} | sort -V | tail -n1)"; \
    ln -sfn "/opt/1cv8/${arch_dir}/${ver}" /opt/1cv8/current

ENV PATH="/opt/1cv8/current:${PATH}" \
    LANG="ru_RU.UTF-8" \
    LC_ALL="ru_RU.UTF-8"
```

- [ ] **Step 4: Запустить content-тест — убедиться, что проходит**

Run: `cd app && python -m pytest tests/env/test_agent_dockerfile.py -q`
Expected: PASS (7 passed)

- [ ] **Step 5: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/docker/agent-image/Dockerfile app/tests/env/test_agent_dockerfile.py
git commit -m "feat(docker-image): лёгкий Dockerfile образа агента (платформа + Claude)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Эндпоинт `POST /api/env/projects/check-image`

**Files:**
- Modify: `app/src/agentmon/env/project_api.py`
- Modify: `app/src/agentmon/api.py:22-33`
- Test: `app/tests/env/test_project_api.py`

**Interfaces:**
- Consumes: `image_tag`, `image_exists` (Task 1); `docker_host_from_conn` (`backends/docker.py`).
- Produces:
  - `build_project_router(..., image_exists_fn=docker_image.image_exists)` —
    новый именованный параметр с дефолтом-реальной функцией.
  - `create_app(..., image_exists_fn=None)` — прокидывает в роутер при наличии.
  - Эндпоинт `POST /api/env/projects/check-image`, тело
    `{platform_version, backend?, conn?}` → `{"exists": bool, "tag": str}`.

- [ ] **Step 1: Написать падающий тест**

Дописать в `app/tests/env/test_project_api.py`:

```python
def test_check_image_true(tmp_path):
    reg_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(reg_db)
    queue = TaskQueue(reg_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0,
                  now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    calls = {}

    def fake_exists(tag, docker_host=None, run=None):
        calls["tag"] = tag
        calls["docker_host"] = docker_host
        return True

    app = create_app(registry=registry, queue=queue, monitor=mon, store=store,
                     image_exists_fn=fake_exists)
    c = TestClient(app)
    r = c.post("/api/env/projects/check-image",
               json={"platform_version": "8.3.27", "backend": "docker"})
    assert r.status_code == 200
    assert r.json() == {"exists": True, "tag": "ai1c-agent:8.3.27"}
    assert calls["tag"] == "ai1c-agent:8.3.27"


def test_check_image_false_passes_docker_host(tmp_path):
    reg_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(reg_db)
    queue = TaskQueue(reg_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0,
                  now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    seen = {}

    def fake_exists(tag, docker_host=None, run=None):
        seen["docker_host"] = docker_host
        return False

    app = create_app(registry=registry, queue=queue, monitor=mon, store=store,
                     image_exists_fn=fake_exists)
    c = TestClient(app)
    r = c.post("/api/env/projects/check-image", json={
        "platform_version": "8.3.27", "backend": "docker",
        "conn": {"host": "srv", "user": "u"},
    })
    assert r.json()["exists"] is False
    assert seen["docker_host"] == "ssh://u@srv"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_project_api.py -q -k check_image`
Expected: FAIL — 404/`TypeError` (эндпоинта и параметра нет)

- [ ] **Step 3: Реализация**

В `app/src/agentmon/env/project_api.py` обновить импорты (верх файла):

```python
from ..backends.docker import DEFAULT_PLATFORM_DIR, docker_host_from_conn
from . import docker_image
```

Сигнатуру роутера (`project_api.py:23-24`) заменить на:

```python
def build_project_router(store, registry, monitor=None,
                         popen=subprocess.Popen,
                         image_exists_fn=docker_image.image_exists,
                         build_image_fn=docker_image.build_agent_image) -> APIRouter:
```

Добавить эндпоинт сразу после `check_db_route` (после `project_api.py:97`):

```python
    # ── check-image ──────────────────────────────────────────────────────────

    @router.post("/api/env/projects/check-image")
    def check_image_route(body: dict):
        """Есть ли уже образ ai1c-agent:<версия> на нужном docker-демоне."""
        tag = docker_image.image_tag(body.get("platform_version", ""))
        docker_host = docker_host_from_conn(body.get("conn"))
        try:
            exists = bool(image_exists_fn(tag, docker_host=docker_host))
        except Exception:                                   # noqa: BLE001
            exists = False
        return {"exists": exists, "tag": tag}
```

В `app/src/agentmon/api.py` обновить `create_app` (строки 22-33):

```python
def create_app(registry, queue, monitor, lifespan=None, store=None,
               popen=None, image_exists_fn=None, build_image_fn=None):
    app = FastAPI(lifespan=lifespan)
    from .env.api import build_env_router
    app.include_router(build_env_router(registry))
    from .env.mcp_api import build_mcp_router
    app.include_router(build_mcp_router(store))
    from .env.project_api import build_project_router
    router_kwargs = {}
    if popen is not None:
        router_kwargs["popen"] = popen
    if image_exists_fn is not None:
        router_kwargs["image_exists_fn"] = image_exists_fn
    if build_image_fn is not None:
        router_kwargs["build_image_fn"] = build_image_fn
    app.include_router(build_project_router(store, registry, monitor, **router_kwargs))
```

(остальные `include_router` в `create_app` — без изменений)

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_project_api.py -q -k check_image`
Expected: PASS (2 passed)

- [ ] **Step 5: Регрессия + коммит**

Run: `cd app && python -m pytest tests/env/test_project_api.py -q`
Expected: PASS (все прежние тесты зелёные)

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/project_api.py app/src/agentmon/api.py app/tests/env/test_project_api.py
git commit -m "feat(project-api): эндпоинт check-image для мастера docker-проекта

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Сборка образа и валидация дистрибутива в create-флоу

**Files:**
- Modify: `app/src/agentmon/env/project_api.py` (`_prepare_install`, `create`, `create/stream`)
- Test: `app/tests/env/test_project_api.py`

**Interfaces:**
- Consumes: `image_tag`, `image_exists_fn`, `build_image_fn` (Task 4),
  `docker_host_from_conn`.
- Produces: поведение create-флоу для docker:
  - `conn["image"] = image_tag(platform_version)` записывается в реестр;
  - если образа нет и `body["distr_path"]` пуст → `HTTPException(400)`;
  - если образа нет и `distr_path` задан → сборка перед установкой окружения
    (в `create` — молча до конца; в `create/stream` — лог сборки в поток).

- [ ] **Step 1: Написать падающие тесты**

Дописать в `app/tests/env/test_project_api.py`:

```python
def _docker_client(tmp_path, *, exists, build_lines=None, build_rc_ok=True):
    """TestClient с docker-бэкендом и инъекцией image/build функций.

    Провиженинг docker идёт через RecordingProvisioner (без реального docker).
    """
    from agentmon.backends import RunResult

    reg_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(reg_db)
    queue = TaskQueue(reg_db)

    class RecProv:
        def __init__(self): self.runs = []
        def write_text(self, p, c): pass
        def write_bytes(self, p, d): pass
        def put_tree(self, s, d, skip=None): pass
        def mkdirs(self, paths): pass
        def exists(self, p): return False
        def is_file(self, p): return False
        def is_empty_dir(self, p): return True
        def read_text(self, p): return ""
        def which(self, t): return "/usr/bin/" + t
        def python_cmd(self): return ["python3"]
        def venv_python(self, d): return d + "/.venv/bin/python"
        def tempdir(self): return "/tmp"
        def run(self, cmd, cwd=None, timeout=None):
            self.runs.append(cmd); return RunResult(0, "", "")

    prov = RecProv()

    class Backends:
        def get(self, project):
            return SimpleNamespace(provisioner=prov)

    mon = Monitor(registry, Backends(), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)

    def fake_exists(tag, docker_host=None, run=None):
        return exists

    def fake_build(distr_path, platform_version, docker_host=None, popen=None):
        for ln in (build_lines or []):
            yield ln
        if not build_rc_ok:
            raise RuntimeError("build failed")

    app = create_app(registry=registry, queue=queue, monitor=mon, store=store,
                     image_exists_fn=fake_exists, build_image_fn=fake_build)
    return TestClient(app), registry


def _docker_body(tmp_path, **extra):
    d = tmp_path / "proj"; d.mkdir()
    body = {
        "name": "dockerproj", "path": str(d),
        "identifier": "dev", "email": "d@e.x",
        "platform_version": "8.3.27",
        "db_connection": "", "backend": "docker",
        "conn": {}, "install_tools": False, "git_init": False,
    }
    body.update(extra)
    return body


def test_docker_create_requires_distr_when_no_image(tmp_path):
    c, _ = _docker_client(tmp_path, exists=False)
    r = c.post("/api/env/projects/create", json=_docker_body(tmp_path))
    assert r.status_code == 400
    assert "дистрибутив" in r.json()["detail"].lower()


def test_docker_create_sets_image_in_conn(tmp_path):
    c, registry = _docker_client(tmp_path, exists=True)
    r = c.post("/api/env/projects/create", json=_docker_body(tmp_path))
    assert r.status_code == 200
    entry = next(p for p in registry.list() if p.name == "dockerproj")
    assert (entry.conn or {}).get("image") == "ai1c-agent:8.3.27"


def test_docker_create_stream_runs_build_when_missing(tmp_path):
    c, _ = _docker_client(tmp_path, exists=False,
                          build_lines=["Step 1/5\n", "Successfully built\n"])
    body = _docker_body(tmp_path, distr_path="/tmp/server64_8_3_27.zip")
    r = c.post("/api/env/projects/create/stream", json=body)
    assert r.status_code == 200
    text = r.text
    assert "Step 1/5" in text
    assert "Successfully built" in text
    assert "✓ Проект создан" in text


def test_docker_create_stream_build_failure_marks_error(tmp_path):
    c, _ = _docker_client(tmp_path, exists=False, build_lines=["boom\n"],
                          build_rc_ok=False)
    body = _docker_body(tmp_path, distr_path="/tmp/server64_8_3_27.zip")
    r = c.post("/api/env/projects/create/stream", json=body)
    assert "✗" in r.text
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_project_api.py -q -k docker_create`
Expected: FAIL (нет валидации/сборки; `conn["image"]` не проставляется)

- [ ] **Step 3: Реализация**

В `app/src/agentmon/env/project_api.py`, в `_prepare_install`, заменить блок
docker-шима (`project_api.py:110-113`) на:

```python
        # Docker: образ тегируется версией платформы и переиспользуется.
        # platform_dir вшит в образ (single source of truth: docker.py).
        docker_build = None  # (distr_path, version, docker_host) если нужна сборка
        if body.get("backend") == "docker":
            if not body.get("platform_dir"):
                body = {**body, "platform_dir": DEFAULT_PLATFORM_DIR}
            tag = docker_image.image_tag(body.get("platform_version", ""))
            conn = dict(body.get("conn") or {})
            conn["image"] = tag
            body = {**body, "conn": conn}
            docker_host = docker_host_from_conn(conn)
            if not image_exists_fn(tag, docker_host=docker_host):
                if not body.get("distr_path"):
                    raise HTTPException(
                        status_code=400,
                        detail=("для docker нужно указать путь к дистрибутиву "
                                "платформы: образа %s ещё нет" % tag),
                    )
                docker_build = (body["distr_path"],
                                body.get("platform_version", ""), docker_host)
```

Далее в `_prepare_install`, где формируется возврат (`project_api.py:175`
`return pid, config, prov, backend, conn`), заменить на возврат с `docker_build`:

```python
        return pid, config, prov, backend, conn, docker_build
```

Обновить распаковку в `create_project` (`project_api.py:195`):

```python
    @router.post("/api/env/projects/create")
    def create_project(body: dict):
        pid, config, prov, backend, conn, docker_build = _prepare_install(body)
        if docker_build is not None:
            # собрать образ до установки окружения; лог не стримим (блокирующий путь)
            for _ in build_image_fn(docker_build[0], docker_build[1],
                                    docker_host=docker_build[2]):
                pass
        events = list(_install_iter(config, body, prov, backend, conn))
        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        return {"project": project, "events": [asdict(e) for e in events]}
```

Обновить `create_project_stream` (`project_api.py:203-223`):

```python
    @router.post("/api/env/projects/create/stream")
    def create_project_stream(body: dict):
        pid, config, prov, backend, conn, docker_build = _prepare_install(body)

        def gen():
            yield f"▶ Создание проекта «{config.project_name}» ({config.project_dir})\n"
            failed = False
            try:
                if docker_build is not None:
                    yield f"[образ] сборка ai1c-agent:{docker_build[1]} из дистрибутива\n"
                    for line in build_image_fn(docker_build[0], docker_build[1],
                                               docker_host=docker_build[2]):
                        yield line
                for ev in _install_iter(config, body, prov, backend, conn):
                    detail = f" {ev.detail}" if ev.detail else ""
                    yield f"[{ev.step}] {ev.status}{detail}\n"
                    if ev.status == "error":
                        failed = True
            except Exception as exc:                       # noqa: BLE001
                failed = True
                yield f"✗ Ошибка: {exc}\n"
            yield ("\n✓ Проект создан\n" if not failed
                   else "\n✗ Установка завершилась с ошибкой\n")

        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_project_api.py -q -k docker_create`
Expected: PASS (4 passed)

- [ ] **Step 5: Регрессия + коммит**

Run: `cd app && python -m pytest tests/env/test_project_api.py tests/env/test_docker_create.py -q`
Expected: PASS (прежние docker-create и project_api тесты зелёные — `conn["image"]` не ломает их)

```bash
cd /home/uam/projects/ai_template
git add app/src/agentmon/env/project_api.py app/tests/env/test_project_api.py
git commit -m "feat(project-api): сборка образа и валидация дистрибутива в create-флоу

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Мастер (web) — поле дистрибутива и вызов check-image

**Files:**
- Modify: `app/web/project-wizard.html`
- Modify: `app/web/project-wizard.js`
- Test: `app/tests/env/test_project_wizard_page.py`

**Interfaces:**
- Consumes: `POST /api/env/projects/check-image` (Task 4); поле `distr_path`
  уходит в теле `create`/`create/stream` (Task 5).
- Produces: UI-элемент `id="distrPath"` в блоке docker-полей; JS дёргает
  `check-image` и показывает/прячет поле.

- [ ] **Step 1: Написать падающие content-тесты**

Дописать в `app/tests/env/test_project_wizard_page.py`:

```python
# ── distr / check-image (docker) ─────────────────────────────────────────────

def test_html_has_distr_path_input():
    assert 'id="distrPath"' in _html(), "Нет поля distrPath в project-wizard.html"


def test_html_has_distr_fields_container():
    assert 'id="distrFields"' in _html(), "Нет контейнера distrFields"


def test_js_calls_check_image_endpoint():
    assert "/api/env/projects/check-image" in _js()


def test_js_sends_distr_path_on_create():
    assert "distr_path" in _js()
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_project_wizard_page.py -q -k "distr or check_image"`
Expected: FAIL (элементов/строк нет)

- [ ] **Step 3: Реализация — HTML**

В `app/web/project-wizard.html` найти блок docker-полей (рядом с существующим
`id="sshFields"` / выбором backend) и добавить контейнер поля дистрибутива.
Вставить сразу после блока с выбором версии платформы:

```html
    <div id="distrFields" style="display:none">
      <label for="distrPath">Путь к дистрибутиву платформы (.zip)</label>
      <input type="text" id="distrPath"
             placeholder="/путь/к/server64_8_3_27_1786.zip" />
      <small id="distrHint">Нужен только для первой сборки образа этой версии.</small>
    </div>
```

- [ ] **Step 4: Реализация — JS**

В `app/web/project-wizard.js`:

(а) Функция проверки наличия образа — добавить рядом с прочими хелперами:

```javascript
  async function refreshDistrField() {
    const backend = document.getElementById('backend').value;
    const distrFields = document.getElementById('distrFields');
    const platformVersion =
      (document.getElementById('platformVersion')?.value || '').trim();
    if (backend !== 'docker' || !platformVersion) {
      distrFields.style.display = 'none';
      return;
    }
    try {
      const resp = await fetch('/api/env/projects/check-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform_version: platformVersion,
          backend: backend,
          conn: typeof collectConn === 'function' ? collectConn() : {},
        }),
      });
      const data = await resp.json();
      // образа нет → поле обязательно и видимо; есть → прячем
      distrFields.style.display = data.exists ? 'none' : 'block';
      document.getElementById('distrPath').required = !data.exists;
    } catch (e) {
      // при ошибке проверки показываем поле (безопаснее требовать дистрибутив)
      distrFields.style.display = 'block';
    }
  }

  document.getElementById('backend')
    .addEventListener('change', refreshDistrField);
  document.getElementById('platformVersion')
    ?.addEventListener('change', refreshDistrField);
```

> Примечание для исполнителя: сверься с реальными `id` в
> `project-wizard.html` (например поле версии платформы и функция сбора conn).
> Если имена отличаются (`platformVersion`/`collectConn`), подставь фактические,
> сохранив поведение. Тесты проверяют наличие строк `check-image` и `distr_path`.

(б) В месте сборки тела запроса `create`/`create/stream` добавить поле:

```javascript
      body.distr_path = (document.getElementById('distrPath')?.value || '').trim();
```

- [ ] **Step 5: Запустить content-тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_project_wizard_page.py -q`
Expected: PASS (прежние + 4 новых зелёные)

- [ ] **Step 6: Коммит**

```bash
cd /home/uam/projects/ai_template
git add app/web/project-wizard.html app/web/project-wizard.js app/tests/env/test_project_wizard_page.py
git commit -m "feat(wizard): поле дистрибутива и проверка наличия образа для docker

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Финальная регрессия всего пакета

**Files:** нет (только прогон).

- [ ] **Step 1: Прогнать весь тест-сьют приложения**

Run: `cd app && python -m pytest -q`
Expected: PASS (без новых падений; docker-build нигде не вызывается реально)

- [ ] **Step 2: Если всё зелёное — зафиксировать статус плана**

Отметить план выполненным (все чекбоксы закрыты). Коммит не требуется, если
регрессия ничего не меняла.

---

## Self-Review

**Spec coverage:**
- Dockerfile (свой, лёгкий, без deps) → Task 3 ✓
- `image_tag`/`image_exists`/`build_agent_image` → Tasks 1, 2 ✓
- `check-image` эндпоинт → Task 4 ✓
- `_prepare_install`: `conn["image"]`, 400 при отсутствии образа+пустом distr,
  `platform_dir` по умолчанию → Task 5 ✓
- Сборка первым шагом в `create` и `create/stream`, лог в поток → Task 5 ✓
- Мастер: поле дистрибутива, обязательное только когда образа нет → Task 6 ✓
- Локальный и удалённый демон (`-H`) → Tasks 1, 2 (тесты docker_host) ✓
- Бэкенд берёт тег из `conn["image"]` → существующий `factory.py:23`, правок нет ✓

**Placeholder scan:** код приведён полностью во всех шагах; в Task 6 оставлена
явная сверка `id` мастера — это необходимая адаптация к существующему HTML, а не
заглушка (тесты фиксируют инварианты `check-image`/`distr_path`).

**Type consistency:** `image_tag(str)->str`, `image_exists(tag, docker_host=None,
run=...)->bool`, `build_agent_image(distr_path, platform_version, docker_host=None,
popen=...)->Iterator[str]` — имена и сигнатуры совпадают между Tasks 1–5.
`_prepare_install` теперь возвращает 6-кортеж (добавлен `docker_build`) —
распаковка обновлена в обоих вызывающих (`create`, `create/stream`).

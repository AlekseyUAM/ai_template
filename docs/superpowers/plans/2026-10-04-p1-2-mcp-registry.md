# P1.2 — Справочник MCP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Справочник MCP: стандартные пресеты (вкл. 1c-md как расширение), подъём docker-MCP с логом, CRUD через McpRepo, API и web-страница.

**Tech Stack:** Python 3.10+ (stdlib subprocess), FastAPI, pytest. Без сборки.

## Global Constraints
- Стандартных MCP пять: `1c-md` (extension, cfe-скачивание, НЕ docker), `1c-syntax-checker-mcp`, `bsl-platform-context`, `1c-naparnic` (+токен), `code-index` (docker, порт).
- Подъём docker-MCP: порт на `127.0.0.1`; лог запуска показывается (одноразовый, не бесконечный SSE). `run` инъектируется в тестах (без живого докера).
- CRUD поверх `McpRepo` (P1.1). `create_app` получает опциональный `store` (Db); env-тесты не ломаются (store=None).
- Тексты на русском; тёмная тема GitHub на странице.

## File Structure
- Modify: `app/src/agentmon/env/mcp_catalog.py` (+поля kind/download/purpose, 1c-md=extension)
- Create: `app/src/agentmon/env/mcp_docker.py`
- Create: `app/src/agentmon/env/mcp_api.py`
- Modify: `app/src/agentmon/api.py` (параметр store + подключить mcp-роутер + страница `/mcp`)
- Create: `app/web/mcp.html`, `app/web/mcp.js`; Modify `app/web/index.html` (ссылка)
- Test: `app/tests/env/test_mcp_catalog_ext.py`, `test_mcp_docker.py`, `test_mcp_api.py`, `test_mcp_page.py`

---

## Task 1: Пресеты (расширение mcp_catalog)

**Files:** Modify `app/src/agentmon/env/mcp_catalog.py`; Test `app/tests/env/test_mcp_catalog_ext.py`.
**Interfaces:** `McpSpec` +поля `kind: str = "docker"`, `needs_token: bool = False`, `download: str | None = None` (после существующих, с дефолтами — позиционные вызовы не ломаются). `1c-md` → `kind="extension"`, `download="deps/mcp_tools_cfe/MCP_Сервер.cfe"`. `1c-naparnic` → `needs_token=True`. `build_mcp_json`/`build_compose` не менять.

- [ ] **Step 1: failing test**
```python
# app/tests/env/test_mcp_catalog_ext.py
from agentmon.env.mcp_catalog import CATALOG


def test_1c_md_is_extension():
    s = CATALOG["1c-md"]
    assert s.kind == "extension"
    assert s.download and s.download.endswith("MCP_Сервер.cfe")


def test_docker_presets_have_port():
    for k in ("1c-syntax-checker-mcp", "bsl-platform-context",
              "1c-naparnic", "code-index"):
        s = CATALOG[k]
        assert s.kind == "docker" and s.default_port


def test_naparnic_needs_token():
    assert CATALOG["1c-naparnic"].needs_token is True
```

- [ ] **Step 2: run (fails).** `cd app && PYTHONPATH=src python -m pytest tests/env/test_mcp_catalog_ext.py -q`
- [ ] **Step 3: implement** — добавить три поля в `McpSpec` (с дефолтами), проставить в CATALOG: `1c-md` c `kind="extension", download="deps/mcp_tools_cfe/MCP_Сервер.cfe"`; `1c-naparnic` с `needs_token=True`. Существующие позиционные аргументы оставить; новые — ключевыми.
- [ ] **Step 4: run (pass)** + прогнать `tests/env/test_mcp_catalog.py` (старые не сломаны).
- [ ] **Step 5: commit** `git commit -m "feat(mcp): пресеты справочника (1c-md=extension, токены)"`

---

## Task 2: Подъём в Docker (mcp_docker.py)

**Files:** Create `app/src/agentmon/env/mcp_docker.py`; Test `app/tests/env/test_mcp_docker.py`.
**Interfaces:**
- `launch(name, image, port, *, token_env=None, token=None, run=subprocess.run) -> dict` → `{"ok": bool, "container": name, "log": str}`; команда `docker run -d --name <name> -p 127.0.0.1:port:port [-e token_env=token] image`.
- `status(name, run=subprocess.run) -> str` → "running" | "absent".
- `stop(name, run=subprocess.run) -> dict` → `{"ok": bool, "log": str}` (`docker rm -f`).

- [ ] **Step 1: failing test**
```python
# app/tests/env/test_mcp_docker.py
from agentmon.env import mcp_docker


class FakeRun:
    def __init__(self, rc=0, out="", err=""):
        self.calls = []; self._rc, self._out, self._err = rc, out, err
    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        class R: pass
        R.returncode=self._rc; R.stdout=self._out; R.stderr=self._err
        return R


def test_launch_builds_command():
    fake = FakeRun(out="abc123\n")
    res = mcp_docker.launch("code-index", "img:latest", 8815, run=fake)
    assert res["ok"] and "abc123" in res["log"]
    cmd = fake.calls[0]
    assert "run" in cmd and "127.0.0.1:8815:8815" in cmd and "img:latest" in cmd


def test_launch_with_token():
    fake = FakeRun()
    mcp_docker.launch("1c-naparnic", "img", 8814, token_env="NAPARNIC_TOKEN",
                      token="secret", run=fake)
    joined = " ".join(fake.calls[0])
    assert "-e" in fake.calls[0] and "NAPARNIC_TOKEN=secret" in joined


def test_launch_failure_reports_log():
    fake = FakeRun(rc=1, err="нет образа")
    res = mcp_docker.launch("x", "img", 8811, run=fake)
    assert res["ok"] is False and "нет образа" in res["log"]


def test_stop_command():
    fake = FakeRun()
    mcp_docker.stop("x", run=fake)
    assert fake.calls[0][:3] == ["docker", "rm", "-f"]
```

- [ ] **Step 2: run (fails).**
- [ ] **Step 3: implement**
```python
# app/src/agentmon/env/mcp_docker.py
"""Подъём MCP-серверов в Docker. Команды через инъектируемый `run` (тесты — без докера)."""
import subprocess


def launch(name, image, port, *, token_env=None, token=None, run=subprocess.run) -> dict:
    cmd = ["docker", "run", "-d", "--name", name,
           "-p", f"127.0.0.1:{port}:{port}"]
    if token_env and token:
        cmd += ["-e", f"{token_env}={token}"]
    cmd.append(image)
    r = run(cmd, capture_output=True, text=True)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "container": name, "log": log}


def status(name, run=subprocess.run) -> str:
    r = run(["docker", "inspect", "-f", "{{.State.Running}}", name],
            capture_output=True, text=True)
    if r.returncode != 0:
        return "absent"
    return "running" if "true" in (r.stdout or "").lower() else "absent"


def stop(name, run=subprocess.run) -> dict:
    r = run(["docker", "rm", "-f", name], capture_output=True, text=True)
    log = (getattr(r, "stdout", "") or "") + (getattr(r, "stderr", "") or "")
    return {"ok": r.returncode == 0, "log": log}
```

- [ ] **Step 4: run (pass).**
- [ ] **Step 5: commit** `git commit -m "feat(mcp): подъём MCP в Docker с логом"`

---

## Task 3: API-роутер справочника MCP

**Files:** Create `app/src/agentmon/env/mcp_api.py`; Modify `app/src/agentmon/api.py`; Test `app/tests/env/test_mcp_api.py`.

**Interfaces:**
- `build_mcp_router(store) -> APIRouter`. `store` — объект `Db` (P1.1) или None.
- `create_app(registry, queue, monitor, lifespan=None, store=None)` — добавить параметр `store`; `app.include_router(build_mcp_router(store))`.
- Маршруты (McpRepo поверх store):
  - `GET /api/mcp` → `{mcp:[...]}`; `GET /api/mcp/standard` → пресеты каталога (id/title/kind/default_port/needs_token/download).
  - `POST /api/mcp` body `{name, purpose?, kind?, standard_key?, connection_json?, port?, token_env?}` → создать (для standard — заполнить из пресета).
  - `PUT /api/mcp/{id}`, `DELETE /api/mcp/{id}`.
  - `POST /api/mcp/{id}/launch` body `{port?, token?}` → для extension (`standard_key=="1c-md"`/kind extension) → 400 «это расширение, скачайте cfe»; иначе `mcp_docker.launch(...)` → `{ok, container, log}`.
  - `POST /api/mcp/{id}/stop` → `mcp_docker.stop`.
  - `GET /api/mcp/{id}/download` → для `1c-md` FileResponse `deps/mcp_tools_cfe/MCP_Сервер.cfe` (404 если нет).
- Если `store is None` — операции с БД возвращают 503 «хранилище не настроено»; `/standard` работает всегда.

- [ ] **Step 1: failing test**
```python
# app/tests/env/test_mcp_api.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def make(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db")); init_schema(store)
    return TestClient(create_app(registry=ProjectRegistry(db), queue=TaskQueue(db),
                                 monitor=mon, store=store))


def test_standard_presets(tmp_path):
    data = make(tmp_path).get("/api/mcp/standard").json()["standard"]
    ids = {s["id"] for s in data}
    assert {"1c-md", "code-index", "1c-naparnic"} <= ids


def test_crud_custom_mcp(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={"name": "my", "kind": "custom",
                                 "connection_json": '{"url":"http://x"}'})
    assert r.status_code == 200
    mid = r.json()["mcp"]["id"]
    assert any(m["name"] == "my" for m in c.get("/api/mcp").json()["mcp"])
    assert c.delete(f"/api/mcp/{mid}").status_code == 200


def test_launch_extension_rejected(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={"name": "1c-md", "kind": "extension",
                                   "standard_key": "1c-md"}).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={})
    assert r.status_code == 400
```

- [ ] **Step 2: run (fails).** `cd app && PYTHONPATH=src:tests python -m pytest tests/env/test_mcp_api.py -q`
- [ ] **Step 3: implement** `mcp_api.py` (McpRepo(store); пресеты из CATALOG; launch через `mcp_docker`, инъекция `run` опционально через модульную функцию — в тестах подменять не обязательно, extension-ветка проверяется до докера). Подключить `store` в `create_app` и роутер. Для launch в тестах docker не вызывается (тест проверяет только extension→400); для docker-ветки можно не тестировать живой запуск.
- [ ] **Step 4: run (pass)** + полный набор.
- [ ] **Step 5: commit** `git commit -m "feat(mcp): API справочника MCP (CRUD, пресеты, подъём, скачивание)"`

---

## Task 4: Web-страница «Справочник MCP»

**Files:** Create `app/web/mcp.html`, `app/web/mcp.js`; Modify `app/src/agentmon/api.py` (маршрут `/mcp`), `app/web/index.html` (ссылка); Test `app/tests/env/test_mcp_page.py`.

- [ ] **Step 1: failing test** — GET `/mcp` → 200 и содержит «Справочник MCP» (как в `test_create_task_page.py`, с `store` в create_app).
- [ ] **Step 2: run (fails).**
- [ ] **Step 3: implement** — `mcp.html` (тёмная тема `/static/github-dark.css`): список MCP (GET /api/mcp), форма добавления произвольного (имя/назначение/connection json), кнопки «добавить стандартный» (GET /api/mcp/standard → выбор), у docker-MCP поля порт/токен + кнопки «Поднять»(POST launch → показать `log`)/«Остановить», у `1c-md` ссылка «Скачать расширение» (`/api/mcp/{id}/download`). `mcp.js` реализует. Маршрут `/mcp` (FileResponse + no-cache) рядом с остальными; ссылка в верхнем меню index.html.
- [ ] **Step 4: run (pass)** + полный набор.
- [ ] **Step 5: commit** `git commit -m "feat(mcp): web-страница «Справочник MCP»"`

---

## Self-Review
- Пресеты (T1), docker-подъём (T2), API (T3), страница (T4) — покрывают спек.
- `create_app` получает опциональный `store` → env-тесты не ломаются.
- Подъём docker тестируется через инъекцию `run`; extension-ветка (1c-md) — без докера.
- Отложено: генерация `.mcp.json` проекта из справочника — в P1.3 (мастер); живой SSE-стрим лога — позже (сейчас одноразовый лог запуска).

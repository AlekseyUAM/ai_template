# Вид MCP «Индексированная кодовая база (локально)» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить вид MCP, разворачивающий bsl-indexer нативно (скачать бинарь с GitHub Releases, написать `daemon.toml`, поставить индексатор и MCP-сервер в user-level автозапуск под Windows/Linux/macOS), и переименовать существующий docker-вид.

**Architecture:** Два вида MCP делят ядро code-index (генератор `daemon.toml`, строка подключения) и различаются бэкендом развёртывания. Новый код: резолвер/загрузчик релиза (`code_index_release.py`), per-OS автозапуск (`autostart.py`), оркестратор (`code_index_local.py`), новые эндпоинты API и ветка UI.

**Tech Stack:** Python 3 (stdlib `urllib`, `zipfile`, `tarfile`, `subprocess`), FastAPI (`StreamingResponse`), pytest; ванильный JS фронтенд.

## Global Constraints

- Алиас репозитория = имя проекта; `daemon.toml` `alias` и строка подключения берут одну и ту же строку. Нормализацию/slug НЕ применять.
- Автозапуск — **user-level** (без root/admin): Windows Scheduled Task `/SC ONLOGON`, Linux `systemd --user`, macOS LaunchAgent. Кнопка регистрирует автозапуск **и** стартует процессы сразу.
- Поддерживаемые платформы ровно как в релизах upstream: Windows x64, Linux x64, macOS arm64; иначе — внятная ошибка.
- GitHub: репозиторий `Regsorm/code-index-mcp`, релиз `releases/latest` (API `https://api.github.com/repos/Regsorm/code-index-mcp/releases/latest`).
- Внешние зависимости не добавлять — только stdlib. Все сетевые/ОС/subprocess-вызовы инъектируются (`fetch`/`run`/`platform_name`) ради тестируемости — тесты ничего реально не качают и не исполняют.
- Тесты и код — в стиле существующих `app/src/agentmon/env` и `app/tests/env`. Запуск: `cd app && python -m pytest <путь> -q`.

---

## File Structure

- Modify `app/src/agentmon/env/mcp_docker_recipes.py` — `_daemon_toml(alias)` → `_daemon_toml(alias, path)`.
- Modify `app/src/agentmon/store/schema.py`, `app/src/agentmon/store/mcp.py` — колонка `code_index_dir`.
- Modify `app/src/agentmon/env/mcp_types.py` — title docker-вида + новый вид `code-index-local`.
- Modify `app/src/agentmon/env/mcp_api.py` — persist `code_index_dir`; эндпоинты `deploy-local`.
- Create `app/src/agentmon/env/code_index_release.py` — резолв/загрузка релиза.
- Create `app/src/agentmon/env/autostart.py` — user-level автозапуск под 3 ОС.
- Create `app/src/agentmon/env/code_index_local.py` — оркестратор.
- Modify `app/web/mcp.js`, `app/web/mcp.html` — ветка `action="local"`.
- Tests: `app/tests/env/test_mcp_docker_recipes.py`, `app/tests/store/test_mcp.py`, `app/tests/env/test_mcp_types.py`, `app/tests/env/test_mcp_api.py`, и новые `test_code_index_release.py`, `test_autostart.py`, `test_code_index_local.py`.

---

## Task 1: Обобщить `_daemon_toml` до (alias, path)

**Files:**
- Modify: `app/src/agentmon/env/mcp_docker_recipes.py`
- Test: `app/tests/env/test_mcp_docker_recipes.py`

**Interfaces:**
- Produces: `_daemon_toml(alias: str, path: str) -> str` — текст daemon.toml с заданными alias и path секции `[[paths]]`.
- Consumes: `launch_params(...)` вызывает `_daemon_toml(project_name, "/repos/src")`.

- [ ] **Step 1: Обновить тест daemon.toml на path-параметр**

В `test_code_index_requires_catalog_dir` заменить проверку на обе величины:

```python
    text = daemon.read_text(encoding="utf-8")
    assert 'path = "/repos/src"' in text
    assert 'alias = "МойПроект"' in text
```

- [ ] **Step 2: Прогнать — тест падает**

Run: `cd app && python -m pytest tests/env/test_mcp_docker_recipes.py::test_code_index_requires_catalog_dir -q`
Expected: FAIL (`_daemon_toml` принимает 1 аргумент / path не совпал).

- [ ] **Step 3: Параметризовать `_daemon_toml`**

Заменить функцию в `mcp_docker_recipes.py`:

```python
def _daemon_toml(alias: str, path: str) -> str:
    """Текст daemon.toml для code-index: alias репозитория = имя проекта,
    path — каталог кодовой базы (в контейнере `/repos/src`, локально — реальный
    путь на хосте). alias и `repo="..."` в подсказках агенту совпадают."""
    return f"""# Сгенерировано автоматически при развёртывании code-index.
[daemon]
http_host = "127.0.0.1"
http_port = 0
log_level = "info"

[[paths]]
path = "{path}"
alias = "{alias}"
language = "bsl"
"""
```

В `launch_params` (ветка `recipe.catalog_mount`) обновить вызов:

```python
        (sp / "daemon.toml").write_text(_daemon_toml(project_name, "/repos/src"),
                                        encoding="utf-8")
```

- [ ] **Step 4: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_mcp_docker_recipes.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/mcp_docker_recipes.py app/tests/env/test_mcp_docker_recipes.py
git commit -m "refactor(code-index): _daemon_toml(alias) → (alias, path)"
```

---

## Task 2: Колонка `code_index_dir` (схема + репозиторий)

**Files:**
- Modify: `app/src/agentmon/store/schema.py`
- Modify: `app/src/agentmon/store/mcp.py`
- Test: `app/tests/store/test_mcp.py`

**Interfaces:**
- Produces: `McpRepo.add(..., code_index_dir=None, ...)`; строка `mcp_servers` содержит ключ `code_index_dir`.

- [ ] **Step 1: Тест на roundtrip `code_index_dir`**

Добавить в `app/tests/store/test_mcp.py` (паттерн файла — `connect` + `init_schema` + `McpRepo(db)` напрямую, без фикстуры):

```python
def test_add_persists_code_index_dir(tmp_path):
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    m = McpRepo(db)
    mid = m.add(name="idx-local", kind="local",
                standard_key="code-index-local",
                catalog_dir="/code/cfg", project_name="proj",
                code_index_dir="/opt/ci")
    row = m.get(mid)
    assert row["code_index_dir"] == "/opt/ci"
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/store/test_mcp.py::test_add_persists_code_index_dir -q`
Expected: FAIL (`add() got unexpected keyword 'code_index_dir'`).

- [ ] **Step 3: Схема — колонка + миграция**

В `schema.py`, `CREATE TABLE ... mcp_servers`, в строке с `catalog_dir TEXT, platform_path TEXT,` сделать:

```python
        mcp_name TEXT, url TEXT, db_name TEXT, catalog_dir TEXT, platform_path TEXT,
        project_name TEXT, code_index_dir TEXT,
        created_at {ts})""")
```

В `_ensure_columns(db, "mcp_servers", {...})` добавить ключ:

```python
        "catalog_dir": "TEXT", "platform_path": "TEXT", "project_name": "TEXT",
        "code_index_dir": "TEXT",
```

- [ ] **Step 4: Репозиторий — параметр и колонка**

В `store/mcp.py`, в сигнатуре `add(...)` после `project_name=None,` добавить `code_index_dir=None,`. В списке `columns` после `"project_name",` добавить `"code_index_dir",`; в `params` после `project_name,` добавить `code_index_dir,`.

- [ ] **Step 5: Прогнать — проходит**

Run: `cd app && python -m pytest tests/store/test_mcp.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/store/schema.py app/src/agentmon/store/mcp.py app/tests/store/test_mcp.py
git commit -m "feat(store): колонка code_index_dir для локального code-index"
```

---

## Task 3: Виды MCP — title docker-вида + новый `code-index-local`

**Files:**
- Modify: `app/src/agentmon/env/mcp_types.py`
- Test: `app/tests/env/test_mcp_types.py`

**Interfaces:**
- Produces: `get_type("code-index").title == "Индексированная кодовая база (в Docker локально)"`; `get_type("code-index-local")` с `action="local"`, `required=("catalog_dir","project_name","code_index_dir","port")`.

- [ ] **Step 1: Тесты на оба вида**

Добавить в `test_mcp_types.py`:

```python
def test_docker_code_index_retitled():
    t = get_type("code-index")
    assert t.title == "Индексированная кодовая база (в Docker локально)"
    assert t.action == "docker"


def test_code_index_local_type():
    t = get_type("code-index-local")
    assert t.title == "Индексированная кодовая база (локально)"
    assert t.action == "local"
    assert t.required == ("catalog_dir", "project_name", "code_index_dir", "port")
    for f in ("catalog_dir", "project_name", "code_index_dir", "port"):
        assert f in t.fields
    assert t.field_labels["code_index_dir"] == "Каталог code_index"
    assert t.field_labels["port"] == "Порт code_index"
    assert t.defaults["mcp_name"] == "code_index"
    assert t.defaults["port"] == 8005
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_mcp_types.py -q`
Expected: FAIL (title прежний / `get_type("code-index-local")` → KeyError).

- [ ] **Step 3: Сменить title docker-вида**

В `mcp_types.py` у `McpType(key="code-index", ...)` заменить строку title на:

```python
        title="Индексированная кодовая база (в Docker локально)",
```

- [ ] **Step 4: Добавить новый вид**

Сразу после закрывающей `),` блока `code-index` (перед `]`, закрывающим `MCP_TYPES`) вставить:

```python
    McpType(
        key="code-index-local",
        title="Индексированная кодовая база (локально)",
        fields=("name", "mcp_name", "purpose", "url", "port",
                "catalog_dir", "project_name", "code_index_dir", "connection"),
        connection_template=_HTTP_PORT,
        defaults={
            "mcp_name": "code_index",
            "url": "localhost",
            "port": 8005,
            "purpose": ("Полнотекстовый поиск по функциям и классам, граф "
                        "вызовов, паспорт объекта, смысловой поиск процедур по "
                        "именам, синонимам и комментариям"),
        },
        action="local",
        required=("catalog_dir", "project_name", "code_index_dir", "port"),
        field_labels={"project_name": "Имя проекта (alias репозитория)",
                      "code_index_dir": "Каталог code_index",
                      "port": "Порт code_index"},
    ),
```

- [ ] **Step 5: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_mcp_types.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_types.py app/tests/env/test_mcp_types.py
git commit -m "feat(mcp): вид «Индексированная кодовая база (локально)» + ретайтл docker"
```

---

## Task 4: API — persist `code_index_dir` в create/update

**Files:**
- Modify: `app/src/agentmon/env/mcp_api.py`
- Test: `app/tests/env/test_mcp_api.py`

**Interfaces:**
- Produces: `POST /api/mcp` и `PUT /api/mcp/{id}` принимают и сохраняют `code_index_dir`.

- [ ] **Step 1: Тест roundtrip через API**

Добавить в `test_mcp_api.py`:

```python
def test_create_local_code_index_persists_fields(tmp_path):
    c = make(tmp_path)
    r = c.post("/api/mcp", json={
        "name": "idx-local", "kind": "local", "standard_key": "code-index-local",
        "mcp_name": "code_index", "url": "localhost", "port": 8005,
        "catalog_dir": "/code/cfg", "project_name": "proj",
        "code_index_dir": "/opt/ci",
    })
    assert r.status_code == 200
    row = r.json()["mcp"]
    assert row["code_index_dir"] == "/opt/ci"
    assert row["project_name"] == "proj"
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_mcp_api.py::test_create_local_code_index_persists_fields -q`
Expected: FAIL (`row["code_index_dir"]` = None).

- [ ] **Step 3: Чтение/проброс в create**

В `create_mcp`, после строки `project_name = body.get("project_name")` добавить:

```python
        code_index_dir = body.get("code_index_dir")
```

В вызове `repo.add(...)`, после `project_name=project_name,` добавить:

```python
            code_index_dir=code_index_dir,
```

- [ ] **Step 4: Разрешить поле в update**

В `update_mcp`, в множество `allowed` добавить `"code_index_dir"` (в ту же фигурную скобку, где `"project_name"`).

- [ ] **Step 5: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_mcp_api.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_api.py app/tests/env/test_mcp_api.py
git commit -m "feat(mcp-api): сохранение code_index_dir"
```

---

## Task 5: Резолв и загрузка релиза bsl-indexer

**Files:**
- Create: `app/src/agentmon/env/code_index_release.py`
- Test: `app/tests/env/test_code_index_release.py`

**Interfaces:**
- Produces:
  - `host_asset_key() -> tuple[str, str] | None` — `(os_marker, arch_marker)` для хоста (`("windows","x64")`/`("linux","x64")`/`("macos","arm64")`) или `None`.
  - `resolve_asset(release_json: dict, markers: tuple[str,str]) -> tuple[str, str]` — `(name, url)` ассета bsl-indexer; `ValueError` если не найден.
  - `download_binary(code_index_dir, *, fetch=..., log=None, platform_name=None) -> pathlib.Path` — качает и распаковывает бинарь, возвращает путь к нему.

- [ ] **Step 1: Тесты резолва (чистые функции)**

Создать `app/tests/env/test_code_index_release.py`:

```python
import pytest
from agentmon.env import code_index_release as R

_RELEASE = {"assets": [
    {"name": "code-index-linux-x64.tar.gz", "browser_download_url": "u1"},
    {"name": "bsl-indexer-linux-x64.tar.gz", "browser_download_url": "u2"},
    {"name": "bsl-indexer-windows-x64.zip", "browser_download_url": "u3"},
    {"name": "bsl-indexer-macos-arm64.tar.gz", "browser_download_url": "u4"},
]}


def test_host_asset_key_linux_x64(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    monkeypatch.setattr(R.platform, "machine", lambda: "x86_64")
    assert R.host_asset_key() == ("linux", "x64")


def test_host_asset_key_macos_arm64(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "darwin")
    monkeypatch.setattr(R.platform, "machine", lambda: "arm64")
    assert R.host_asset_key() == ("macos", "arm64")


def test_host_asset_key_unsupported(monkeypatch):
    monkeypatch.setattr(R.sys, "platform", "linux")
    monkeypatch.setattr(R.platform, "machine", lambda: "armv7l")
    assert R.host_asset_key() is None


def test_resolve_asset_picks_bsl_indexer():
    name, url = R.resolve_asset(_RELEASE, ("linux", "x64"))
    assert name == "bsl-indexer-linux-x64.tar.gz" and url == "u2"


def test_resolve_asset_missing_raises():
    with pytest.raises(ValueError, match="bsl-indexer"):
        R.resolve_asset({"assets": []}, ("linux", "x64"))
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_code_index_release.py -q`
Expected: FAIL (модуль отсутствует).

- [ ] **Step 3: Реализация резолва**

Создать `app/src/agentmon/env/code_index_release.py`:

```python
"""Скачивание готового бинаря bsl-indexer с GitHub Releases под текущий хост."""
import io
import json
import platform
import stat
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

GH_LATEST = "https://api.github.com/repos/Regsorm/code-index-mcp/releases/latest"


def host_asset_key():
    """Маркеры ассета bsl-indexer под хост или None, если платформа не из
    публикуемых upstream (Windows x64 / Linux x64 / macOS arm64)."""
    machine = platform.machine().lower()
    is_x64 = machine in ("x86_64", "amd64", "x64")
    is_arm64 = machine in ("arm64", "aarch64")
    if sys.platform.startswith("win") and is_x64:
        return ("windows", "x64")
    if sys.platform.startswith("linux") and is_x64:
        return ("linux", "x64")
    if sys.platform == "darwin" and is_arm64:
        return ("macos", "arm64")
    return None


def resolve_asset(release_json, markers):
    """(name, url) ассета bsl-indexer под платформу из JSON релиза."""
    os_m, arch_m = markers
    for a in release_json.get("assets", []):
        low = a["name"].lower()
        if "bsl-indexer" in low and os_m in low and arch_m in low:
            return a["name"], a["browser_download_url"]
    names = [a["name"] for a in release_json.get("assets", [])]
    raise ValueError(
        f"в релизе нет ассета bsl-indexer для {os_m}-{arch_m}; доступны: {names}")
```

- [ ] **Step 4: Прогнать — резолв проходит**

Run: `cd app && python -m pytest tests/env/test_code_index_release.py -q`
Expected: PASS.

- [ ] **Step 5: Тест загрузки (инъекция fetch, zip)**

Добавить в `test_code_index_release.py`:

```python
def _zip_bytes(names):
    buf = io.BytesIO()
    import zipfile as z
    with z.ZipFile(buf, "w") as zf:
        for n in names:
            zf.writestr(n, b"BINDATA")
    return buf.getvalue()


def test_download_binary_extracts_and_returns_path(tmp_path, monkeypatch):
    import io
    def fetch(url):
        if url == R.GH_LATEST:
            return json.dumps(_RELEASE).encode("utf-8")
        return _zip_bytes(["bsl-indexer.exe", "README.txt"])
    dest = tmp_path / "ci"
    path = R.download_binary(str(dest), fetch=fetch, platform_name="win32")
    assert path.name == "bsl-indexer.exe"
    assert path.exists()


def test_download_binary_unsupported_platform(tmp_path):
    with pytest.raises(ValueError, match="платформ"):
        R.download_binary(str(tmp_path), fetch=lambda u: b"", platform_name="sunos5")
```

(`globals()` в тесте уже содержит `import io`/`import json` из Step 1/здесь — продублировать импорты вверху файла: `import io, json`.)

- [ ] **Step 6: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_code_index_release.py -q`
Expected: FAIL (`download_binary` отсутствует).

- [ ] **Step 7: Реализация загрузки**

Дописать в `code_index_release.py`:

```python
def _default_fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ai1c-agentmon"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _host_markers(platform_name):
    """markers по явному platform_name (для тестов) или по хосту.

    При явном platform_name доверяем единственной публикуемой upstream арке на
    каждую ОС (Windows/Linux — x64, macOS — arm64)."""
    if platform_name is None:
        return host_asset_key()
    if platform_name.startswith("win"):
        return ("windows", "x64")
    if platform_name.startswith("linux"):
        return ("linux", "x64")
    if platform_name == "darwin":
        return ("macos", "arm64")
    return None


def _extract(blob, asset_name, dest):
    """Распаковать архив ассета в dest."""
    low = asset_name.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            zf.extractall(dest)
    elif low.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
            tf.extractall(dest)
    else:
        raise ValueError(f"неизвестный формат архива: {asset_name}")


def _find_binary(dest, os_marker):
    """Найти исполняемый bsl-indexer в распакованном дереве."""
    want = "bsl-indexer.exe" if os_marker == "windows" else "bsl-indexer"
    for p in Path(dest).rglob("*"):
        if p.is_file() and p.name == want:
            return p
    raise ValueError(f"в архиве не найден {want}")


def download_binary(code_index_dir, *, fetch=_default_fetch, log=None,
                    platform_name=None):
    """Скачать bsl-indexer под хост в code_index_dir, вернуть путь к бинарю."""
    log = log or (lambda s: None)
    markers = _host_markers(platform_name)
    if markers is None:
        raise ValueError("платформа не поддерживается "
                         "(нужны Windows x64, Linux x64 или macOS arm64)")
    log(f"Определение релиза для {markers[0]}-{markers[1]}…")
    release = json.loads(fetch(GH_LATEST).decode("utf-8"))
    name, url = resolve_asset(release, markers)
    log(f"Скачивание {name}…")
    blob = fetch(url)
    dest = Path(code_index_dir)
    dest.mkdir(parents=True, exist_ok=True)
    _extract(blob, name, dest)
    binary = _find_binary(dest, markers[0])
    if markers[0] != "windows":
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP
                     | stat.S_IXOTH)
    log(f"Бинарь установлен: {binary}")
    return binary
```

- [ ] **Step 8: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_code_index_release.py -q`
Expected: PASS.

- [ ] **Step 9: Коммит**

```bash
git add app/src/agentmon/env/code_index_release.py app/tests/env/test_code_index_release.py
git commit -m "feat(code-index): загрузка бинаря bsl-indexer с GitHub Releases"
```

---

## Task 6: User-level автозапуск под 3 ОС

**Files:**
- Create: `app/src/agentmon/env/autostart.py`
- Test: `app/tests/env/test_autostart.py`

**Interfaces:**
- Produces:
  - `windows_wrapper(argv, env) -> str`, `systemd_unit(argv, env, description) -> str`, `launchd_plist(label, argv, env) -> str` — чистые генераторы текста.
  - `install_and_start(name, argv, *, env, state_dir, home=None, run=..., platform_name=None) -> list[str]` — пишет файлы автозапуска, регистрирует и стартует; возвращает лог-строки.

- [ ] **Step 1: Тесты генераторов и диспетчеризации**

Создать `app/tests/env/test_autostart.py`:

```python
import pytest
from pathlib import Path
from agentmon.env import autostart as A


def test_systemd_unit_has_env_and_exec():
    unit = A.systemd_unit(["/opt/ci/bsl-indexer", "serve"],
                          {"CODE_INDEX_HOME": "/opt/ci", "MCP_HTTP_PORT": "8005"},
                          "ai1c code-index mcp")
    assert 'Environment="CODE_INDEX_HOME=/opt/ci"' in unit
    assert 'Environment="MCP_HTTP_PORT=8005"' in unit
    assert "ExecStart=/opt/ci/bsl-indexer serve" in unit
    assert "WantedBy=default.target" in unit


def test_launchd_plist_has_args_and_env():
    pl = A.launchd_plist("ai1c.ci.mcp", ["/opt/ci/bsl-indexer", "serve"],
                         {"MCP_HTTP_PORT": "8005"})
    assert "<string>/opt/ci/bsl-indexer</string>" in pl
    assert "<string>serve</string>" in pl
    assert "<key>MCP_HTTP_PORT</key><string>8005</string>" in pl
    assert "<key>RunAtLoad</key><true/>" in pl


def test_windows_wrapper_sets_env_and_runs():
    cmd = A.windows_wrapper(["C:\\ci\\bsl-indexer.exe", "serve"],
                            {"MCP_HTTP_PORT": "8005"})
    assert 'set "MCP_HTTP_PORT=8005"' in cmd
    assert "bsl-indexer.exe" in cmd


def test_install_and_start_linux(tmp_path, monkeypatch):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    home = tmp_path / "home"
    log = A.install_and_start(
        "ai1c-code-index-mcp-7", ["/opt/ci/bsl-indexer", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(tmp_path / "ci"),
        home=home, run=run, platform_name="linux")
    unit = home / ".config" / "systemd" / "user" / "ai1c-code-index-mcp-7.service"
    assert unit.exists()
    assert any("systemctl" in c and "enable" in c for c in calls)
    assert any("ExecStart" in l or "systemctl" in l or "юнит" in l.lower()
               for l in log)


def test_install_and_start_windows(tmp_path, monkeypatch):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    state = tmp_path / "ci"
    A.install_and_start(
        "ai1c-code-index-mcp-7", ["C:\\ci\\bsl-indexer.exe", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(state),
        home=tmp_path / "home", run=run, platform_name="win32")
    assert (state / "ai1c-code-index-mcp-7.cmd").exists()
    assert any("schtasks" in c and "/Create" in c for c in calls)
    assert any("schtasks" in c and "/Run" in c for c in calls)


def test_install_and_start_macos(tmp_path):
    calls = []
    def run(cmd, **k):
        calls.append(cmd)
        class R: returncode = 0; stdout = ""; stderr = ""
        return R()
    home = tmp_path / "home"
    A.install_and_start(
        "ai1c-code-index-mcp-7", ["/opt/ci/bsl-indexer", "serve"],
        env={"MCP_HTTP_PORT": "8005"}, state_dir=str(tmp_path / "ci"),
        home=home, run=run, platform_name="darwin")
    plist = home / "Library" / "LaunchAgents" / "ai1c-code-index-mcp-7.plist"
    assert plist.exists()
    assert any("launchctl" in c for c in calls)


def test_install_and_start_unsupported(tmp_path):
    with pytest.raises(ValueError, match="платформ"):
        A.install_and_start("n", ["x"], env={}, state_dir=str(tmp_path),
                            run=lambda *a, **k: None, platform_name="sunos5")
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_autostart.py -q`
Expected: FAIL (модуль отсутствует).

- [ ] **Step 3: Реализация**

Создать `app/src/agentmon/env/autostart.py`:

```python
"""User-level автозапуск процессов под Windows/Linux/macOS (без root/admin)."""
import subprocess
import sys
from pathlib import Path


def _q(a):
    """Кавычки вокруг аргумента, если есть пробел."""
    return f'"{a}"' if " " in a else a


def windows_wrapper(argv, env):
    """Текст .cmd: выставляет env и запускает процесс."""
    lines = ["@echo off"]
    for k, v in env.items():
        lines.append(f'set "{k}={v}"')
    lines.append(" ".join(_q(a) for a in argv))
    return "\r\n".join(lines) + "\r\n"


def systemd_unit(argv, env, description):
    """Текст systemd user-unit."""
    env_lines = "\n".join(f'Environment="{k}={v}"' for k, v in env.items())
    exec_start = " ".join(_q(a) for a in argv)
    return (f"[Unit]\nDescription={description}\n\n"
            f"[Service]\n{env_lines}\nExecStart={exec_start}\n"
            f"Restart=on-failure\n\n"
            f"[Install]\nWantedBy=default.target\n")


def launchd_plist(label, argv, env):
    """Текст LaunchAgent plist."""
    args = "".join(f"    <string>{a}</string>\n" for a in argv)
    envs = "".join(f"    <key>{k}</key><string>{v}</string>\n"
                   for k, v in env.items())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>\n'
            f'  <key>Label</key><string>{label}</string>\n'
            f'  <key>ProgramArguments</key><array>\n{args}  </array>\n'
            f'  <key>EnvironmentVariables</key><dict>\n{envs}  </dict>\n'
            '  <key>RunAtLoad</key><true/>\n'
            '  <key>KeepAlive</key><true/>\n'
            '</dict></plist>\n')


def _run_logged(run, cmd, log, *, check=True):
    res = run(cmd, capture_output=True, text=True)
    rc = getattr(res, "returncode", 0)
    log.append(f"$ {' '.join(cmd)} → код {rc}")
    if check and rc != 0:
        err = (getattr(res, "stderr", "") or "").strip()
        raise ValueError(f"команда не выполнена ({' '.join(cmd)}): {err}")
    return res


def _install_linux(name, argv, env, state_dir, home, run):
    log = []
    unit_dir = Path(home) / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit_path = unit_dir / f"{name}.service"
    unit_path.write_text(systemd_unit(argv, env, name), encoding="utf-8")
    log.append(f"Юнит: {unit_path}")
    _run_logged(run, ["systemctl", "--user", "daemon-reload"], log)
    _run_logged(run, ["systemctl", "--user", "enable", "--now", name], log)
    # best-effort: пережить ребут без входа
    _run_logged(run, ["loginctl", "enable-linger"], log, check=False)
    return log


def _install_windows(name, argv, env, state_dir, home, run):
    log = []
    wrapper = Path(state_dir) / f"{name}.cmd"
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text(windows_wrapper(argv, env), encoding="utf-8")
    log.append(f"Обёртка: {wrapper}")
    _run_logged(run, ["schtasks", "/Create", "/SC", "ONLOGON",
                      "/TN", name, "/TR", str(wrapper), "/F"], log)
    _run_logged(run, ["schtasks", "/Run", "/TN", name], log)
    return log


def _install_macos(name, argv, env, state_dir, home, run):
    log = []
    agents = Path(home) / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"{name}.plist"
    plist.write_text(launchd_plist(name, argv, env), encoding="utf-8")
    log.append(f"LaunchAgent: {plist}")
    _run_logged(run, ["launchctl", "unload", str(plist)], log, check=False)
    _run_logged(run, ["launchctl", "load", "-w", str(plist)], log)
    return log


def install_and_start(name, argv, *, env, state_dir, home=None,
                      run=subprocess.run, platform_name=None):
    """Зарегистрировать автозапуск процесса (user-level) и стартовать сразу."""
    home = Path(home) if home is not None else Path.home()
    pf = platform_name or sys.platform
    if pf.startswith("win"):
        return _install_windows(name, argv, env, state_dir, home, run)
    if pf.startswith("linux"):
        return _install_linux(name, argv, env, state_dir, home, run)
    if pf == "darwin":
        return _install_macos(name, argv, env, state_dir, home, run)
    raise ValueError(f"автозапуск не поддержан на платформе {pf}")
```

- [ ] **Step 4: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_autostart.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/autostart.py app/tests/env/test_autostart.py
git commit -m "feat(autostart): user-level автозапуск под Windows/Linux/macOS"
```

---

## Task 7: Оркестратор `code_index_local.deploy_local`

**Files:**
- Create: `app/src/agentmon/env/code_index_local.py`
- Test: `app/tests/env/test_code_index_local.py`

**Interfaces:**
- Consumes: `code_index_release.download_binary(code_index_dir, *, log=...) -> Path`; `autostart.install_and_start(name, argv, *, env, state_dir) -> list[str]`; `mcp_docker_recipes._daemon_toml(alias, path) -> str`.
- Produces: `deploy_local(*, mid, code_index_dir, catalog_dir, project_name, port, download=..., install=...) -> Iterator[str]` — генератор строк лога (каждая без завершающего `\n`).

- [ ] **Step 1: Тест оркестратора (инъекция download/install)**

Создать `app/tests/env/test_code_index_local.py`:

```python
from pathlib import Path
from agentmon.env import code_index_local as L


def test_deploy_local_writes_daemon_toml_and_autostarts(tmp_path):
    ci = tmp_path / "ci"; ci.mkdir()
    captured = {"installs": []}

    def fake_download(code_index_dir, *, log=None, **k):
        if log:
            log("скачал")
        return Path(code_index_dir) / "bsl-indexer"

    def fake_install(name, argv, *, env, state_dir):
        captured["installs"].append((name, tuple(argv), dict(env)))
        return [f"установлен {name}"]

    log = list(L.deploy_local(
        mid=7, code_index_dir=str(ci), catalog_dir="/code/cfg",
        project_name="proj", port=8005,
        download=fake_download, install=fake_install))

    text = "\n".join(log)
    # daemon.toml записан с alias=имя проекта и path=каталог кодовой базы
    daemon = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "proj"' in daemon
    assert 'path = "/code/cfg"' in daemon
    # два автозапуска: daemon run и serve
    names = [i[0] for i in captured["installs"]]
    assert names == ["ai1c-code-index-daemon-7", "ai1c-code-index-mcp-7"]
    daemon_i, serve_i = captured["installs"]
    assert daemon_i[1][-2:] == ("daemon", "run")
    assert daemon_i[2]["CODE_INDEX_HOME"] == str(ci)
    assert serve_i[1][-1] == "serve"
    assert serve_i[2]["MCP_HTTP_PORT"] == "8005"
    assert serve_i[2]["MCP_HTTP_HOST"] == "127.0.0.1"
    assert "proj" in text and "8005" in text
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_code_index_local.py -q`
Expected: FAIL (модуль отсутствует).

- [ ] **Step 3: Реализация**

Создать `app/src/agentmon/env/code_index_local.py`:

```python
"""Оркестратор локального (нативного) развёртывания code-index."""
from pathlib import Path

from .mcp_docker_recipes import _daemon_toml
from .code_index_release import download_binary as _download
from .autostart import install_and_start as _install


def deploy_local(*, mid, code_index_dir, catalog_dir, project_name, port,
                 download=_download, install=_install):
    """Генератор строк лога: скачать bsl-indexer, написать daemon.toml, поставить
    индексатор и MCP-сервер в автозапуск (и стартовать)."""
    yield (f"▶ Локальное развёртывание code-index: проект «{project_name}», "
           f"порт {port}")
    buf = []
    binary = download(code_index_dir, log=buf.append)
    for s in buf:
        yield s

    toml_path = Path(code_index_dir) / "daemon.toml"
    toml_path.write_text(_daemon_toml(project_name, catalog_dir),
                         encoding="utf-8")
    yield (f"✓ daemon.toml: {toml_path} (alias={project_name}, "
           f"path={catalog_dir})")

    home_env = {"CODE_INDEX_HOME": str(code_index_dir)}

    yield "=== Автозапуск: индексатор (daemon) ==="
    for s in install(f"ai1c-code-index-daemon-{mid}",
                     [str(binary), "daemon", "run"],
                     env=home_env, state_dir=code_index_dir):
        yield s

    yield "=== Автозапуск: MCP-сервер (serve) ==="
    serve_env = {**home_env, "MCP_HTTP_HOST": "127.0.0.1",
                 "MCP_HTTP_PORT": str(port)}
    for s in install(f"ai1c-code-index-mcp-{mid}", [str(binary), "serve"],
                     env=serve_env, state_dir=code_index_dir):
        yield s

    yield f"✓ Готово. MCP доступен на http://127.0.0.1:{port}/mcp"
```

- [ ] **Step 4: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_code_index_local.py -q`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/code_index_local.py app/tests/env/test_code_index_local.py
git commit -m "feat(code-index): оркестратор локального развёртывания"
```

---

## Task 8: API — эндпоинты `deploy-local` (блокирующий + стрим)

**Files:**
- Modify: `app/src/agentmon/env/mcp_api.py`
- Test: `app/tests/env/test_mcp_api.py`

**Interfaces:**
- Consumes: `code_index_local.deploy_local(*, mid, code_index_dir, catalog_dir, project_name, port) -> Iterator[str]`.
- Produces: `POST /api/mcp/{mid}/deploy-local` (JSON `{ok, log}`), `POST /api/mcp/{mid}/deploy-local/stream` (text/plain стрим).

- [ ] **Step 1: Тесты эндпоинтов (патч оркестратора)**

Добавить в `test_mcp_api.py`:

```python
def test_deploy_local_stream(tmp_path, monkeypatch):
    from agentmon.env import code_index_local
    monkeypatch.setattr(
        code_index_local, "deploy_local",
        lambda **kw: iter([f"строка про {kw['project_name']}", "готово"]))
    c = make(tmp_path)
    ci = tmp_path / "ci"; ci.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx-local", "kind": "local", "standard_key": "code-index-local",
        "port": 8005, "catalog_dir": "/code/cfg", "project_name": "proj",
        "code_index_dir": str(ci),
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/deploy-local/stream", json={})
    assert r.status_code == 200
    assert "строка про proj" in r.text and "готово" in r.text


def test_deploy_local_requires_code_index_dir(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "idx-local2", "kind": "local", "standard_key": "code-index-local",
        "port": 8005, "catalog_dir": "/code/cfg", "project_name": "proj",
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/deploy-local", json={})
    assert r.status_code == 400
```

- [ ] **Step 2: Прогнать — падает**

Run: `cd app && python -m pytest tests/env/test_mcp_api.py -k deploy_local -q`
Expected: FAIL (404/405 — маршрутов нет).

- [ ] **Step 3: Валидатор контекста локального вида**

В `mcp_api.py` добавить импорт рядом с существующими (`from . import mcp_docker` и т.п.):

```python
from . import code_index_local
```

После метода `_resolve_docker(...)` (перед эндпоинтами) добавить:

```python
    def _resolve_local(mid: int) -> dict:
        """Валидирует карточку локального code-index и собирает параметры."""
        repo = require_repo()
        row = repo.get(mid)
        if row is None:
            raise HTTPException(status_code=404, detail=f"нет MCP с id={mid}")
        if row.get("standard_key") != "code-index-local":
            raise HTTPException(status_code=400,
                                detail="это не локальный code-index")
        missing = [k for k in ("catalog_dir", "project_name",
                               "code_index_dir", "port") if not row.get(k)]
        if missing:
            raise HTTPException(status_code=400,
                                detail=f"не заданы поля: {', '.join(missing)}")
        return {
            "mid": mid,
            "code_index_dir": row["code_index_dir"],
            "catalog_dir": row["catalog_dir"],
            "project_name": row["project_name"],
            "port": int(row["port"]),
        }
```

- [ ] **Step 4: Эндпоинты**

После `launch_mcp_stream` (перед `stop_mcp`) добавить:

```python
    # ── локальное развёртывание (нативно, автозапуск) ─────────────────────────
    @router.post("/api/mcp/{mid}/deploy-local")
    def deploy_local_mcp(mid: int, body: dict):
        ctx = _resolve_local(mid)
        try:
            log = list(code_index_local.deploy_local(**ctx))
        except (ValueError, OSError) as exc:
            return {"ok": False, "log": str(exc)}
        return {"ok": True, "log": "\n".join(log)}

    @router.post("/api/mcp/{mid}/deploy-local/stream")
    def deploy_local_mcp_stream(mid: int, body: dict):
        ctx = _resolve_local(mid)

        def gen():
            try:
                for line in code_index_local.deploy_local(**ctx):
                    yield line + "\n"
            except (ValueError, OSError) as exc:
                yield f"\n✗ Ошибка: {exc}\n"

        return StreamingResponse(gen(), media_type="text/plain; charset=utf-8")
```

- [ ] **Step 5: Прогнать — проходит**

Run: `cd app && python -m pytest tests/env/test_mcp_api.py -q`
Expected: PASS.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_api.py app/tests/env/test_mcp_api.py
git commit -m "feat(mcp-api): эндпоинты deploy-local (блокирующий + стрим)"
```

---

## Task 9: Фронтенд — ветка `action="local"`

**Files:**
- Modify: `app/web/mcp.js`
- Test: ручная проверка (JS юнит-тестами не покрыт)

**Interfaces:**
- Consumes: `/api/mcp` (поле `code_index_dir`), `/api/mcp/{id}/deploy-local/stream`.

- [ ] **Step 1: Подпись поля**

В `FIELD_LABELS` после строки `project_name: ...` добавить:

```javascript
  code_index_dir: "Каталог code_index",
```

- [ ] **Step 2: Кнопка в форме**

В `renderTypeFields`, в блок `if (action) {` после ветки `t.action === "docker"` добавить ветку (перед `} else if (t.action === "cfe")`):

```javascript
    } else if (t.action === "local") {
      action.innerHTML =
        `<button type="button" onclick="deployLocalFromForm()">Развернуть локально</button>`;
```

- [ ] **Step 3: kind и сбор поля при создании**

В `createMcp`, в строке вычисления `kind` расширить тернарник:

```javascript
  const kind =
    t.action === "cfe" ? "extension"
      : t.action === "docker" ? "docker"
      : t.action === "local" ? "local"
      : "custom";
```

После строки сбора `catalog_dir` добавить:

```javascript
  if (t.fields.includes("code_index_dir")) body.code_index_dir = fieldVal("code_index_dir") || null;
```

- [ ] **Step 4: Функции развёртывания**

После `deployFromForm()` добавить:

```javascript
// Кнопка «Развернуть локально» в форме: сохранить элемент, затем развернуть нативно.
async function deployLocalFromForm() {
  const id = await createMcp();
  if (id == null) return;
  hideAddForm();
  await loadMcp();
  await streamDeployLocal(id);
}

// Стрим лога локального развёртывания в тот же вывод, что и docker-подъём.
async function streamDeployLocal(id) {
  await streamLaunch(id, {}, `/api/mcp/${id}/deploy-local/stream`);
}
```

- [ ] **Step 5: Параметризовать `streamLaunch` URL-ом**

Найти объявление `async function streamLaunch(id, body` и добавить третий аргумент с дефолтом на docker-URL. В теле заменить захардкоженный путь `/api/mcp/${id}/launch/stream` на параметр. Пример (подставить фактические имена из файла):

```javascript
async function streamLaunch(id, body = {}, url = `/api/mcp/${id}/launch/stream`) {
  // ... fetch(url, { method: "POST", ... })
}
```

Если `streamLaunch` отсутствует (логика инлайн в `launchMcp`) — вынести общий помощник `streamTo(url, body)` и вызвать его из `launchMcp` и `streamDeployLocal`.

- [ ] **Step 6: Кнопка в карточке**

В `showMcpCard`, рядом с `isDocker`, добавить `const isLocal = (type && type.action === "local") || mcp.kind === "local";` и ветку кнопки:

```javascript
  } else if (isLocal) {
    controlsHtml = `<button type="button" onclick="deployLocal('${mcp.id}')">Развернуть локально</button>`;
```

И показать поле в карточке — рядом со строкой `mcp.catalog_dir ? cardField(...)`:

```javascript
    mcp.code_index_dir ? cardField("Каталог code_index", mcp.code_index_dir) : "",
```

Добавить функцию карточки:

```javascript
async function deployLocal(id) {
  await streamDeployLocal(id);
}
```

- [ ] **Step 7: Проверка синтаксиса JS**

Run: `node --check app/web/mcp.js`
Expected: без ошибок.

- [ ] **Step 8: Коммит**

```bash
git add app/web/mcp.js
git commit -m "feat(mcp-ui): вид «локально» — поля и кнопка «Развернуть локально»"
```

---

## Task 10: Регрессия — полный прогон

**Files:**
- Test: весь `app/tests`

- [ ] **Step 1: Полный прогон**

Run: `cd app && python -m pytest -q`
Expected: все зелёные (ожидаемо ~1280+ passed).

- [ ] **Step 2: Коммит (если были мелкие правки)**

```bash
git add -A && git commit -m "test: регрессия вида code-index (локально)" || echo "нет изменений"
```

---

## Self-Review (выполнено при написании плана)

- **Покрытие спеки:** §Компоненты 1–8 → Task 1–9; обработка ошибок → Task 5/6/8 (ValueError, 400, best-effort linger); тестирование → тест-шаги в каждой задаче + Task 10. Переименование docker-вида → Task 3. UI → Task 9.
- **Плейсхолдеры:** код приведён в каждом шаге; в Task 9 Step 5 есть условная инструкция («если `streamLaunch` отсутствует») — это осознанная развилка под фактическое состояние `mcp.js`, не плейсхолдер, обе ветки конкретны.
- **Согласованность типов:** `_daemon_toml(alias, path)` (Task 1) ← используется в Task 7; `download_binary(..., log=...)->Path` (Task 5) ← Task 7; `install_and_start(name, argv, *, env, state_dir)->list[str]` (Task 6) ← Task 7; `deploy_local(*, mid, code_index_dir, catalog_dir, project_name, port)->Iterator[str]` (Task 7) ← Task 8. Имена `standard_key="code-index-local"`, колонка `code_index_dir`, задачи автозапуска `ai1c-code-index-{daemon,mcp}-<mid>` — едины во всех задачах.

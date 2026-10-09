# Ядро окружения + мастер установки — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать в Web-приложении возможность создать/обновить готовый к ИИ-разработке 1С-проект (layout на диске, конфиг-мастер, подключение MCP, выгрузка cf/cfe, регистрация в agentmon).

**Architecture:** Вендорим agentmon в репозиторий как базу (`app/`), добавляем пакет `agentmon.env` с чистыми, независимо тестируемыми модулями (схема конфига, каталог MCP, генерация файлов, scaffold, выгрузка платформы, оркестрация установки), подключаем FastAPI-роутер окружения в существующий `create_app`, добавляем web-страницу «Создать проект». Источник истины конфигурации — файл `ai1c.config.json` в каталоге проекта (Вариант A).

**Tech Stack:** Python 3.10+, FastAPI, uvicorn, pytest + FastAPI TestClient, stdlib `json`/`sqlite3`/`dataclasses`/`pathlib`/`subprocess`. Без новых зависимостей.

## Global Constraints

- Среды: **Linux и Windows**. Пути нормализуем как agentmon (слэши к одному виду, хвостовой слэш отбрасывается, буква диска — без учёта регистра). Нигде не хардкодить разделитель — только `pathlib`.
- **Своя реализация, deps как референс.** Код свой; `deps/` только читаем.
- **Рантайм:** окружение и платформа 1С — нативно на хосте; в Docker — только MCP-серверы.
- **Источник истины конфига — файл `ai1c.config.json` в проекте** (Вариант A). Реестр agentmon (SQLite) лишь ссылается на путь. Секреты в файл не пишем — только имя env-переменной.
- **Без новых зависимостей** сверх тех, что уже в `app/pyproject.toml` (fastapi, uvicorn, paramiko, pywinpty).
- Сообщения/комментарии — на русском, как в agentmon.
- `SCHEMA_VERSION = 1` для `ai1c.config.json`.
- Экран мастера называется **«Создать проект»**.
- Пять MCP: `1c-md`, `1c-syntax-checker-mcp`, `bsl-platform-context`, `1c-naparnic`, `code-index`.
- Пять субагентов: `analyst`, `architect`, `reviewer`, `developer`, `tester`.

---

## File Structure

Создаётся/меняется:

- `app/` — вендор agentmon (копия `deps/ai_env/agent-monitor`), далее наш код.
- `app/src/agentmon/env/__init__.py` — пакет окружения.
- `app/src/agentmon/env/config_schema.py` — dataclasses конфига, save/load.
- `app/src/agentmon/env/migration.py` — миграция схемы `ai1c.config.json`.
- `app/src/agentmon/env/mcp_catalog.py` — каталог MCP, генерация `.mcp.json` и compose.
- `app/src/agentmon/env/scaffold.py` — создание layout и запись файлов (merge/backup).
- `app/src/agentmon/env/platform_dump.py` — выгрузка cf/cfe через `1c-batch-py`.
- `app/src/agentmon/env/installer.py` — оркестрация install/update, события прогресса.
- `app/src/agentmon/env/api.py` — FastAPI-роутер окружения.
- `app/src/agentmon/api.py` — модификация: подключить роутер окружения.
- `app/web/create-project.html`, `app/web/create-project.js` — страница мастера.
- `app/web/index.html` — модификация: ссылка на «Создать проект».
- Тесты: `app/tests/env/test_*.py`.

---

## Task 0: Вендор agentmon в репозиторий

**Files:**
- Create: `app/` (копия `deps/ai_env/agent-monitor/`)

**Interfaces:**
- Produces: рабочее дерево `app/src/agentmon/...`, `app/web/`, `app/tests/`, `app/pyproject.toml` — база для всех последующих задач.

- [ ] **Step 1: Скопировать agentmon в `app/`**

```bash
mkdir -p app
cp -r deps/ai_env/agent-monitor/. app/
rm -rf app/agentmon.db app/.git
```

- [ ] **Step 2: Установить и прогнать базовые тесты**

Run:
```bash
cd app && pip install -e . && PYTHONPATH=src python -m pytest -q
```
Expected: все тесты agentmon проходят (базовая линия зелёная).

- [ ] **Step 3: Создать пакет окружения**

```bash
mkdir -p app/src/agentmon/env app/tests/env
touch app/src/agentmon/env/__init__.py app/tests/env/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git add app
git commit -m "chore: вендор agentmon как база приложения (app/)"
```

---

## Task 1: Схема конфига ai1c.config.json

**Files:**
- Create: `app/src/agentmon/env/config_schema.py`
- Test: `app/tests/env/test_config_schema.py`

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION: int = 1`
  - `@dataclass McpSelection(id: str, enabled: bool, mode: str, endpoint: str|None=None, secret_env: str|None=None)`
  - `@dataclass AgentModel(agent: str, model: str, effort: str)`
  - `@dataclass EnvConfig(schema_version:int, project_name:str, project_dir:str, developer_id:str, developer_email:str, platform_dir:str, platform_version:str, db_kind:str, db_connection:str, web_publication:str, mcp:list[McpSelection], agents:list[AgentModel])`
  - `EnvConfig.to_dict() -> dict`, `EnvConfig.from_dict(data: dict) -> EnvConfig`
  - `save_config(config: EnvConfig, project_dir) -> Path` (пишет `<project_dir>/ai1c.config.json`)
  - `load_config(project_dir) -> EnvConfig`

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_config_schema.py
from agentmon.env.config_schema import (
    EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION,
    save_config, load_config,
)


def sample_config():
    return EnvConfig(
        schema_version=SCHEMA_VERSION,
        project_name="demo", project_dir="/proj/demo",
        developer_id="ivanov", developer_email="i@e.ru",
        platform_dir="/opt/1cv8/8.3.27.1786", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/base/demo", web_publication="http://host/demo",
        mcp=[McpSelection(id="code-index", enabled=True, mode="managed",
                          endpoint=None, secret_env=None)],
        agents=[AgentModel(agent="developer", model="claude-opus-4-8", effort="high")],
    )


def test_roundtrip_dict():
    cfg = sample_config()
    assert EnvConfig.from_dict(cfg.to_dict()) == cfg


def test_save_and_load(tmp_path):
    cfg = sample_config()
    path = save_config(cfg, tmp_path)
    assert path == tmp_path / "ai1c.config.json"
    assert load_config(tmp_path) == cfg


def test_saved_json_has_schema_version(tmp_path):
    import json
    save_config(sample_config(), tmp_path)
    data = json.loads((tmp_path / "ai1c.config.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == SCHEMA_VERSION
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_config_schema.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.config_schema).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/config_schema.py
import json
from dataclasses import dataclass, asdict
from pathlib import Path

SCHEMA_VERSION = 1
CONFIG_FILENAME = "ai1c.config.json"


@dataclass
class McpSelection:
    id: str
    enabled: bool
    mode: str                       # "managed" | "external"
    endpoint: str | None = None     # external: url или команда
    secret_env: str | None = None   # managed: имя env-переменной с секретом


@dataclass
class AgentModel:
    agent: str
    model: str
    effort: str


@dataclass
class EnvConfig:
    schema_version: int
    project_name: str
    project_dir: str
    developer_id: str
    developer_email: str
    platform_dir: str
    platform_version: str
    db_kind: str                    # "server" | "file"
    db_connection: str
    web_publication: str
    mcp: list[McpSelection]
    agents: list[AgentModel]

    def to_dict(self) -> dict:
        data = asdict(self)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "EnvConfig":
        data = dict(data)
        data["mcp"] = [McpSelection(**m) for m in data.get("mcp", [])]
        data["agents"] = [AgentModel(**a) for a in data.get("agents", [])]
        return cls(**data)


def save_config(config: EnvConfig, project_dir) -> Path:
    path = Path(project_dir) / CONFIG_FILENAME
    path.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_config(project_dir) -> EnvConfig:
    path = Path(project_dir) / CONFIG_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    return EnvConfig.from_dict(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_config_schema.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/config_schema.py app/tests/env/test_config_schema.py
git commit -m "feat(env): схема и сохранение ai1c.config.json"
```

---

## Task 2: Миграция схемы конфига

**Files:**
- Create: `app/src/agentmon/env/migration.py`
- Modify: `app/src/agentmon/env/config_schema.py` (load_config вызывает migrate)
- Test: `app/tests/env/test_migration.py`

**Interfaces:**
- Consumes: `SCHEMA_VERSION` из `config_schema`.
- Produces: `migrate(data: dict) -> dict` — доводит словарь конфига до `SCHEMA_VERSION`, прогоняя зарегистрированные шаги по возрастанию версии; неизвестная (большая) версия — ошибка `ValueError`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_migration.py
import pytest
from agentmon.env.migration import migrate
from agentmon.env.config_schema import SCHEMA_VERSION


def test_adds_schema_version_when_absent():
    data = migrate({"project_name": "x"})
    assert data["schema_version"] == SCHEMA_VERSION


def test_already_current_is_unchanged():
    data = {"schema_version": SCHEMA_VERSION, "project_name": "x"}
    assert migrate(dict(data)) == data


def test_future_version_is_error():
    with pytest.raises(ValueError):
        migrate({"schema_version": SCHEMA_VERSION + 1})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_migration.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.migration).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/migration.py
from .config_schema import SCHEMA_VERSION


def _to_v1(data: dict) -> dict:
    # Версия 0 (конфиг без schema_version) → 1: просто проставляем версию.
    data["schema_version"] = 1
    return data


# Ключ — версия, С которой мигрируем; значение — функция до следующей версии.
_MIGRATIONS = {
    0: _to_v1,
}


def migrate(data: dict) -> dict:
    version = int(data.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"конфиг версии {version} новее поддерживаемой {SCHEMA_VERSION} — "
            "обновите приложение")
    while version < SCHEMA_VERSION:
        step = _MIGRATIONS.get(version)
        if step is None:
            raise ValueError(f"нет миграции с версии {version}")
        data = step(data)
        version = int(data["schema_version"])
    return data
```

- [ ] **Step 4: Подключить migrate в load_config**

В `app/src/agentmon/env/config_schema.py` заменить тело `load_config`:

```python
def load_config(project_dir) -> EnvConfig:
    path = Path(project_dir) / CONFIG_FILENAME
    data = json.loads(path.read_text(encoding="utf-8"))
    from .migration import migrate
    return EnvConfig.from_dict(migrate(data))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_migration.py tests/env/test_config_schema.py -q`
Expected: PASS (все).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/migration.py app/src/agentmon/env/config_schema.py app/tests/env/test_migration.py
git commit -m "feat(env): миграция схемы ai1c.config.json"
```

---

## Task 3: Каталог MCP и генерация .mcp.json / docker-compose.mcp.yml

**Files:**
- Create: `app/src/agentmon/env/mcp_catalog.py`
- Test: `app/tests/env/test_mcp_catalog.py`

**Interfaces:**
- Consumes: `McpSelection` из `config_schema`.
- Produces:
  - `@dataclass McpSpec(id:str, title:str, transport:str, default_port:int|None, image:str|None, needs_secret:bool)`
  - `CATALOG: dict[str, McpSpec]` — 5 серверов.
  - `build_mcp_json(selections: list[McpSelection], catalog=CATALOG) -> dict` — объект для `.mcp.json` (ключ `mcpServers`). managed+http → `{"url": "http://127.0.0.1:<port>"}`; managed+stdio → `{"command":"docker","args":["exec","-i","<id>","..."]}`; external → как задал пользователь (url, если начинается с http, иначе command).
  - `build_compose(selections, project_name, catalog=CATALOG) -> dict|None` — объект docker-compose только для managed; `None`, если managed-сервисов нет.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_mcp_catalog.py
from agentmon.env.config_schema import McpSelection
from agentmon.env.mcp_catalog import CATALOG, build_mcp_json, build_compose


def test_catalog_has_five_servers():
    assert set(CATALOG) == {
        "1c-md", "1c-syntax-checker-mcp", "bsl-platform-context",
        "1c-naparnic", "code-index",
    }


def test_disabled_server_is_skipped():
    sel = [McpSelection(id="code-index", enabled=False, mode="managed")]
    assert build_mcp_json(sel) == {"mcpServers": {}}


def test_managed_http_uses_localhost_url():
    sel = [McpSelection(id="code-index", enabled=True, mode="managed")]
    out = build_mcp_json(sel)["mcpServers"]["code-index"]
    port = CATALOG["code-index"].default_port
    assert out == {"url": f"http://127.0.0.1:{port}"}


def test_external_url_is_passed_through():
    sel = [McpSelection(id="1c-naparnic", enabled=True, mode="external",
                        endpoint="http://host:9000/sse")]
    out = build_mcp_json(sel)["mcpServers"]["1c-naparnic"]
    assert out == {"url": "http://host:9000/sse"}


def test_compose_only_for_managed():
    sel = [
        McpSelection(id="code-index", enabled=True, mode="managed"),
        McpSelection(id="1c-naparnic", enabled=True, mode="external",
                     endpoint="http://host:9000/sse"),
    ]
    compose = build_compose(sel, project_name="demo")
    assert "code-index" in compose["services"]
    assert "1c-naparnic" not in compose["services"]


def test_compose_none_when_no_managed():
    sel = [McpSelection(id="1c-naparnic", enabled=True, mode="external",
                        endpoint="http://host:9000/sse")]
    assert build_compose(sel, project_name="demo") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_mcp_catalog.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.mcp_catalog).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/mcp_catalog.py
from dataclasses import dataclass


@dataclass(frozen=True)
class McpSpec:
    id: str
    title: str
    transport: str          # "http" | "stdio"
    default_port: int | None
    image: str | None       # образ для managed; None для stdio-only
    needs_secret: bool


# Порты/образы — стартовые значения, уточняются при интеграции с docker_1c_sandbox.
CATALOG: dict[str, McpSpec] = {
    "1c-md": McpSpec("1c-md", "Запросы к метаданным", "http", 8811,
                     "ai1c/mcp-1c-md:latest", False),
    "1c-syntax-checker-mcp": McpSpec("1c-syntax-checker-mcp",
                     "Статический анализ BSL", "http", 8812,
                     "ai1c/mcp-bsl-syntax:latest", False),
    "bsl-platform-context": McpSpec("bsl-platform-context",
                     "Справка по платформе", "http", 8813,
                     "ai1c/mcp-bsl-context:latest", False),
    "1c-naparnic": McpSpec("1c-naparnic", "1С:Напарник", "http", 8814,
                     "ai1c/mcp-1c-naparnic:latest", True),
    "code-index": McpSpec("code-index", "Индекс кодовой базы", "http", 8815,
                     "ai1c/mcp-code-index:latest", False),
}


def _external_entry(endpoint: str) -> dict:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return {"url": endpoint}
    # команда вида "cmd arg1 arg2"
    parts = endpoint.split()
    return {"command": parts[0], "args": parts[1:]}


def build_mcp_json(selections, catalog=CATALOG) -> dict:
    servers: dict[str, dict] = {}
    for sel in selections:
        if not sel.enabled:
            continue
        spec = catalog[sel.id]
        if sel.mode == "external":
            servers[sel.id] = _external_entry(sel.endpoint or "")
        elif spec.transport == "http":
            servers[sel.id] = {"url": f"http://127.0.0.1:{spec.default_port}"}
        else:  # managed stdio
            servers[sel.id] = {"command": "docker",
                               "args": ["exec", "-i", sel.id]}
    return {"mcpServers": servers}


def build_compose(selections, project_name, catalog=CATALOG) -> dict | None:
    services: dict[str, dict] = {}
    for sel in selections:
        if not sel.enabled or sel.mode != "managed":
            continue
        spec = catalog[sel.id]
        service: dict = {"image": spec.image,
                         "container_name": f"{project_name}-{sel.id}",
                         "restart": "unless-stopped"}
        if spec.transport == "http" and spec.default_port:
            service["ports"] = [f"127.0.0.1:{spec.default_port}:{spec.default_port}"]
        if spec.needs_secret and sel.secret_env:
            service["environment"] = [f"{sel.secret_env}=${{{sel.secret_env}}}"]
        services[sel.id] = service
    if not services:
        return None
    return {"services": services}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_mcp_catalog.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/mcp_catalog.py app/tests/env/test_mcp_catalog.py
git commit -m "feat(env): каталог MCP и генерация .mcp.json/compose"
```

---

## Task 4: Scaffold layout и запись файлов (merge/backup при обновлении)

**Files:**
- Create: `app/src/agentmon/env/scaffold.py`
- Test: `app/tests/env/test_scaffold.py`

**Interfaces:**
- Consumes: `build_mcp_json`, `build_compose` из `mcp_catalog`; `EnvConfig` из `config_schema`.
- Produces:
  - `LAYOUT_DIRS: list[str]`
  - `scaffold_layout(project_dir) -> None` — создаёт дерево каталогов (идемпотентно).
  - `write_json(path, data) -> None` — стабильный JSON (`ensure_ascii=False, indent=2`, перевод строки в конце).
  - `write_preserving(path, content, *, update: bool) -> None` — при `update` и существующем файле делает бэкап `<name>.bak` перед заменой; при первом создании пишет как есть.
  - `write_env_files(config, *, update: bool) -> None` — пишет `.mcp.json`, `docker-compose.mcp.yml` (если есть managed) в `config.project_dir`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_scaffold.py
import json
from pathlib import Path
from agentmon.env.config_schema import EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION
from agentmon.env import scaffold


def cfg(tmp_path, mcp):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="http://h/demo",
        mcp=mcp, agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


def test_scaffold_creates_layout(tmp_path):
    scaffold.scaffold_layout(tmp_path)
    for rel in scaffold.LAYOUT_DIRS:
        assert (tmp_path / rel).is_dir()


def test_scaffold_is_idempotent(tmp_path):
    scaffold.scaffold_layout(tmp_path)
    scaffold.scaffold_layout(tmp_path)  # повторный вызов не падает
    assert (tmp_path / "src" / "cf").is_dir()


def test_write_env_files_writes_mcp_json(tmp_path):
    c = cfg(tmp_path, [McpSelection("code-index", True, "managed")])
    scaffold.write_env_files(c, update=False)
    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    assert "code-index" in data["mcpServers"]
    assert (tmp_path / "docker-compose.mcp.yml").exists()


def test_write_env_files_no_compose_when_no_managed(tmp_path):
    c = cfg(tmp_path, [McpSelection("1c-naparnic", True, "external",
                                    endpoint="http://h:9000/sse")])
    scaffold.write_env_files(c, update=False)
    assert not (tmp_path / "docker-compose.mcp.yml").exists()


def test_write_preserving_backs_up_on_update(tmp_path):
    p = tmp_path / "CLAUDE.md"
    scaffold.write_preserving(p, "первая\n", update=False)
    scaffold.write_preserving(p, "вторая\n", update=True)
    assert p.read_text(encoding="utf-8") == "вторая\n"
    assert (tmp_path / "CLAUDE.md.bak").read_text(encoding="utf-8") == "первая\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_scaffold.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.scaffold).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/scaffold.py
import json
from pathlib import Path

from .mcp_catalog import build_mcp_json, build_compose

LAYOUT_DIRS = [
    ".claude/agents", ".claude/skills", ".claude/hooks",
    "src/cf", "src/cfe", "tasks",
]


def scaffold_layout(project_dir) -> None:
    base = Path(project_dir)
    for rel in LAYOUT_DIRS:
        (base / rel).mkdir(parents=True, exist_ok=True)


def write_json(path, data) -> None:
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_preserving(path, content, *, update: bool) -> None:
    path = Path(path)
    if update and path.exists():
        backup = path.with_name(path.name + ".bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(content, encoding="utf-8")


def _to_compose_yaml(compose: dict) -> str:
    # Минимальный YAML-эмиттер для простой структуры compose (без зависимостей).
    lines = ["services:"]
    for name, svc in compose["services"].items():
        lines.append(f"  {name}:")
        for key, val in svc.items():
            if isinstance(val, list):
                lines.append(f"    {key}:")
                for item in val:
                    lines.append(f"      - {item}")
            else:
                lines.append(f"    {key}: {val}")
    return "\n".join(lines) + "\n"


def write_env_files(config, *, update: bool) -> None:
    base = Path(config.project_dir)
    write_json(base / ".mcp.json", build_mcp_json(config.mcp))
    compose = build_compose(config.mcp, config.project_name)
    compose_path = base / "docker-compose.mcp.yml"
    if compose is None:
        if update and compose_path.exists():
            compose_path.unlink()       # managed-серверов не осталось
        return
    write_preserving(compose_path, _to_compose_yaml(compose), update=update)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_scaffold.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/scaffold.py app/tests/env/test_scaffold.py
git commit -m "feat(env): scaffold layout и запись .mcp.json/compose c бэкапом"
```

---

## Task 5: Выгрузка cf/cfe через 1c-batch-py

**Files:**
- Create: `app/src/agentmon/env/platform_dump.py`
- Test: `app/tests/env/test_platform_dump.py`

**Interfaces:**
- Consumes: `EnvConfig` из `config_schema`.
- Produces:
  - `build_dump_command(config, kind: str) -> list[str]` — аргументы вызова `1c-batch-py` для `kind in {"cf","cfe"}`; `cf` → цель `src/cf`, `cfe` → `src/cfe`.
  - `dump(config, kind, *, run=subprocess.run) -> None` — вызывает команду; ненулевой код → `RuntimeError` с текстом stderr. `run` инъектируется в тестах.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_platform_dump.py
import pytest
from agentmon.env.config_schema import EnvConfig, AgentModel, SCHEMA_VERSION
from agentmon.env import platform_dump


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/base/demo", web_publication="",
        mcp=[], agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


class FakeRun:
    def __init__(self, returncode=0, stderr=""):
        self.calls = []
        self._rc, self._err = returncode, stderr

    def __call__(self, args, **kw):
        self.calls.append(args)
        class R:
            returncode = self._rc
            stderr = self._err
        return R()


def test_cf_command_targets_src_cf(tmp_path):
    args = platform_dump.build_dump_command(cfg(tmp_path), "cf")
    assert str(tmp_path / "src" / "cf") in args


def test_dump_calls_runner(tmp_path):
    fake = FakeRun()
    platform_dump.dump(cfg(tmp_path), "cf", run=fake)
    assert len(fake.calls) == 1


def test_dump_raises_on_nonzero(tmp_path):
    fake = FakeRun(returncode=1, stderr="платформа недоступна")
    with pytest.raises(RuntimeError, match="платформа недоступна"):
        platform_dump.dump(cfg(tmp_path), "cfe", run=fake)


def test_unknown_kind_is_error(tmp_path):
    with pytest.raises(ValueError):
        platform_dump.build_dump_command(cfg(tmp_path), "xml")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_platform_dump.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.platform_dump).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/platform_dump.py
import subprocess
import sys
from pathlib import Path

_TARGET = {"cf": ("src", "cf"), "cfe": ("src", "cfe")}


def build_dump_command(config, kind: str) -> list[str]:
    if kind not in _TARGET:
        raise ValueError(f"неизвестный вид выгрузки: {kind!r}")
    target = str(Path(config.project_dir).joinpath(*_TARGET[kind]))
    # Вызов пакетной операции 1c-batch-py; точные флаги уточняются при
    # интеграции, но форма «python -m onec_batch dump <kind> ...» стабильна.
    return [
        sys.executable, "-m", "onec_batch", "dump", kind,
        "--platform", config.platform_dir,
        "--db", config.db_connection,
        "--db-kind", config.db_kind,
        "--out", target,
    ]


def dump(config, kind: str, *, run=subprocess.run) -> None:
    cmd = build_dump_command(config, kind)
    result = run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr or f"выгрузка {kind} завершилась с ошибкой")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_platform_dump.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/platform_dump.py app/tests/env/test_platform_dump.py
git commit -m "feat(env): выгрузка cf/cfe через 1c-batch-py"
```

---

## Task 6: Оркестрация установки (installer) с событиями прогресса

**Files:**
- Create: `app/src/agentmon/env/installer.py`
- Test: `app/tests/env/test_installer.py`

**Interfaces:**
- Consumes: `EnvConfig`, `save_config` (config_schema); `scaffold_layout`, `write_env_files`, `write_preserving` (scaffold); `dump` (platform_dump).
- Produces:
  - `@dataclass ProgressEvent(step: str, status: str, detail: str = "")` (`status in {"start","ok","error"}`).
  - `install_environment(config, *, update: bool, register, dump_cf: bool, dump_cfe: bool, run=subprocess.run) -> Iterator[ProgressEvent]` — выполняет шаги по порядку (layout → config → claude/CLAUDE.md → env-файлы → [cf] → [cfe] → register) и отдаёт события. На ошибке шага отдаёт `error`-событие и прекращает. `register(config) -> None` инъектируется (в API — обёртка над `registry.add`).

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_installer.py
from agentmon.env.config_schema import EnvConfig, McpSelection, AgentModel, SCHEMA_VERSION, load_config
from agentmon.env import installer


def cfg(tmp_path):
    return EnvConfig(
        schema_version=SCHEMA_VERSION, project_name="demo",
        project_dir=str(tmp_path), developer_id="i", developer_email="i@e.ru",
        platform_dir="/opt/1cv8", platform_version="8.3.27.1786",
        db_kind="file", db_connection="/b", web_publication="",
        mcp=[McpSelection("code-index", True, "managed")],
        agents=[AgentModel("developer", "claude-opus-4-8", "high")],
    )


def ok_run(args, **kw):
    class R:
        returncode = 0
        stderr = ""
    return R()


def test_install_writes_config_and_registers(tmp_path):
    registered = []
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=registered.append,
        dump_cf=False, dump_cfe=False, run=ok_run))
    assert load_config(tmp_path).project_name == "demo"
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    assert len(registered) == 1
    assert events[-1].status == "ok"
    assert any(e.step == "register" and e.status == "ok" for e in events)


def test_install_runs_dumps_when_requested(tmp_path):
    calls = []
    def run(args, **kw):
        calls.append(args)
        return ok_run(args)
    list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=True, dump_cfe=True, run=run))
    assert len(calls) == 2            # cf и cfe


def test_install_stops_on_dump_error(tmp_path):
    def run(args, **kw):
        class R:
            returncode = 1
            stderr = "нет платформы"
        return R()
    events = list(installer.install_environment(
        cfg(tmp_path), update=False, register=lambda c: None,
        dump_cf=True, dump_cfe=False, run=run))
    assert events[-1].status == "error"
    assert "нет платформы" in events[-1].detail
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_installer.py -q`
Expected: FAIL (ModuleNotFoundError: agentmon.env.installer).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/installer.py
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from .config_schema import EnvConfig, save_config
from .scaffold import scaffold_layout, write_env_files, write_preserving
from .platform_dump import dump


@dataclass
class ProgressEvent:
    step: str
    status: str                 # "start" | "ok" | "error"
    detail: str = ""


def _claude_md(config: EnvConfig) -> str:
    return (
        f"# {config.project_name}\n\n"
        f"Разработчик: {config.developer_id} <{config.developer_email}>\n"
        f"Платформа: {config.platform_version}\n"
    )


def install_environment(
    config: EnvConfig, *, update: bool,
    register: Callable[[EnvConfig], None],
    dump_cf: bool, dump_cfe: bool,
    run=subprocess.run,
) -> Iterator[ProgressEvent]:
    base = Path(config.project_dir)

    def step(name, fn):
        yield ProgressEvent(name, "start")
        try:
            fn()
        except Exception as exc:                       # noqa: BLE001
            yield ProgressEvent(name, "error", str(exc))
            raise
        yield ProgressEvent(name, "ok")

    steps = [
        ("layout", lambda: scaffold_layout(base)),
        ("config", lambda: save_config(config, base)),
        ("claude", lambda: write_preserving(base / "CLAUDE.md",
                                            _claude_md(config), update=update)),
        ("mcp", lambda: write_env_files(config, update=update)),
    ]
    if dump_cf:
        steps.append(("dump-cf", lambda: dump(config, "cf", run=run)))
    if dump_cfe:
        steps.append(("dump-cfe", lambda: dump(config, "cfe", run=run)))
    steps.append(("register", lambda: register(config)))

    try:
        for name, fn in steps:
            yield from step(name, fn)
    except Exception:
        return                      # error-событие уже отдано шагом
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src python -m pytest tests/env/test_installer.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/installer.py app/tests/env/test_installer.py
git commit -m "feat(env): оркестрация установки окружения с прогрессом"
```

---

## Task 7: API-роутер окружения

**Files:**
- Create: `app/src/agentmon/env/api.py`
- Modify: `app/src/agentmon/api.py` (подключить роутер)
- Test: `app/tests/env/test_env_api.py`

**Interfaces:**
- Consumes: `EnvConfig.from_dict` (config_schema); `install_environment`, `ProgressEvent` (installer); `registry` (из create_app).
- Produces:
  - `build_env_router(registry) -> APIRouter` с маршрутами:
    - `POST /api/environment/create` — тело: `{config: <dict ai1c>, update: bool, dump_cf: bool, dump_cfe: bool}`. Выполняет установку синхронно, возвращает `{"events": [ {step,status,detail}, ... ], "ok": bool}`. Регистрация в agentmon — `registry.add(name=project_name, path=project_dir, backend="local")` (идемпотентно: если путь уже есть — пропустить).
- Modify `create_app`: `app.include_router(build_env_router(registry))`.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_env_api.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends    # noqa: E402


def make_client(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    mon = Monitor(reg, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    return TestClient(create_app(registry=reg, queue=q, monitor=mon)), reg


def payload(project_dir):
    return {
        "config": {
            "schema_version": 1, "project_name": "demo",
            "project_dir": str(project_dir), "developer_id": "i",
            "developer_email": "i@e.ru", "platform_dir": "/opt/1cv8",
            "platform_version": "8.3.27.1786", "db_kind": "file",
            "db_connection": "/b", "web_publication": "",
            "mcp": [{"id": "1c-naparnic", "enabled": True, "mode": "external",
                     "endpoint": "http://h:9000/sse", "secret_env": None}],
            "agents": [{"agent": "developer", "model": "claude-opus-4-8",
                        "effort": "high"}],
        },
        "update": False, "dump_cf": False, "dump_cfe": False,
    }


def test_create_environment_registers_project(tmp_path):
    client, reg = make_client(tmp_path)
    proj_dir = tmp_path / "demo"
    proj_dir.mkdir()
    r = client.post("/api/environment/create", json=payload(proj_dir))
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert (proj_dir / "ai1c.config.json").exists()
    assert [p.path for p in reg.list()] == [str(proj_dir)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src:tests python -m pytest tests/env/test_env_api.py -q`
Expected: FAIL (ImportError build_env_router / 404 на маршруте).

- [ ] **Step 3: Write minimal implementation**

```python
# app/src/agentmon/env/api.py
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from .config_schema import EnvConfig
from .installer import install_environment


def build_env_router(registry) -> APIRouter:
    router = APIRouter()

    def register(config: EnvConfig) -> None:
        for p in registry.list():
            if p.path == config.project_dir:
                return                  # уже зарегистрирован — идемпотентно
        registry.add(name=config.project_name, path=config.project_dir,
                     backend="local", conn=None, claude_cmd=None)

    @router.post("/api/environment/create")
    def create_environment(body: dict):
        try:
            config = EnvConfig.from_dict(body["config"])
        except (KeyError, TypeError) as exc:
            raise HTTPException(status_code=400, detail=f"плохой config: {exc}")
        events = list(install_environment(
            config,
            update=bool(body.get("update")),
            register=register,
            dump_cf=bool(body.get("dump_cf")),
            dump_cfe=bool(body.get("dump_cfe")),
        ))
        ok = bool(events) and events[-1].status == "ok"
        return {"ok": ok, "events": [asdict(e) for e in events]}

    return router
```

- [ ] **Step 4: Подключить роутер в create_app**

В `app/src/agentmon/api.py`, сразу после строки `app = FastAPI(lifespan=lifespan)`, добавить:

```python
    from .env.api import build_env_router
    app.include_router(build_env_router(registry))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src:tests python -m pytest tests/env/test_env_api.py -q`
Expected: PASS (1 passed).

- [ ] **Step 6: Прогнать весь набор тестов**

Run: `cd app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все, включая базовые agentmon).

- [ ] **Step 7: Commit**

```bash
git add app/src/agentmon/env/api.py app/src/agentmon/api.py app/tests/env/test_env_api.py
git commit -m "feat(env): API-роутер создания окружения"
```

---

## Task 8: Web-страница «Создать проект»

**Files:**
- Create: `app/web/create-project.html`
- Create: `app/web/create-project.js`
- Modify: `app/web/index.html` (ссылка на страницу)
- Modify: `app/src/agentmon/api.py` (отдавать `/create-project`)
- Test: `app/tests/env/test_create_project_page.py`

**Interfaces:**
- Consumes: `POST /api/environment/create`.
- Produces: статическая страница с формой (секции: Режим, Проект, Разработчик, Платформа, База, MCP (5 строк: enabled/mode/endpoint), Модели агентов (5 строк), Действия), которая собирает `config` и шлёт на API, показывает список событий ответа.

- [ ] **Step 1: Write the failing test**

```python
# app/tests/env/test_create_project_page.py
from fastapi.testclient import TestClient
from agentmon.api import create_app
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends    # noqa: E402


def test_create_project_page_served(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    mon = Monitor(ProjectRegistry(db), FakeBackends(None),
                  generating_window=10.0, now_fn=lambda: 1.0)
    client = TestClient(create_app(registry=ProjectRegistry(db),
                                   queue=TaskQueue(db), monitor=mon))
    r = client.get("/create-project")
    assert r.status_code == 200
    assert "Создать проект" in r.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && PYTHONPATH=src:tests python -m pytest tests/env/test_create_project_page.py -q`
Expected: FAIL (404 на /create-project).

- [ ] **Step 3: Создать страницу**

```html
<!-- app/web/create-project.html -->
<!doctype html>
<html lang="ru">
<head><meta charset="utf-8"><title>Создать проект</title></head>
<body>
  <h1>Создать проект</h1>
  <form id="f">
    <fieldset><legend>Режим</legend>
      <label><input type="checkbox" name="update"> обновить существующий</label>
    </fieldset>
    <fieldset><legend>Проект</legend>
      <input name="project_name" placeholder="имя">
      <input name="project_dir" placeholder="каталог">
    </fieldset>
    <fieldset><legend>Разработчик</legend>
      <input name="developer_id" placeholder="идентификатор">
      <input name="developer_email" placeholder="email">
    </fieldset>
    <fieldset><legend>Платформа</legend>
      <input name="platform_dir" placeholder="каталог платформы">
      <input name="platform_version" placeholder="версия">
    </fieldset>
    <fieldset><legend>База</legend>
      <select name="db_kind"><option value="file">файловая</option>
        <option value="server">серверная</option></select>
      <input name="db_connection" placeholder="строка подключения">
      <input name="web_publication" placeholder="веб-публикация">
    </fieldset>
    <fieldset><legend>MCP</legend><div id="mcp"></div></fieldset>
    <fieldset><legend>Модели агентов</legend><div id="agents"></div></fieldset>
    <fieldset><legend>Действия</legend>
      <label><input type="checkbox" name="dump_cf"> выгрузить cf</label>
      <label><input type="checkbox" name="dump_cfe"> выгрузить cfe</label>
    </fieldset>
    <button type="submit">Создать</button>
  </form>
  <pre id="out"></pre>
  <script src="/static/create-project.js"></script>
</body>
</html>
```

```javascript
// app/web/create-project.js
const MCP = ["1c-md","1c-syntax-checker-mcp","bsl-platform-context","1c-naparnic","code-index"];
const AGENTS = ["analyst","architect","reviewer","developer","tester"];

const mcpBox = document.getElementById("mcp");
MCP.forEach(id => {
  mcpBox.insertAdjacentHTML("beforeend",
    `<div data-mcp="${id}"><label><input type="checkbox" class="en" checked> ${id}</label>
     <select class="mode"><option value="managed">managed</option><option value="external">external</option></select>
     <input class="ep" placeholder="endpoint (для external)"></div>`);
});

const agBox = document.getElementById("agents");
AGENTS.forEach(a => {
  agBox.insertAdjacentHTML("beforeend",
    `<div data-agent="${a}">${a}
     <input class="model" value="claude-opus-4-8">
     <select class="effort"><option>high</option><option>medium</option><option>low</option></select></div>`);
});

document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.target;
  const mcp = [...mcpBox.querySelectorAll("[data-mcp]")].map(d => ({
    id: d.dataset.mcp, enabled: d.querySelector(".en").checked,
    mode: d.querySelector(".mode").value, endpoint: d.querySelector(".ep").value || null,
    secret_env: null,
  }));
  const agents = [...agBox.querySelectorAll("[data-agent]")].map(d => ({
    agent: d.dataset.agent, model: d.querySelector(".model").value,
    effort: d.querySelector(".effort").value,
  }));
  const config = {
    schema_version: 1,
    project_name: f.project_name.value, project_dir: f.project_dir.value,
    developer_id: f.developer_id.value, developer_email: f.developer_email.value,
    platform_dir: f.platform_dir.value, platform_version: f.platform_version.value,
    db_kind: f.db_kind.value, db_connection: f.db_connection.value,
    web_publication: f.web_publication.value, mcp, agents,
  };
  const body = { config, update: f.update.checked,
                 dump_cf: f.dump_cf.checked, dump_cfe: f.dump_cfe.checked };
  const r = await fetch("/api/environment/create",
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
  const data = await r.json();
  document.getElementById("out").textContent =
    (data.ok ? "OK\n" : "ОШИБКА\n") +
    data.events.map(ev => `${ev.step}: ${ev.status} ${ev.detail}`).join("\n");
});
```

- [ ] **Step 4: Отдавать страницу роутом**

В `app/src/agentmon/api.py`, в блоке `if web_dir.exists():` (рядом с `index`) добавить:

```python
        @app.get("/create-project")
        def create_project_page():
            return FileResponse(web_dir / "create-project.html",
                                headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 5: Ссылка на странице index**

В `app/web/index.html` добавить в видимую часть ссылку:

```html
<a href="/create-project">Создать проект</a>
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd app && PYTHONPATH=src:tests python -m pytest tests/env/test_create_project_page.py -q`
Expected: PASS (1 passed).

- [ ] **Step 7: Прогнать весь набор тестов**

Run: `cd app && PYTHONPATH=src:tests python -m pytest -q`
Expected: PASS (все).

- [ ] **Step 8: Commit**

```bash
git add app/web/create-project.html app/web/create-project.js app/web/index.html app/src/agentmon/api.py app/tests/env/test_create_project_page.py
git commit -m "feat(env): web-страница «Создать проект»"
```

---

## Self-Review

**Spec coverage:**
- Layout окружения → Task 4 (scaffold) + Task 6 (CLAUDE.md, config).
- Источник истины = файл (Вариант A) → Task 1 (save/load в каталоге проекта), регистрация ссылается на путь (Task 7).
- Секреты не в файле → `McpSelection.secret_env` хранит имя переменной (Task 1/3), в compose подставляется `${ENV}` (Task 3).
- MCP managed/external → Task 3 (build_mcp_json/build_compose), Task 4 (запись).
- Мастер «Создать проект», 8 секций → Task 8.
- Выгрузка cf/cfe → Task 5, включение в поток → Task 6, галки → Task 8.
- Режим обновления (merge/backup, миграция) → Task 2 (миграция), Task 4 (`write_preserving` бэкап), Task 6 (`update` проброшен).
- Прогресс стримом → `ProgressEvent` (Task 6), возвращается списком в API (Task 7). Примечание: в этом плане прогресс отдаётся одним ответом (список событий); живой SSE-стрим — улучшение, выносится в отдельную задачу, т.к. не блокирует работоспособность.
- Регистрация в agentmon → Task 7.
- Тесты по спеку (генерация файлов, idempotent-обновление, миграция, пути) → Task 1-7.

**Placeholder scan:** код во всех шагах полный; явных TODO в коде нет. Точные флаги `1c-batch-py` помечены как уточняемые при интеграции, но форма команды и её тестирование (через инъекцию `run`) определены.

**Type consistency:** `EnvConfig`/`McpSelection`/`AgentModel` — единые имена полей во всех задачах; `build_mcp_json`/`build_compose`/`write_env_files`/`install_environment`/`ProgressEvent`/`build_env_router` согласованы между задачами и тестами.

**Отложенные улучшения (вне этого плана, не ломают работоспособность):** живой SSE-стрим прогресса; скан версий платформы (автоподстановка в форме); health-check managed-MCP и `docker compose up` из UI; раскладка реального контента `.claude/*` (подсистема №2).

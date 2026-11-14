# Benchmark Environment Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Одна команда создаёт готовый к прогону benchmark-проект AgentMon из `benchmark/test.env`: окружение, база 1С, выгрузки, задачи, MCP и code_index.

**Architecture:** Оркестрация — новый модуль `app/src/agentmon/env/bench_setup.py`, переиспользующий `install_environment`, `devbase`, `store`, `registry`, `mcp_docker_recipes`. Тонкий CLI `benchmark/setup_benchmark.py` читает `.ai1c.env` и `test.env` и вызывает `run_setup`.

**Tech Stack:** Python 3.10+, pytest, существующие модули `agentmon.env`/`agentmon.store`/`agentmon.registry`, 1c-batch, Docker.

## Global Constraints

- Python ≥ 3.10; не добавлять внешних зависимостей.
- Весь пользовательский текст (логи, ошибки, комментарии) — на русском, как в репозитории.
- Коммиты — только локально в `main`, без `push`. Каждый коммит с трейлером `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- В рабочем дереве есть посторонние изменения: `benchmark/tasks/task##002/TASK.md`, `template/.bsl-language-server.json`, удаления `benchmark/tasks/task##003`/`task##004`. Их **не трогать и не коммитить**. `git add` — только файлы, перечисленные в задаче.
- `test2`, `benchmark/cf`, `benchmark/tasks/*` не изменять (задачи только копируются при выполнении скрипта).
- Секреты (`test.env`, пароль 1С) не печатать в лог и не коммитить. `benchmark/test.env` — в `.gitignore`.
- Тесты запускать из `app`: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`.
- После каждой задачи все тесты файла должны проходить.

## File Structure

| Путь | Ответственность |
|---|---|
| `benchmark/example.test.env` | Образец конфигурации без секретов |
| `benchmark/setup_benchmark.py` | CLI: парсинг аргументов, `.ai1c.env`, подключение store/registry, вызов `run_setup` |
| `app/src/agentmon/env/bench_setup.py` | Парсинг env, preflight, MCP-карточки, команды 1С, импорт задач, code_index, откат |
| `app/tests/env/test_bench_setup.py` | Юнит-тесты с реальным SQLite-store и фейками 1С/Docker |
| `.gitignore` | `/benchmark/test.env` |
| `benchmark/README.md` | Инструкция запуска |

---

### Task 1: test.env, парсинг и BenchConfig

**Files:**
- Create: `app/src/agentmon/env/bench_setup.py`
- Create: `app/tests/env/test_bench_setup.py`
- Create: `benchmark/example.test.env`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `agentmon.env.project_checks.infer_db_kind`.
- Produces: `SetupError`, `BenchConfig`, `parse_env_file(path) -> dict[str,str]`, `load_config(env_path, *, repo_root, warn=print) -> BenchConfig`.

- [ ] **Step 1: Write the failing tests**

Create `app/tests/env/test_bench_setup.py`:

```python
"""Тесты подготовки benchmark-окружения (без 1С, Docker и PostgreSQL)."""
from pathlib import Path

import pytest

from agentmon.env.bench_setup import BenchConfig, SetupError, load_config, parse_env_file


def make_platform(tmp_path: Path) -> Path:
    """Фейковый бинарник платформы в каталоге с версией в пути."""
    platform = tmp_path / "8.3.27.2130"
    platform.mkdir(exist_ok=True)
    binary = platform / "1cv8"
    binary.write_text("", encoding="utf-8")
    return binary


def write_env(tmp_path: Path, **overrides: str) -> Path:
    binary = make_platform(tmp_path) if not (tmp_path / "8.3.27.2130" / "1cv8").exists() else (
        tmp_path / "8.3.27.2130" / "1cv8")
    values = {
        "BENCH_PROJECT_NAME": "bench",
        "BENCH_PROJECT_DIR": str(tmp_path / "project"),
        "BENCH_DEVELOPER_ID": "alex",
        "BENCH_DEVELOPER_EMAIL": "alex@example.ru",
        "BENCH_PLATFORM_PATH": str(binary),
        "BENCH_DB_CONNECTION": "Srvr=localhost;Ref=bench",
        "BENCH_DB_USER": "Администратор",
        "BENCH_DB_PASSWORD": "",
        "MCP_BSL_LS_URL": "http://localhost:8001/mcp",
        "MCP_1C_PLATFORM_URL": "http://localhost:8002/sse",
        "MCP_CODE_INDEX_PORT": "8004",
    }
    values.update(overrides)
    path = tmp_path / "test.env"
    path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )
    return path


def test_parse_env_file_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "test.env"
    path.write_text("# comment\n\nA=1\nB=two=2\n", encoding="utf-8")
    assert parse_env_file(path) == {"A": "1", "B": "two=2"}


def test_load_config_required_optional_and_defaults(tmp_path):
    env = write_env(tmp_path)
    cfg = load_config(env, repo_root=tmp_path)
    assert isinstance(cfg, BenchConfig)
    assert cfg.project_name == "bench"
    assert cfg.project_dir == str((tmp_path / "project").resolve())
    assert cfg.platform_version == "8.3.27.2130"
    assert cfg.db_kind == "server"
    assert cfg.db_connection == "Srvr=localhost;Ref=bench"
    assert cfg.code_index_port == 8004
    assert cfg.code_index_host == "localhost"
    assert cfg.code_index_wait_minutes == 360
    assert cfg.one_c_md_url is None
    assert cfg.dt_path is None


def test_load_config_allows_empty_password(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    assert cfg.db_password == ""


def test_load_config_missing_required_key(tmp_path):
    env = write_env(tmp_path)
    env.write_text(
        env.read_text(encoding="utf-8").replace("BENCH_DB_USER=Администратор\n", ""),
        encoding="utf-8",
    )
    with pytest.raises(SetupError, match="BENCH_DB_USER"):
        load_config(env, repo_root=tmp_path)


def test_load_config_rejects_relative_project_dir(tmp_path):
    with pytest.raises(SetupError, match="абсолют"):
        load_config(write_env(tmp_path, BENCH_PROJECT_DIR="relative"), repo_root=tmp_path)


def test_load_config_warns_unknown_key(tmp_path):
    warnings = []
    load_config(
        write_env(tmp_path, UNKNOWN_KEY="x"),
        repo_root=tmp_path,
        warn=warnings.append,
    )
    assert any("UNKNOWN_KEY" in warning for warning in warnings)


def test_load_config_dt_path_is_relative_to_repo(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="benchmark/base.dt"),
        repo_root=tmp_path,
    )
    assert cfg.dt_path == str((tmp_path / "benchmark" / "base.dt").resolve())


def test_load_config_optional_1c_md_and_code_index_overrides(tmp_path):
    cfg = load_config(
        write_env(
            tmp_path,
            MCP_1C_MD_URL="http://localhost/t_bench/hs/mcp",
            MCP_CODE_INDEX_HOST="127.0.0.1",
            MCP_CODE_INDEX_PORT="8104",
            CODE_INDEX_WAIT_MINUTES="120",
        ),
        repo_root=tmp_path,
    )
    assert cfg.one_c_md_url == "http://localhost/t_bench/hs/mcp"
    assert cfg.code_index_host == "127.0.0.1"
    assert cfg.code_index_port == 8104
    assert cfg.code_index_wait_minutes == 120
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentmon.env.bench_setup'`.

- [ ] **Step 3: Create the module**

Create `app/src/agentmon/env/bench_setup.py`:

```python
"""Подготовка benchmark-окружения: test.env → готовый проект AgentMon.

Секреты (test.env, .1c-devbase.json) не попадают в git. Модуль не читает
agentmon.config на уровне импорта: DSN и путь реестра передаёт CLI после
загрузки .ai1c.env.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .project_checks import infer_db_kind

REQUIRED_KEYS = (
    "BENCH_PROJECT_NAME", "BENCH_PROJECT_DIR", "BENCH_DEVELOPER_ID",
    "BENCH_DEVELOPER_EMAIL", "BENCH_PLATFORM_PATH", "BENCH_DB_CONNECTION",
    "BENCH_DB_USER", "BENCH_DB_PASSWORD", "MCP_BSL_LS_URL",
    "MCP_1C_PLATFORM_URL", "MCP_CODE_INDEX_PORT",
)
OPTIONAL_KEYS = (
    "MCP_1C_MD_URL", "BENCH_DT_PATH", "MCP_CODE_INDEX_HOST",
    "CODE_INDEX_WAIT_MINUTES",
)
_VERSION_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class SetupError(RuntimeError):
    """Ошибка подготовки benchmark-окружения (сообщение — для пользователя)."""


@dataclass(frozen=True)
class BenchConfig:
    project_name: str
    project_dir: str
    developer_id: str
    developer_email: str
    platform_path: str          # бинарник 1cv8
    platform_version: str
    db_kind: str                # "server" | "file"
    db_connection: str
    db_user: str
    db_password: str
    bsl_ls_url: str
    platform_url: str
    code_index_port: int
    code_index_host: str
    code_index_wait_minutes: int
    one_c_md_url: str | None
    dt_path: str | None


def parse_env_file(path: Path) -> dict[str, str]:
    """Прочитать KEY=value; комментарии и пустые строки игнорируются."""
    data: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if not sep:
            raise SetupError(f"{path}: строка не в формате KEY=value: {raw!r}")
        data[key.strip()] = value.strip()
    return data


def _resolve_platform(raw: Path) -> Path:
    """Каталог платформы → бинарник 1cv8; сам файл возвращается как есть."""
    if raw.is_file():
        return raw
    for rel in ("1cv8", "bin/1cv8", "1cv8.exe", "bin/1cv8.exe"):
        candidate = raw / rel
        if candidate.is_file():
            return candidate
    raise SetupError(
        f"не найден бинарник 1cv8: {raw} "
        "(укажите каталог платформы или сам файл)")


def load_config(env_path: Path, *, repo_root: Path,
                warn: Callable[[str], None] = print) -> BenchConfig:
    """Разобрать test.env и проверить значения, не трогая БД и файловую систему проекта."""
    if not env_path.is_file():
        raise SetupError(f"не найден файл конфигурации: {env_path}")
    data = parse_env_file(env_path)

    missing = [key for key in REQUIRED_KEYS if key not in data]
    empty = [key for key in REQUIRED_KEYS
             if key != "BENCH_DB_PASSWORD" and not data.get(key, "").strip()]
    if missing or empty:
        raise SetupError(
            "не заданы обязательные ключи: " + ", ".join(missing + empty))

    unknown = sorted(set(data) - set(REQUIRED_KEYS) - set(OPTIONAL_KEYS))
    if unknown:
        warn(f"⚠ неизвестные ключи test.env игнорируются: {', '.join(unknown)}")

    for key in ("MCP_BSL_LS_URL", "MCP_1C_PLATFORM_URL", "MCP_1C_MD_URL"):
        value = data.get(key, "")
        if value and not _URL_RE.match(value):
            raise SetupError(f"{key} должен начинаться с http:// или https://")

    try:
        port = int(data["MCP_CODE_INDEX_PORT"])
    except ValueError:
        raise SetupError("MCP_CODE_INDEX_PORT должен быть целым числом") from None
    if not 1 <= port <= 65535:
        raise SetupError("MCP_CODE_INDEX_PORT должен быть в диапазоне 1..65535")

    try:
        wait_minutes = int(data.get("CODE_INDEX_WAIT_MINUTES") or "360")
    except ValueError:
        raise SetupError("CODE_INDEX_WAIT_MINUTES должен быть целым числом") from None
    if wait_minutes < 1:
        raise SetupError("CODE_INDEX_WAIT_MINUTES должен быть положительным")

    project_dir = Path(os.path.expanduser(data["BENCH_PROJECT_DIR"].strip()))
    if not project_dir.is_absolute():
        raise SetupError("BENCH_PROJECT_DIR должен быть абсолютным путём")

    platform_raw = Path(os.path.expanduser(data["BENCH_PLATFORM_PATH"].strip()))
    platform = _resolve_platform(platform_raw)
    version = _VERSION_RE.search(str(platform))
    if not version:
        raise SetupError(
            f"не удалось определить версию платформы из пути: {platform}")

    dt_path = None
    dt_raw = (data.get("BENCH_DT_PATH") or "").strip()
    if dt_raw:
        dt = Path(os.path.expanduser(dt_raw))
        if not dt.is_absolute():
            dt = repo_root / dt
        dt_path = str(dt.resolve())

    db_connection = data["BENCH_DB_CONNECTION"].strip()
    return BenchConfig(
        project_name=data["BENCH_PROJECT_NAME"].strip(),
        project_dir=str(project_dir.resolve()),
        developer_id=data["BENCH_DEVELOPER_ID"].strip(),
        developer_email=data["BENCH_DEVELOPER_EMAIL"].strip(),
        platform_path=str(platform),
        platform_version=version.group(1),
        db_kind=infer_db_kind(db_connection),
        db_connection=db_connection,
        db_user=data["BENCH_DB_USER"].strip(),
        db_password=data.get("BENCH_DB_PASSWORD", ""),
        bsl_ls_url=data["MCP_BSL_LS_URL"].strip(),
        platform_url=data["MCP_1C_PLATFORM_URL"].strip(),
        code_index_port=port,
        code_index_host=(data.get("MCP_CODE_INDEX_HOST") or "localhost").strip(),
        code_index_wait_minutes=wait_minutes,
        one_c_md_url=(data.get("MCP_1C_MD_URL") or "").strip() or None,
        dt_path=dt_path,
    )
```

- [ ] **Step 4: Add example config and gitignore rule**

Create `benchmark/example.test.env`:

```dotenv
# Пример конфигурации benchmark-окружения.
# Скопируйте в benchmark/test.env и заполните своими значениями:
#
#     cp benchmark/example.test.env benchmark/test.env
#
# Реальный test.env не коммитится (см. .gitignore) и содержит пароль 1С.

# ─── Проект ───────────────────────────────────────────────────────────────────
BENCH_PROJECT_NAME=bench
BENCH_PROJECT_DIR=/home/uam/projects/bench
BENCH_DEVELOPER_ID=alex
BENCH_DEVELOPER_EMAIL=alex@example.ru

# ─── Платформа и база 1С ──────────────────────────────────────────────────────
# Каталог платформы или сам бинарник 1cv8.
BENCH_PLATFORM_PATH=/opt/1cv8/x86_64/8.3.27.2130/1cv8
# Серверная: Srvr=host;Ref=base. Файловая: путь к каталогу ИБ.
BENCH_DB_CONNECTION=Srvr=localhost;Ref=bench
BENCH_DB_USER=Администратор
BENCH_DB_PASSWORD=

# ─── MCP ──────────────────────────────────────────────────────────────────────
# Общие серверы (обязательны).
MCP_BSL_LS_URL=http://localhost:8001/mcp
MCP_1C_PLATFORM_URL=http://localhost:8002/sse
# Порт контейнера code_index (обязателен); хост по умолчанию localhost.
MCP_CODE_INDEX_PORT=8004
#MCP_CODE_INDEX_HOST=localhost
# Таймаут ожидания полной индексации, минуты (по умолчанию 360).
#CODE_INDEX_WAIT_MINUTES=360

# ─── Опционально ──────────────────────────────────────────────────────────────
# URL http-сервиса 1c-md в базе; если не задан — MCP-сервер не подключается.
#MCP_1C_MD_URL=http://localhost/bench/hs/mcp
# Локальный путь к .dt. Если задан — benchmark/cf и расширения НЕ загружаются.
#BENCH_DT_PATH=/home/uam/backups/bench.dt
```

Add to `.gitignore` (в конец файла):

```gitignore
/benchmark/test.env
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — 8 passed.

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py benchmark/example.test.env .gitignore
git commit -m "feat(bench): парсинг test.env и BenchConfig" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Preflight, MCP-карточки и EnvConfig

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `BenchConfig`, `SetupError`; `agentmon.env.project_checks.validate_name`, `agentmon.env.project_checks.current_env_version`, `agentmon.env.config_schema`, `agentmon.env.mcp_catalog.build_mcp_json`, `agentmon.paths.same_path`, `agentmon.store.projects.ProjectRepo`, `agentmon.store.mcp.McpRepo`.
- Produces:
  - `McpPlan`
  - `EXTENSIONS`
  - `create_project_row(store, cfg) -> int`
  - `default_tcp_ok(url, timeout=3.0) -> bool`
  - `preflight(cfg, *, repo_root, store, registry, tcp_ok=default_tcp_ok) -> None`
  - `build_mcp_plans(cfg) -> list[McpPlan]`
  - `resolve_mcp_cards(mcp_repo, plans, *, project_id, project_name, log=print, created_out=None) -> tuple[dict[str, int], list[int]]`
  - `build_env_config(cfg, plans) -> EnvConfig`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_bench_setup.py`:

```python
import json

from agentmon.env.bench_setup import (
    build_env_config,
    build_mcp_plans,
    create_project_row,
    preflight,
    resolve_mcp_cards,
)
from agentmon.env.config_schema import EnvConfig
from agentmon.env.mcp_catalog import build_mcp_json
from agentmon.paths import same_path
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.mcp import McpRepo
from agentmon.store.projects import ProjectRepo
from agentmon.store.schema import init_schema


def make_store(tmp_path: Path):
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    return store


def make_registry(tmp_path: Path) -> ProjectRegistry:
    return ProjectRegistry(open_db(tmp_path / "agentmon.db"))


def make_repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "benchmark" / "cf").mkdir(parents=True)
    (root / "app" / "web" / "assets").mkdir(parents=True)
    (root / "app" / "web" / "assets" / "ЮнитТесты.cfe").write_bytes(b"")
    (root / "deps" / "mcp_tools_cfe").mkdir(parents=True)
    (root / "deps" / "mcp_tools_cfe" / "1c-mcp-tools-1.0.6.cfe").write_bytes(b"")
    return root


def test_preflight_ok(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    preflight(cfg, repo_root=make_repo_root(tmp_path), store=store,
              registry=registry, tcp_ok=lambda url: True)


def test_preflight_rejects_non_empty_project_dir(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    (Path(cfg.project_dir) / "x").write_text("x")
    with pytest.raises(SetupError, match="не пуст"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True)


def test_preflight_rejects_duplicate_project(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    store = make_store(tmp_path)
    create_project_row(store, cfg)
    with pytest.raises(SetupError, match="уже существует"):
        preflight(cfg, repo_root=make_repo_root(tmp_path), store=store,
                  registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_rejects_unreachable_shared_mcp(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    with pytest.raises(SetupError, match="недоступен"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: False)


def test_preflight_requires_cf_and_extensions(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    root = make_repo_root(tmp_path)
    (root / "app" / "web" / "assets" / "ЮнитТесты.cfe").unlink()
    with pytest.raises(SetupError, match="ЮнитТесты.cfe"):
        preflight(cfg, repo_root=root, store=make_store(tmp_path),
                  registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_dt_branch_does_not_require_cf(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="base.dt"), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    root = make_repo_root(tmp_path)
    (root / "benchmark" / "cf").rmdir()
    (tmp_path / "base.dt").write_bytes(b"")
    # project_dir пуст; dt существует
    preflight(cfg, repo_root=root, store=make_store(tmp_path),
              registry=make_registry(tmp_path), tcp_ok=lambda url: True)


def test_preflight_rejects_missing_dt(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="missing.dt"), repo_root=tmp_path)
    Path(cfg.project_dir).mkdir(parents=True)
    with pytest.raises(SetupError, match="BENCH_DT_PATH"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=make_registry(tmp_path),
                  tcp_ok=lambda url: True)


def test_preflight_rejects_registered_path(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    registry = make_registry(tmp_path)
    registry.add(name="old", path=cfg.project_dir, backend="local")
    with pytest.raises(SetupError, match="реестр"):
        preflight(cfg, repo_root=make_repo_root(tmp_path),
                  store=make_store(tmp_path), registry=registry,
                  tcp_ok=lambda url: True)


def test_build_mcp_plans_without_1c_md(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "code_index"]
    code_index = plans[-1]
    assert code_index.catalog_dir == str(Path(cfg.project_dir) / "src" / "cf")
    assert code_index.project_name == cfg.project_name
    assert json.loads("{" + code_index.connection_json + "}") == {
        "code_index": {
            "type": "http",
            "url": "http://localhost:8004/mcp",
        }
    }
    servers = build_mcp_json(build_env_config(cfg, plans).mcp)["mcpServers"]
    assert set(servers) == {"bsl_ls", "1c_platform", "code_index"}


def test_build_mcp_plans_with_1c_md(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_MD_URL="http://localhost/bench/hs/mcp"),
        repo_root=tmp_path,
    )
    plans = build_mcp_plans(cfg)
    assert [plan.mcp_name for plan in plans] == [
        "bsl_ls", "1c_platform", "1c-md", "code_index"]
    md = plans[2]
    assert md.standard_key == "1c-md-queries"
    assert json.loads("{" + md.connection_json + "}")["1c-md"]["url"] == (
        "http://localhost/bench/hs/mcp")


def test_build_env_config_produces_mcp_json(tmp_path):
    cfg = load_config(
        write_env(tmp_path, MCP_1C_MD_URL="http://localhost/bench/hs/mcp"),
        repo_root=tmp_path,
    )
    config = build_env_config(cfg, build_mcp_plans(cfg))
    assert isinstance(config, EnvConfig)
    assert config.agents == []
    servers = build_mcp_json(config.mcp)["mcpServers"]
    assert set(servers) == {"bsl_ls", "1c_platform", "1c-md", "code_index"}
    assert servers["1c_platform"]["type"] == "stdio"
    assert servers["1c_platform"]["args"][1] == "http://localhost:8002/sse"


def test_resolve_mcp_cards_reuses_shared_and_creates_project_cards(tmp_path):
    store = make_store(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project_id = create_project_row(store, cfg)
    repo = McpRepo(store)
    plans = build_mcp_plans(cfg)

    ids, created = resolve_mcp_cards(
        repo, plans, project_id=project_id, project_name=cfg.project_name)
    assert set(ids) == {"bsl-ls", "1c-platform", "code-index"}
    assert len(created) == 3

    cfg2 = load_config(
        write_env(tmp_path, BENCH_PROJECT_NAME="bench2",
                  BENCH_PROJECT_DIR=str(tmp_path / "project2")),
        repo_root=tmp_path)
    other_id = create_project_row(store, cfg2)
    ids2, created2 = resolve_mcp_cards(
        repo, build_mcp_plans(cfg2), project_id=other_id,
        project_name=cfg2.project_name)
    assert set(ids2) == set(ids)
    # bsl_ls и 1c_platform переиспользованы, code-index — новый (другой
    # catalog_dir/project_name), поэтому создана ровно одна карточка.
    assert len(created2) == 1
    assert repo.get(ids["code-index"])["catalog_dir"] != repo.get(
        ids2["code-index"])["catalog_dir"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ImportError: cannot import name 'preflight'` (или `EXTENSIONS`).

- [ ] **Step 3: Implement**

Add imports to `app/src/agentmon/env/bench_setup.py` (замените строку
`from .project_checks import infer_db_kind` из Task 1 на общий импорт):

```python
import json
import socket
import time
from urllib.parse import urlparse

from .config_schema import SCHEMA_VERSION, EnvConfig, McpSelection
from .project_checks import current_env_version, infer_db_kind, validate_name
from ..paths import same_path
from ..store.mcp import McpRepo
from ..store.projects import ProjectRepo
```

Append to the module:

```python
EXTENSIONS = (
    ("app/web/assets/ЮнитТесты.cfe", "ЮнитТесты"),
    ("deps/mcp_tools_cfe/1c-mcp-tools-1.0.6.cfe", "mcp_tools"),
)


@dataclass(frozen=True)
class McpPlan:
    standard_key: str
    mcp_name: str
    kind: str
    connection_json: str
    purpose: str = ""
    url: str | None = None
    port: int | None = None
    catalog_dir: str | None = None
    project_name: str | None = None


def _connection_http(name: str, url: str) -> str:
    return json.dumps({name: {"type": "http", "url": url}}, ensure_ascii=False)


def _connection_platform(url: str) -> str:
    return json.dumps(
        {"1c_platform": {
            "type": "stdio",
            "command": "python3",
            "args": [".claude/mcp/sse_stdio_bridge.py", url],
        }},
        ensure_ascii=False,
    )


def _url_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname or "", port


def default_tcp_ok(url: str, timeout: float = 3.0) -> bool:
    """True, если TCP-соединение с хостом/портом URL устанавливается."""
    host, port = _url_host_port(url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def create_project_row(store, cfg: BenchConfig) -> int:
    return ProjectRepo(store).add(
        name=cfg.project_name,
        path=cfg.project_dir,
        identifier=cfg.developer_id,
        email=cfg.developer_email,
        platform_dir=cfg.platform_path,
        platform_version=cfg.platform_version,
        db_kind=cfg.db_kind,
        db_connection=cfg.db_connection,
        web_publication="",
        env_version=current_env_version(),
        now=time.time(),
    )


def preflight(cfg: BenchConfig, *, repo_root: Path, store, registry,
              tcp_ok=default_tcp_ok) -> None:
    """Проверить всё, что можно проверить до создания каталога и записей БД."""
    ok, error = validate_name(cfg.project_name)
    if not ok:
        raise SetupError(f"недопустимое BENCH_PROJECT_NAME: {error}")

    project_dir = Path(cfg.project_dir)
    if project_dir.exists() and (not project_dir.is_dir()
                                 or any(project_dir.iterdir())):
        raise SetupError(f"каталог проекта должен быть пустым: {project_dir}")

    for row in ProjectRepo(store).list():
        if row["name"] == cfg.project_name or same_path(
                row["path"], cfg.project_dir):
            raise SetupError(
                "проект с таким именем или каталогом уже существует: "
                f"{row['name']} ({row['path']})")

    for project in registry.list():
        if same_path(project.path, cfg.project_dir):
            raise SetupError(
                f"каталог уже зарегистрирован в реестре: {project.path}")

    if cfg.dt_path:
        if not Path(cfg.dt_path).is_file():
            raise SetupError(f"не найден BENCH_DT_PATH: {cfg.dt_path}")
    else:
        cf_dir = repo_root / "benchmark" / "cf"
        if not cf_dir.is_dir():
            raise SetupError(f"не найден каталог конфигурации: {cf_dir}")
        for rel, name in EXTENSIONS:
            if not (repo_root / rel).is_file():
                raise SetupError(f"не найдено расширение {name}: {repo_root / rel}")

    for key, url in (("MCP_BSL_LS_URL", cfg.bsl_ls_url),
                     ("MCP_1C_PLATFORM_URL", cfg.platform_url)):
        if not tcp_ok(url):
            raise SetupError(f"{key}: сервер недоступен по адресу {url}")


def build_mcp_plans(cfg: BenchConfig) -> list[McpPlan]:
    bsl_host, bsl_port = _url_host_port(cfg.bsl_ls_url)
    plans = [
        McpPlan(
            standard_key="bsl-ls", mcp_name="bsl_ls", kind="docker",
            connection_json=_connection_http("bsl_ls", cfg.bsl_ls_url),
            purpose="Статический анализ кода на соответствие стандартам 1С",
            url=bsl_host, port=bsl_port,
        ),
        McpPlan(
            standard_key="1c-platform", mcp_name="1c_platform", kind="docker",
            connection_json=_connection_platform(cfg.platform_url),
            purpose=("Справочная информация по встроенным функциям, типам "
                     "данных, методам и свойствам платформы"),
        ),
    ]
    if cfg.one_c_md_url:
        plans.append(McpPlan(
            standard_key="1c-md-queries", mcp_name="1c-md", kind="extension",
            connection_json=_connection_http("1c-md", cfg.one_c_md_url),
            purpose=("Произвольные запросы к данным, вся информация об "
                     "актуальных метаданных конфигурации"),
        ))
    plans.append(McpPlan(
        standard_key="code-index", mcp_name="code_index", kind="docker",
        connection_json=_connection_http(
            "code_index",
            f"http://{cfg.code_index_host}:{cfg.code_index_port}/mcp"),
        purpose=("Полнотекстовый поиск по функциям и классам, граф вызовов, "
                 "паспорт объекта"),
        url=cfg.code_index_host, port=cfg.code_index_port,
        catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
        project_name=cfg.project_name,
    ))
    return plans


def _connection_equal(left: str | None, right: str) -> bool:
    """Сравнить фрагменты connection_json семантически, а не по форматированию."""
    try:
        return json.loads("{" + (left or "") + "}") == json.loads("{" + right + "}")
    except (TypeError, ValueError):
        return (left or "") == right


def _unique_card_name(repo, base: str) -> str:
    name, index = base, 2
    while repo.by_name(name) is not None:
        name = f"{base} {index}"
        index += 1
    return name


def resolve_mcp_cards(mcp_repo, plans: list[McpPlan], *, project_id: int,
                      project_name: str, log=print,
                      created_out: list[int] | None = None
                      ) -> tuple[dict[str, int], list[int]]:
    """Найти точные карточки или создать новые; связать их с проектом.

    created_out (необязательный) пополняется сразу после создания карточки —
    чтобы частичный сбой можно было откатить. Возвращает
    (карта standard_key → mcp_id, id созданных карточек).
    """
    existing = mcp_repo.list()
    by_key: dict[str, int] = {}
    created = created_out if created_out is not None else []
    for plan in plans:
        match = None
        for row in existing:
            if row.get("standard_key") != plan.standard_key:
                continue
            if not _connection_equal(row.get("connection_json"), plan.connection_json):
                continue
            if plan.standard_key == "code-index":
                if not same_path(row.get("catalog_dir") or "", plan.catalog_dir or ""):
                    continue
                if (row.get("project_name") or "") != (plan.project_name or ""):
                    continue
            match = row
            break
        if match is not None:
            by_key[plan.standard_key] = match["id"]
            log(f"✓ MCP «{plan.mcp_name}»: переиспользую карточку #{match['id']}")
            continue
        mid = mcp_repo.add(
            name=_unique_card_name(mcp_repo, f"{project_name}: {plan.mcp_name}"),
            purpose=plan.purpose,
            kind=plan.kind,
            standard_key=plan.standard_key,
            connection_json=plan.connection_json,
            port=plan.port,
            mcp_name=plan.mcp_name,
            url=plan.url,
            catalog_dir=plan.catalog_dir,
            project_name=plan.project_name,
        )
        by_key[plan.standard_key] = mid
        created.append(mid)
        existing = mcp_repo.list()
        log(f"✓ MCP «{plan.mcp_name}»: создана карточка #{mid}")
    mcp_repo.set_for_project(project_id, list(by_key.values()))
    return by_key, created


def build_env_config(cfg: BenchConfig, plans: list[McpPlan]) -> EnvConfig:
    return EnvConfig(
        schema_version=SCHEMA_VERSION,
        project_name=cfg.project_name,
        project_dir=cfg.project_dir,
        developer_id=cfg.developer_id,
        developer_email=cfg.developer_email,
        platform_dir=cfg.platform_path,
        platform_version=cfg.platform_version,
        db_kind=cfg.db_kind,
        db_connection=cfg.db_connection,
        web_publication="",
        mcp=[
            McpSelection(
                id=plan.standard_key,
                enabled=True,
                mode="managed",
                connection=plan.connection_json,
                catalog_dir=plan.catalog_dir,
                project_name=plan.project_name,
            )
            for plan in plans
        ],
        agents=[],
    )
```

Remove the unused `container_name` import if it was added; it is used in Task 5, so
either leave it unused (lint noise) or add it in Task 5. Add it in Task 5 only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — все тесты Task 1–2.

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py
git commit -m "feat(bench): preflight и MCP-карточки" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Команды базы 1С

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `BenchConfig`, `EXTENSIONS`, `SetupError`; `agentmon.env.devbase._parse_connection`.
- Produces:
  - `build_create_base_command(cfg) -> list[str]`
  - `ensure_base(cfg, *, prov, log=print) -> None`
  - `base_load_steps(cfg, repo_root) -> list[list[str]]`
  - `base_dump_steps() -> list[list[str]]`
  - `run_batch_step(project_dir, args, *, prov, log=print) -> None`
  - `default_http_ok(url, timeout=5.0) -> bool`
  - `check_mcp_url(url, *, http_ok, log=print) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_bench_setup.py`:

```python
from dataclasses import dataclass

from agentmon.env.bench_setup import (
    base_dump_steps,
    base_load_steps,
    build_create_base_command,
    check_mcp_url,
    ensure_base,
    run_batch_step,
)


@dataclass
class RunResult:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


class FakeProv:
    def __init__(self, results=None):
        self.calls = []
        self.results = list(results or [])

    def run(self, cmd, cwd=None, timeout=None):
        self.calls.append((list(cmd), cwd))
        return self.results.pop(0) if self.results else RunResult()


def test_create_base_command_server(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    cmd = build_create_base_command(cfg)
    assert cmd[1:] == [
        "CREATEINFOBASE", "Srvr=localhost;Ref=bench"]


def test_create_base_command_file(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DB_CONNECTION=str(tmp_path / "ib")),
        repo_root=tmp_path,
    )
    expected = tmp_path / "ib"
    cmd = build_create_base_command(cfg)
    assert cmd[1:] == ["CREATEINFOBASE", f'File="{expected}"']


def test_ensure_base_creates_file_base_only_when_missing(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DB_CONNECTION=str(tmp_path / "ib")),
        repo_root=tmp_path,
    )
    prov = FakeProv()
    expected = tmp_path / "ib"
    expected.mkdir()
    ensure_base(cfg, prov=prov, log=lambda line: None)
    assert prov.calls == []

    expected.rmdir()
    ensure_base(cfg, prov=prov, log=lambda line: None)
    assert prov.calls[0][0][1:] == [
        "CREATEINFOBASE", f'File="{expected}"']


def test_ensure_base_tolerates_existing_server_base(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    prov = FakeProv([RunResult(1, stderr="база уже существует")])
    lines = []
    ensure_base(cfg, prov=prov, log=lines.append)
    assert prov.calls[0][0][1] == "CREATEINFOBASE"
    assert any("⚠" in line for line in lines)


def test_base_load_steps_without_dt(tmp_path):
    root = make_repo_root(tmp_path)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    steps = base_load_steps(cfg, root)
    assert steps[0] == ["load-config", str(root / "benchmark" / "cf")]
    assert steps[1] == [
        "load-cfg-extension",
        str(root / "app" / "web" / "assets" / "ЮнитТесты.cfe"),
        "--name", "ЮнитТесты",
    ]
    assert steps[2] == ["update-db-cfg", "--extension", "ЮнитТесты"]
    assert steps[3] == [
        "load-cfg-extension",
        str(root / "deps" / "mcp_tools_cfe" / "1c-mcp-tools-1.0.6.cfe"),
        "--name", "mcp_tools",
    ]
    assert steps[4] == ["update-db-cfg", "--extension", "mcp_tools"]


def test_base_load_steps_with_dt(tmp_path):
    cfg = load_config(
        write_env(tmp_path, BENCH_DT_PATH="base.dt"), repo_root=tmp_path)
    assert base_load_steps(cfg, tmp_path) == [["restore-ib", cfg.dt_path]]


def test_base_dump_steps():
    assert base_dump_steps() == [
        ["dump-config", "src/cf"],
        ["dump-config", "src/cfe", "--all-extensions"],
    ]


def test_run_batch_step_uses_project_venv_and_raises_on_error(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project = Path(cfg.project_dir)
    (project / ".venv" / "bin").mkdir(parents=True)
    (project / ".venv" / "bin" / "python").write_text("")
    (project / ".claude" / "skills" / "1c-batch" / "scripts").mkdir(parents=True)
    (project / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py").write_text("")

    prov = FakeProv([RunResult(1, stdout="line1\n", stderr="ошибка 1С")])
    with pytest.raises(SetupError, match="ошибка 1С"):
        run_batch_step(cfg.project_dir, ["load-config", "/cf"],
                       prov=prov, log=lambda line: None)
    cmd, cwd = prov.calls[0]
    assert cmd[:2] == [
        str(project / ".venv" / "bin" / "python"),
        str(project / ".claude" / "skills" / "1c-batch" / "scripts" / "1c-batch.py"),
    ]
    assert cwd == cfg.project_dir


def test_check_mcp_url_fails_when_unreachable(tmp_path):
    with pytest.raises(SetupError, match="недоступен"):
        check_mcp_url("http://localhost:9999/hs/mcp", http_ok=lambda url: False)


def test_check_mcp_url_accepts_reachable():
    check_mcp_url("http://localhost:9999/hs/mcp", http_ok=lambda url: True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ImportError: cannot import name 'base_dump_steps'`.

- [ ] **Step 3: Implement**

Add imports:

```python
import urllib.error
import urllib.request

from .devbase import _parse_connection
```

Append:

```python
def build_create_base_command(cfg: BenchConfig) -> list[str]:
    """Команда CREATEINFOBASE для серверной или файловой базы."""
    conn = _parse_connection(cfg.db_kind, cfg.db_connection)
    if cfg.db_kind == "file":
        return [cfg.platform_path, "CREATEINFOBASE", f'File="{conn["path"]}"']
    return [
        cfg.platform_path, "CREATEINFOBASE",
        f'Srvr={conn["server"]};Ref={conn["base"]}',
    ]


def ensure_base(cfg: BenchConfig, *, prov, log=print) -> None:
    """Создать базу, если её нет. Существование серверной базы заранее не проверить:
    неудачный CREATEINFOBASE не фатален — ошибка проявится на restore/load."""
    if cfg.db_kind == "file":
        conn = _parse_connection(cfg.db_kind, cfg.db_connection)
        if Path(conn["path"]).exists():
            log(f"✓ база уже существует: {conn['path']}")
            return
    cmd = build_create_base_command(cfg)
    res = prov.run(cmd)
    if res.returncode != 0:
        tail = ((res.stdout or "") + (res.stderr or "")).strip()[-1000:]
        log(f"⚠ CREATEINFOBASE вернул код {res.returncode} "
            f"(возможно, база уже существует): {tail}")
    else:
        log(f"✓ база создана: {cfg.db_connection}")


def base_load_steps(cfg: BenchConfig, repo_root: Path) -> list[list[str]]:
    """Последовательность аргументов 1c-batch для подготовки базы."""
    if cfg.dt_path:
        return [["restore-ib", cfg.dt_path]]
    steps = [["load-config", str(repo_root / "benchmark" / "cf")]]
    for rel, name in EXTENSIONS:
        steps.append(["load-cfg-extension", str(repo_root / rel), "--name", name])
        steps.append(["update-db-cfg", "--extension", name])
    return steps


def base_dump_steps() -> list[list[str]]:
    return [
        ["dump-config", "src/cf"],
        ["dump-config", "src/cfe", "--all-extensions"],
    ]


def _venv_python(project_dir: str) -> str:
    base = Path(project_dir) / ".venv"
    suffix = Path("Scripts") / "python.exe" if os.name == "nt" else Path("bin") / "python"
    return str(base / suffix)


def run_batch_step(project_dir: str, args: list[str], *, prov, log=print) -> None:
    """Выполнить команду 1c-batch интерпретатором .venv проекта."""
    script = (Path(project_dir) / ".claude" / "skills" / "1c-batch"
              / "scripts" / "1c-batch.py")
    cmd = [_venv_python(project_dir), str(script), *args]
    res = prov.run(cmd, cwd=project_dir)
    if res.returncode != 0:
        tail = ((res.stdout or "") + (res.stderr or "")).strip()[-2000:]
        raise SetupError(
            f"1c-batch {' '.join(args)} завершился с кодом "
            f"{res.returncode}:\n{tail}")
    log(f"✓ 1c-batch {args[0]}")


def default_http_ok(url: str, timeout: float = 5.0) -> bool:
    """Любой HTTP-ответ (включая 4xx) означает, что сервис слушает."""
    request = urllib.request.Request(
        url, headers={"User-Agent": "ai1c-agentmon"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False


def check_mcp_url(url: str, *, http_ok=default_http_ok, log=print) -> None:
    if not http_ok(url):
        raise SetupError(f"1c-md недоступен по адресу {url}")
    log(f"✓ 1c-md доступен: {url}")
```

Note: `subprocess` is added here only for the default of later functions; if
unused after Task 3, it is used in Task 5/6.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — все тесты Task 1–3.

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py
git commit -m "feat(bench): команды загрузки и выгрузки базы 1С" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Импорт задач и git-коммиты

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `BenchConfig`, `create_project_row`, `SetupError`; `agentmon.env.task_json.to_local_iso` (через `agentmon.env.timefmt.to_local_iso`), `agentmon.store.tasks.TaskRepo`, `agentmon.env.devbase.git_init_project`, `agentmon.env.devbase.git_commit_all`.
- Produces:
  - `ImportedTask`
  - `import_tasks(*, project_id, cfg, repo_root, store, log=print) -> list[ImportedTask]`
  - `commit_init(cfg, prov) -> None`
  - `commit_baseline(cfg, tasks, prov) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_bench_setup.py`:

```python
import shutil

from agentmon.env.bench_setup import (
    ImportedTask,
    commit_baseline,
    commit_init,
    import_tasks,
)
from agentmon.store.tasks import TaskRepo


def make_tasks(root: Path) -> Path:
    task_dir = root / "benchmark" / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    data = {
        "id": 23,
        "project_id": 13,
        "name": "Метаданные",
        "identifier": "#001",
        "goal": "Добавить метаданные",
        "plan": "План",
        "constraints": "Ограничения",
        "tests": "Тесты",
        "status": "planned",
        "stage": None,
        "started_at": None,
        "finished_at": None,
        "created_at": None,
        "kind": "real",
        "update_db": True,
        "max_minutes": 60,
        "mark_changes": False,
        "developer_id": "alex",
        "stages": [
            {"name": "develop", "enabled": True, "subagent": "developer",
             "artifact": "DEVELOP.md", "gate": False, "approved": False,
             "status": "pending", "changed_files": [], "started_at": None,
             "finished_at": None, "iteration": 1},
        ],
    }
    (task_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "TASK.md").write_text(
        "# Задача #001 (#23): Метаданные\n\n## Цель\nДобавить метаданные\n\n"
        "## Правка пользователя\nНе потерять эту строку.\n",
        encoding="utf-8",
    )
    (task_dir / "extra.txt").write_text("extra", encoding="utf-8")
    return task_dir


def test_import_tasks_copies_rewrites_and_preserves_body(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)

    imported = import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                            store=store, log=lambda line: None)

    assert len(imported) == 1
    item = imported[0]
    assert isinstance(item, ImportedTask)
    assert item.identifier == "#001"
    assert item.folder == "task##001"

    task_row = TaskRepo(store).get(item.task_id)
    assert task_row["project_id"] == project_id
    assert task_row["name"] == "Метаданные"
    assert task_row["identifier"] == "#001"
    assert json.loads(task_row["stages_json"])[0]["name"] == "develop"

    task_dir = Path(cfg.project_dir) / "tasks" / "task##001"
    assert (task_dir / "extra.txt").read_text(encoding="utf-8") == "extra"
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    assert data["id"] == item.task_id
    assert data["project_id"] == project_id
    assert data["developer_id"] == "alex"
    assert data["status"] == "planned"
    assert data["created_at"] and "T" in data["created_at"]
    assert data["update_db"] is True
    assert data["mark_changes"] is False
    assert data["stages"][0]["status"] == "pending"

    md = (task_dir / "TASK.md").read_text(encoding="utf-8")
    assert md.startswith(f"# Задача #001 (#{item.task_id}):")
    assert "Не потерять эту строку." in md


def test_import_tasks_requires_at_least_one_task(tmp_path):
    root = make_repo_root(tmp_path)
    (root / "benchmark" / "tasks").mkdir(parents=True)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store = make_store(tmp_path)
    project_id = create_project_row(store, cfg)
    Path(cfg.project_dir).mkdir(parents=True)
    with pytest.raises(SetupError, match="ни одной задачи"):
        import_tasks(project_id=project_id, cfg=cfg, repo_root=root,
                     store=store, log=lambda line: None)


class GitProv:
    def __init__(self):
        self.calls = []

    def mkdirs(self, paths):
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)

    def exists(self, path):
        return False

    def is_file(self, path):
        return False

    def write_text(self, path, content):
        pass

    def read_text(self, path):
        return ""

    def run(self, cmd, cwd=None, timeout=None):
        self.calls.append((list(cmd), cwd))
        return RunResult()


def test_commit_init_and_baseline(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    Path(cfg.project_dir).mkdir(parents=True)
    prov = GitProv()

    commit_init(cfg, prov)
    assert prov.calls[0][0] == ["git", "init"]
    init_commit = prov.calls[-1][0]
    assert "commit" in init_commit and "init" in init_commit

    tasks = [ImportedTask(identifier="#001", task_id=7, folder="task##001")]
    commit_baseline(cfg, tasks, prov)
    baseline_commit = prov.calls[-1][0]
    assert "baseline before task#001" in baseline_commit
```

Примечание: проверку `created_at` лучше упростить одним assert на ISO-формат,
чтобы не зависеть от часового пояса:

```python
    assert data["created_at"] and "T" in data["created_at"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ImportError: cannot import name 'ImportedTask'`.

- [ ] **Step 3: Implement**

Add imports:

```python
import shutil

from .devbase import git_commit_all, git_init_project
from .timefmt import to_local_iso
from ..store.tasks import TaskRepo
```

Append:

```python
@dataclass(frozen=True)
class ImportedTask:
    identifier: str
    task_id: int
    folder: str


_TASK_HEADER_RE = re.compile(r"^(# Задача .+?) \(#\d+\):", re.MULTILINE)


def _source_task_dirs(repo_root: Path) -> list[Path]:
    tasks_root = repo_root / "benchmark" / "tasks"
    if not tasks_root.is_dir():
        return []
    return sorted(
        path for path in tasks_root.iterdir()
        if path.is_dir() and (path / "task.json").is_file()
    )


def import_tasks(*, project_id: int, cfg: BenchConfig, repo_root: Path,
                 store, log=print) -> list[ImportedTask]:
    """Скопировать задачи benchmark/tasks, завести их в БД и обновить id в файлах."""
    sources = _source_task_dirs(repo_root)
    if not sources:
        raise SetupError(f"в {repo_root / 'benchmark' / 'tasks'} нет ни одной задачи")

    repo = TaskRepo(store)
    imported: list[ImportedTask] = []
    for source in sources:
        raw = (source / "task.json").read_text(encoding="utf-8")
        data = json.loads(raw)
        identifier = str(data.get("identifier") or "").strip()
        if not identifier:
            identifier = source.name.removeprefix("task#")

        now = time.time()
        task_id = repo.add(
            project_id=project_id,
            name=data.get("name", ""),
            identifier=identifier,
            goal=data.get("goal", ""),
            plan=data.get("plan", ""),
            constraints=data.get("constraints", ""),
            tests=data.get("tests", ""),
            stages_json=json.dumps(data.get("stages", []), ensure_ascii=False),
            status="planned",
            stage=None,
            now=now,
            kind=data.get("kind") or "real",
            update_db=1 if data.get("update_db") else 0,
            max_minutes=int(data.get("max_minutes") or 60),
            interactive=0,
            mark_changes=1 if data.get("mark_changes") else 0,
        )

        destination = Path(cfg.project_dir) / "tasks" / source.name
        shutil.copytree(source, destination)

        data["id"] = task_id
        data["project_id"] = project_id
        data["developer_id"] = cfg.developer_id
        data["status"] = "planned"
        data["stage"] = None
        data["started_at"] = None
        data["finished_at"] = None
        data["created_at"] = to_local_iso(now)
        data["update_db"] = bool(data.get("update_db"))
        data["mark_changes"] = bool(data.get("mark_changes"))
        (destination / "task.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        task_md = destination / "TASK.md"
        if task_md.is_file():
            text = task_md.read_text(encoding="utf-8")
            updated = _TASK_HEADER_RE.sub(
                lambda match: f"{match.group(1)} (#{task_id}):", text, count=1)
            if updated != text:
                task_md.write_text(updated, encoding="utf-8")

        imported.append(ImportedTask(identifier, task_id, source.name))
        log(f"✓ задача {identifier} → #{task_id} ({source.name})")
    return imported


def commit_init(cfg: BenchConfig, prov) -> None:
    git_init_project(prov, cfg.project_dir, config=cfg)
    git_commit_all(prov, cfg.project_dir, "init", config=cfg)


def commit_baseline(cfg: BenchConfig, tasks: list[ImportedTask], prov) -> None:
    if not tasks:
        return
    git_commit_all(
        prov, cfg.project_dir,
        f"baseline before task{tasks[0].identifier}", config=cfg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — все тесты Task 1–4.

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py
git commit -m "feat(bench): импорт задач и git-коммиты" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: code_index — запуск и ожидание индексации

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: `BenchConfig`, `SetupError`; `agentmon.env.mcp_docker`, `agentmon.env.mcp_sources`, `agentmon.env.mcp_docker_recipes.launch_params`, `recipe_for`, `container_name`.
- Produces:
  - `CODE_INDEX_CONTAINER`
  - `launch_code_index(cfg, *, repo_root, mid, run=subprocess.run, image_exists=..., launch=..., build_image=None, log=print) -> str`
  - `wait_code_index_ready(name, *, cfg, run=subprocess.run, sleep=time.sleep, clock=time.monotonic, log=print) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_bench_setup.py`:

```python
from agentmon.env.bench_setup import (
    CODE_INDEX_CONTAINER,
    launch_code_index,
    wait_code_index_ready,
)


def test_launch_code_index_removes_old_container_with_volumes(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    project = Path(cfg.project_dir)
    (project / "src" / "cf").mkdir(parents=True)
    state_root = tmp_path / "repo"
    state_root.mkdir()
    calls = []
    launched = {}

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return RunResult(1)  # docker rm для отсутствующего контейнера

    def fake_launch(**kwargs):
        launched.update(kwargs)
        return {"ok": True, "log": ""}

    name = launch_code_index(
        cfg, repo_root=state_root, mid=42, run=fake_run,
        image_exists=lambda image: True, launch=fake_launch,
        log=lambda line: None,
    )
    assert name == CODE_INDEX_CONTAINER
    assert calls[0] == ["docker", "rm", "-f", "-v", CODE_INDEX_CONTAINER]
    assert launched["name"] == CODE_INDEX_CONTAINER
    assert launched["port"] == cfg.code_index_port
    volumes = launched["volumes"]
    assert f"{project / 'src' / 'cf'}:/repos/src" in volumes
    toml = state_root / ".ai1c" / "mcp-state" / "42" / "daemon.toml"
    assert toml.is_file()
    assert f'alias = "{cfg.project_name}"' in toml.read_text(encoding="utf-8")
    assert 'path = "/repos/src"' in toml.read_text(encoding="utf-8")


def test_launch_code_index_raises_when_launch_fails(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    with pytest.raises(SetupError, match="контейнер"):
        launch_code_index(
            cfg, repo_root=tmp_path, mid=1,
            run=lambda cmd, **kwargs: RunResult(),
            image_exists=lambda image: True,
            launch=lambda **kwargs: {"ok": False, "log": "boom"},
            log=lambda line: None,
        )


def test_wait_code_index_ready_returns_when_ready(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    status = json.dumps({
        "status": "running",
        "paths": [{"path": "/repos/src", "status": "ready"}],
    })
    lines = []
    wait_code_index_ready(
        CODE_INDEX_CONTAINER, cfg=cfg,
        run=lambda cmd, **kwargs: RunResult(0, status),
        sleep=lambda seconds: None, clock=lambda: 0.0,
        log=lines.append,
    )
    assert any("готов" in line for line in lines)


def test_wait_code_index_ready_fails_on_error_status(tmp_path):
    cfg = load_config(write_env(tmp_path), repo_root=tmp_path)
    status = json.dumps({
        "status": "running",
        "paths": [{"path": "/repos/src", "status": "error"}],
    })
    with pytest.raises(SetupError, match="error"):
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=lambda cmd, **kwargs: RunResult(0, status),
            sleep=lambda seconds: None, clock=lambda: 0.0,
            log=lambda line: None,
        )


def test_wait_code_index_ready_times_out(tmp_path):
    cfg = load_config(
        write_env(tmp_path, CODE_INDEX_WAIT_MINUTES="1"), repo_root=tmp_path)
    now = [0.0]

    def fake_sleep(seconds):
        now[0] += seconds

    with pytest.raises(SetupError, match="CODE_INDEX_WAIT_MINUTES"):
        wait_code_index_ready(
            CODE_INDEX_CONTAINER, cfg=cfg,
            run=lambda cmd, **kwargs: RunResult(
                0, json.dumps({"paths": [
                    {"path": "/repos/src", "status": "initial_indexing"}]})),
            sleep=fake_sleep, clock=lambda: now[0],
            log=lambda line: None,
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ImportError: cannot import name 'CODE_INDEX_CONTAINER'`.

- [ ] **Step 3: Implement**

Add imports:

```python
import subprocess

from .mcp_docker_recipes import container_name, launch_params, recipe_for
from . import mcp_docker
from . import mcp_sources
```

Append:

```python
CODE_INDEX_CONTAINER = "ai1c-mcp-code_index"


def _build_code_index_image(repo_root: Path, *, run, log=print) -> None:
    recipe = recipe_for("code-index")
    build = recipe.build
    if build is None:
        raise SetupError(f"образ {recipe.image} отсутствует, а сборка недоступна")
    cloned = mcp_sources.clone(build, str(repo_root), run=run)
    if not cloned["ok"]:
        raise SetupError("не удалось скачать исходники code-index:\n"
                         + cloned.get("log", ""))
    built = mcp_docker.build(
        recipe.image, str(repo_root / build.dockerfile),
        str(repo_root / build.context), run=run)
    if not built["ok"]:
        raise SetupError("не удалось собрать образ code-index:\n"
                         + built.get("log", ""))
    log(f"✓ образ code-index собран: {recipe.image}")


def launch_code_index(cfg: BenchConfig, *, repo_root: Path, mid: int,
                      run=subprocess.run, image_exists=mcp_docker.image_exists,
                      launch=mcp_docker.launch, build_image=None,
                      log=print) -> str:
    """Пересоздать контейнер code_index и вернуть его имя."""
    name = container_name({"mcp_name": "code_index"})
    run(["docker", "rm", "-f", "-v", name], capture_output=True, text=True)

    state_dir = Path(repo_root) / ".ai1c" / "mcp-state" / str(mid)
    params = launch_params(
        "code-index",
        port=cfg.code_index_port,
        catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
        state_dir=str(state_dir),
        project_name=cfg.project_name,
    )
    if not image_exists(params["image"]):
        if build_image is None:
            _build_code_index_image(repo_root, run=run, log=log)
        else:
            build_image()

    result = launch(
        name=name,
        image=params["image"],
        port=cfg.code_index_port,
        internal_port=params["internal_port"],
        env=params["env"],
        volumes=params["volumes"],
        network=params.get("network"),
        run=run,
    )
    if not result.get("ok"):
        raise SetupError(
            f"не удалось запустить контейнер {name}:\n{result.get('log', '')}")
    log(f"✓ контейнер code_index запущен: {name} "
        f"(порт {cfg.code_index_port})")
    return name


def _daemon_status(name: str, run):
    result = run(
        ["docker", "exec", name, "env",
         "CODE_INDEX_HOME=/data/code-index-home",
         "bsl-indexer", "daemon", "status", "--json"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except (TypeError, ValueError):
        return None


def wait_code_index_ready(name: str, *, cfg: BenchConfig,
                          run=subprocess.run, sleep=time.sleep,
                          clock=time.monotonic, log=print) -> None:
    """Дождаться статуса ready для всех путей (полная первичная индексация)."""
    deadline = clock() + cfg.code_index_wait_minutes * 60
    last_state = None
    while True:
        data = _daemon_status(name, run)
        if data:
            paths = data.get("paths") or []
            errors = [p for p in paths if p.get("status") == "error"]
            if errors:
                raise SetupError(
                    "code_index завершился с ошибкой: "
                    + ", ".join(f"{p.get('path')}: {p.get('status')}"
                                for p in errors))
            if paths and all(p.get("status") == "ready" for p in paths):
                log("✓ индекс code_index готов: "
                    + ", ".join(p.get("path", "?") for p in paths))
                return
            state = ", ".join(
                f"{p.get('path')}: {p.get('status')}" for p in paths)
            if state != last_state:
                log(f"… индексация code_index: {state or 'нет данных'}")
                last_state = state
        if clock() >= deadline:
            raise SetupError(
                "code_index не проиндексировал базу за "
                f"{cfg.code_index_wait_minutes} мин; увеличьте "
                "CODE_INDEX_WAIT_MINUTES")
        sleep(15)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — все тесты Task 1–5.

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py
git commit -m "feat(bench): запуск и ожидание code_index" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Оркестратор, откат и CLI

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Create: `benchmark/setup_benchmark.py`
- Modify: `benchmark/README.md`
- Test: `app/tests/env/test_bench_setup.py`

**Interfaces:**
- Consumes: всё из Task 1–5; `agentmon.env.installer.install_environment`.
- Produces:
  - `RollbackState`, `SetupResult`
  - `rollback(state, *, store, run=subprocess.run, log=print) -> None`
  - `run_setup(cfg, *, repo_root, store, registry, prov=None, run=..., sleep=..., clock=..., log=..., tcp_ok=..., http_ok=..., install_env=install_environment, batch_run=run_batch_step, launch_index=launch_code_index, wait_index=wait_code_index_ready) -> SetupResult`

- [ ] **Step 1: Write the failing tests**

Append to `app/tests/env/test_bench_setup.py`:

```python
from agentmon.env.bench_setup import RollbackState, run_setup, rollback


class OrchestratorProv(GitProv):
    """Провизор, которого хватает install_env-фейку и git-хелперам."""

    def mkdirs(self, paths):
        for path in paths:
            Path(path).mkdir(parents=True, exist_ok=True)


def fake_install_env(config, **kwargs):
    Path(config.project_dir, ".claude").mkdir(parents=True, exist_ok=True)
    Path(config.project_dir, ".claude", "VERSION").write_text("test")
    (Path(config.project_dir) / "src" / "cf").mkdir(parents=True, exist_ok=True)
    (Path(config.project_dir) / "src" / "cfe").mkdir(parents=True, exist_ok=True)
    return []


def test_run_setup_happy_path(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    batch_calls, waited = [], []

    result = run_setup(
        cfg, repo_root=root, store=store, registry=registry,
        prov=OrchestratorProv(),
        tcp_ok=lambda url: True,
        http_ok=lambda url: True,
        install_env=fake_install_env,
        batch_run=lambda project_dir, args, **kwargs: batch_calls.append(args),
        launch_index=lambda cfg, **kwargs: CODE_INDEX_CONTAINER,
        wait_index=lambda name, **kwargs: waited.append(name),
        log=lambda line: None,
    )

    assert result.project_id > 0
    assert result.container == CODE_INDEX_CONTAINER
    assert result.task_ids and len(result.task_ids) == 1
    assert batch_calls[0][0] == "load-config"
    assert batch_calls[-1][0] == "dump-config"
    assert waited == [CODE_INDEX_CONTAINER]
    assert registry.list()[0].path == cfg.project_dir
    assert TaskRepo(store).list(project_id=result.project_id)


def test_run_setup_rolls_back_db_and_container_on_error(tmp_path):
    root = make_repo_root(tmp_path)
    make_tasks(root)
    cfg = load_config(write_env(tmp_path), repo_root=root)
    store, registry = make_store(tmp_path), make_registry(tmp_path)
    removed = []

    def failing_wait(name, **kwargs):
        raise SetupError("индексация не удалась")

    def fake_run(cmd, **kwargs):
        removed.append(list(cmd))
        return RunResult()

    with pytest.raises(SetupError, match="индексация"):
        run_setup(
            cfg, repo_root=root, store=store, registry=registry,
            prov=OrchestratorProv(), run=fake_run,
            tcp_ok=lambda url: True, http_ok=lambda url: True,
            install_env=fake_install_env,
            batch_run=lambda project_dir, args, **kwargs: None,
            launch_index=lambda cfg, **kwargs: CODE_INDEX_CONTAINER,
            wait_index=failing_wait,
            log=lambda line: None,
        )

    assert ProjectRepo(store).list() == []
    assert McpRepo(store).list() == []
    assert TaskRepo(store).list() == []
    assert registry.list() == []
    assert ["docker", "rm", "-f", "-v", CODE_INDEX_CONTAINER] in removed
    assert Path(cfg.project_dir).exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: FAIL — `ImportError: cannot import name 'run_setup'`.

- [ ] **Step 3: Implement orchestration**

Add imports:

```python
from .installer import install_environment
```

Append:

```python
@dataclass(frozen=True)
class SetupResult:
    project_id: int
    task_ids: list[int]
    container: str
    project_dir: str


@dataclass
class RollbackState:
    project_dir: str
    project_id: int | None = None
    task_ids: list[int] = None
    created_mcp_ids: list[int] = None
    container: str | None = None

    def __post_init__(self):
        if self.task_ids is None:
            self.task_ids = []
        if self.created_mcp_ids is None:
            self.created_mcp_ids = []


def rollback(state: RollbackState, *, store, run=subprocess.run, log=print) -> None:
    """Убрать записи этого запуска; каталог проекта оставить для диагностики."""
    task_repo = TaskRepo(store)
    for task_id in state.task_ids:
        try:
            task_repo.delete(task_id)
        except Exception as exc:                       # noqa: BLE001
            log(f"⚠ откат задачи #{task_id}: {exc}")

    mcp_repo = McpRepo(store)
    if state.project_id is not None:
        try:
            mcp_repo.set_for_project(state.project_id, [])
        except Exception as exc:                       # noqa: BLE001
            log(f"⚠ откат связей MCP: {exc}")
    for mid in state.created_mcp_ids:
        try:
            mcp_repo.delete(mid)
        except Exception as exc:                       # noqa: BLE001
            log(f"⚠ откат MCP #{mid}: {exc}")
    if state.project_id is not None:
        try:
            ProjectRepo(store).delete(state.project_id)
        except Exception as exc:                       # noqa: BLE001
            log(f"⚠ откат проекта #{state.project_id}: {exc}")

    if state.container:
        try:
            res = run(["docker", "rm", "-f", "-v", state.container],
                      capture_output=True, text=True)
        except Exception as exc:                       # noqa: BLE001
            warn(f"откат контейнера {state.container}: {exc}")
        else:
            code = getattr(res, "returncode", 0)
            if code != 0:
                tail = ((getattr(res, "stdout", "") or "")
                        + (getattr(res, "stderr", "") or "")).strip()[-500:]
                warn(f"откат контейнера {state.container}: docker rm "
                     f"вернул код {code}: {tail}")

    if warnings:
        log("✗ Откат выполнен частично: " + "; ".join(warnings))
    else:
        log("✗ Откат выполнен.")
    log(f"✗ Каталог проекта оставлен для диагностики: {state.project_dir}. "
        "Удалите его перед повторным запуском.")


def run_setup(cfg: BenchConfig, *, repo_root: Path, store, registry,
              prov=None, run=subprocess.run, sleep=time.sleep,
              clock=time.monotonic, log=print, tcp_ok=default_tcp_ok,
              http_ok=default_http_ok, install_env=install_environment,
              batch_run=run_batch_step, launch_index=launch_code_index,
              wait_index=wait_code_index_ready) -> SetupResult:
    """Полный сценарий подготовки проекта. Ошибка → откат записей БД."""
    if prov is None:
        from ..backends.local import LocalProvisioner
        prov = LocalProvisioner()

    preflight(cfg, repo_root=repo_root, store=store, registry=registry,
              tcp_ok=tcp_ok)

    state = RollbackState(project_dir=cfg.project_dir)
    try:
        log(f"▶ проект «{cfg.project_name}» ({cfg.project_dir})")
        Path(cfg.project_dir).mkdir(parents=True)

        project_id = create_project_row(store, cfg)
        state.project_id = project_id

        plans = build_mcp_plans(cfg)
        by_key, created = resolve_mcp_cards(
            McpRepo(store), plans, project_id=project_id,
            project_name=cfg.project_name, log=log,
            created_out=state.created_mcp_ids)
        config = build_env_config(cfg, plans)

        log("▶ окружение проекта")
        for event in install_env(
                config, update=False, register=lambda cfg_: None,
                dump_cf=False, dump_cfe=False, git_init=False,
                db_user=cfg.db_user, db_password=cfg.db_password, prov=prov):
            detail = f" {event.detail}" if event.detail else ""
            log(f"[{event.step}] {event.status}{detail}")

        log("▶ база 1С")
        ensure_base(cfg, prov=prov, log=log)
        for args in base_load_steps(cfg, repo_root):
            batch_run(cfg.project_dir, args, prov=prov, log=log)
        if cfg.one_c_md_url:
            check_mcp_url(cfg.one_c_md_url, http_ok=http_ok, log=log)

        log("▶ выгрузка cf/cfe")
        for args in base_dump_steps():
            batch_run(cfg.project_dir, args, prov=prov, log=log)

        log("▶ code_index")
        container = launch_index(
            cfg, repo_root=repo_root, mid=by_key["code-index"],
            run=run, log=log)
        state.container = container

        log("▶ git init")
        commit_init(cfg, prov)

        log("▶ задачи benchmark")
        tasks = import_tasks(project_id=project_id, cfg=cfg,
                             repo_root=repo_root, store=store, log=log)
        state.task_ids = [task.task_id for task in tasks]
        commit_baseline(cfg, tasks, prov)

        log("▶ ожидание индексации code_index")
        wait_index(container, cfg=cfg, run=run, sleep=sleep, clock=clock,
                   log=log)

        registry.add(name=cfg.project_name, path=cfg.project_dir,
                     backend="local")
        return SetupResult(
            project_id=project_id,
            task_ids=[task.task_id for task in tasks],
            container=container,
            project_dir=cfg.project_dir,
        )
    except BaseException:
        rollback(state, store=store, run=run, log=log)
        raise
```

- [ ] **Step 4: Create the CLI**

Create `benchmark/setup_benchmark.py`:

```python
#!/usr/bin/env python3
"""Одна команда подготовки benchmark-окружения AgentMon.

Запуск из корня репозитория (после python bootstrap.py):

    .venv/bin/python benchmark/setup_benchmark.py [--env benchmark/test.env]
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_repo_env() -> None:
    """Прочитать .ai1c.env в os.environ до импорта agentmon.config."""
    env_file = ROOT / ".ai1c.env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        if sep and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Подготовка benchmark-окружения AgentMon")
    parser.add_argument(
        "--env", default=str(ROOT / "benchmark" / "test.env"),
        help="путь к test.env (по умолчанию benchmark/test.env)")
    args = parser.parse_args(argv)

    os.chdir(ROOT)
    load_repo_env()

    try:
        from agentmon import config
        from agentmon.backends.local import LocalProvisioner
        from agentmon.env.bench_setup import (SetupError, load_config,
                                               run_setup)
        from agentmon.registry import ProjectRegistry, open_db
        from agentmon.store.db import connect
        from agentmon.store.schema import init_schema
    except ModuleNotFoundError as exc:
        print(f"✗ не удалось импортировать agentmon: {exc}", file=sys.stderr)
        print("Запустите из .venv репозитория: python bootstrap.py",
              file=sys.stderr)
        return 1

    env_path = Path(args.env).expanduser()
    if not env_path.is_absolute():
        env_path = ROOT / env_path

    try:
        cfg = load_config(env_path, repo_root=ROOT)
    except SetupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1

    try:
        store = connect(config.DSN)
        init_schema(store)
    except Exception as exc:                           # noqa: BLE001
        print(f"✗ не удалось открыть store {config.DSN}: {exc}",
              file=sys.stderr)
        return 1
    try:
        registry = ProjectRegistry(open_db(config.DB_PATH))
    except Exception as exc:                           # noqa: BLE001
        print(f"✗ не удалось открыть реестр {config.DB_PATH}: {exc}",
              file=sys.stderr)
        return 1

    try:
        result = run_setup(
            cfg, repo_root=ROOT, store=store, registry=registry,
            prov=LocalProvisioner())
    except SetupError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("✗ прервано пользователем", file=sys.stderr)
        return 130

    print("\n✓ Готово")
    print(f"  проект:      #{result.project_id} {cfg.project_name}")
    print(f"  каталог:     {result.project_dir}")
    print(f"  задачи:      {', '.join(f'#{tid}' for tid in result.task_ids)}")
    print(f"  code_index:  {result.container} "
          f"(порт {cfg.code_index_port})")
    print(f"  bsl_ls:      {cfg.bsl_ls_url}")
    print(f"  1c_platform: {cfg.platform_url}")
    if cfg.one_c_md_url:
        print(f"  1c-md:       {cfg.one_c_md_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Update benchmark README**

Добавить в `benchmark/README.md` раздел:

```markdown
## Подготовка окружения

1. Скопируйте пример и заполните значения:

   ```bash
   cp benchmark/example.test.env benchmark/test.env
   ```

   `benchmark/test.env` содержит пароль 1С и в git не попадает.

2. Запустите из корня репозитория:

   ```bash
   .venv/bin/python benchmark/setup_benchmark.py
   ```

   Скрипт создаст проект, окружение, базу (из `.dt` или из `cf/` +
   расширений), выгрузки `src/cf`/`src/cfe`, задачи в `tasks/` и БД AgentMon,
   пересоздаст контейнер `ai1c-mcp-code_index` и дождётся полной индексации.
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd app && .venv/bin/python -m pytest tests/env/test_bench_setup.py -q`
Expected: PASS — все тесты Task 1–6.

- [ ] **Step 7: Commit**

```bash
git add app/src/agentmon/env/bench_setup.py app/tests/env/test_bench_setup.py benchmark/setup_benchmark.py benchmark/README.md
git commit -m "feat(bench): оркестратор и CLI подготовки проекта" -m "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** test.env/example/gitignore — Task 1; preflight/регистрация/MCP — Task 2; база 1С (create/restore/cf/расширения/выгрузки) — Task 3; задачи/git — Task 4; code_index — Task 5; оркестратор/откат/CLI/README — Task 6.
- **Плейсхолдеры:** нет TBD/TODO; каждый шаг содержит код или команду.
- **Согласованность:** `BenchConfig` поля используются одинаково; `resolve_mcp_cards` возвращает `(dict, created)` и в Task 2, и в Task 6; `run_setup` использует `by_key["code-index"]` (ключ стабилен); `launch_code_index` возвращает имя контейнера; `ImportedTask.identifier` даёт `baseline before task#001`.
- **Риски:** серверный `CREATEINFOBASE` может требовать прав кластера — ошибка проявится на restore/load с логом 1c-batch; полная индексация BSP может занять часы — таймаут 360 мин настраивается.

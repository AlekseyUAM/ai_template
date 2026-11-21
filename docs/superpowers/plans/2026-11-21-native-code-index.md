# Нативный code-index — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перевести code-index на нативное развёртывание: один вид карточки, несколько баз в одном сервисе, benchmark на своих процессах с `CODE_INDEX_DIR`; удалить Docker-кнопку, Docker-рецепт и рестарт контейнера между задачами.

**Architecture:** Новый `code_index_toml.py` мерджит `[[paths]]` без затирания; `code_index_local.py` разворачивает общий сервис на `code_index_dir` (бинарь, `daemon.toml`, `service.json`, autostart) и добавляет базы; `code_index_bench.py` поднимает detached daemon/serve для benchmark с PID-файлом и очисткой; UI/API переводят code-index на один нативный вид.

**Tech Stack:** Python 3.10+ (stdlib), FastAPI, pytest, `bsl-indexer` (upstream binary), systemd/schtasks/launchd для agentmon autostart.

**Spec:** `docs/superpowers/specs/2026-11-21-native-code-index-design.md`

## Global Constraints

- Не трогать `deps/**`, `tmp/**`, тестовый проект `D:\projects\test`.
- Только stdlib Python; новых зависимостей нет.
- Кроссплатформенность: Windows/Linux/macOS; пути через `pathlib`, UTF-8.
- Тексты `template/.claude/**` — на английском.
- Коммиты локально в `main`, без push; один логический коммит на таск.
- Alias базы — ровно `project_name` (уже реализовано в code-index).
- `service.json` — единственный источник порта нативного сервиса.
- Benchmark чистит только `CODE_INDEX_DIR` и `<catalog>/.code-index`; `CODE_INDEX_DIR` не должен лежать внутри `BENCH_PROJECT_DIR`.

## File Structure

```
app/src/agentmon/env/
  code_index_toml.py       # новый: merge [[paths]], ensure sections
  code_index_local.py      # переработан: сервис, service.json, multi-base
  code_index_bench.py      # новый: detached daemon/serve, PID, clean/wait
  autostart.py             # + stop/restart
  mcp_types.py             # один видимый code-index, hidden legacy
  mcp_api.py               # deploy-local для code-index, порт сервиса
  bench_setup.py           # нативный запуск, CODE_INDEX_DIR
app/web/mcp.js             # одна кнопка «Развернуть»
app/tests/env/
  test_code_index_toml.py  # новый
  test_code_index_local.py # расширен
  test_code_index_bench.py # новый
  test_autostart.py        # расширен
  test_mcp_types.py        # обновлён
  test_mcp_api.py          # обновлён
  test_bench_setup.py      # обновлён
benchmark/
  bench_index.py           # удалить
  tests/test_bench_index.py# удалить
  bench_run.py             # убрать index_refresh
  bench_metrics.py         # убрать строку индекса
  example.test.env         # + CODE_INDEX_DIR
  README.md                # нативный setup
template/.claude/skills/mcp-usage/SKILL.md
docs/mcp/code-index-*.md
docs/superpowers/specs/2026-11-21-benchmark-environment-fixes-design.md
docs/superpowers/plans/2026-11-21-benchmark-environment-fixes.md
```

---

### Task 1: `code_index_toml.py` — merge путей и секций

**Files:**
- Create: `app/src/agentmon/env/code_index_toml.py`
- Create: `app/tests/env/test_code_index_toml.py`
- Modify: `app/src/agentmon/env/mcp_docker_recipes.py` (`_daemon_toml` делегирует новому renderer)

**Interfaces:**
- Produces: `render_daemon_toml(alias: str, path: str, port: int | None = None) -> str`, `merge_path(text: str, *, alias: str, path: str, language: str = "bsl") -> str`, `ensure_sections(text: str, port: int) -> str`.
- Consumes: ничего.

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/env/test_code_index_toml.py`:

```python
from agentmon.env.code_index_toml import (ensure_sections, merge_path,
                                          render_daemon_toml)


def test_render_has_one_path_and_sections():
    text = render_daemon_toml("a", "/a", 8005)
    assert text.count("[[paths]]") == 1
    assert 'alias = "a"' in text and 'path = "/a"' in text
    assert "[mcp]" in text and "mass_mode_tools" in text
    assert "http://127.0.0.1:8005" in text


def test_merge_preserves_other_paths_and_sections():
    text = render_daemon_toml("a", "/a", 8005)
    out = merge_path(text, alias="b", path="/b")
    assert out.count("[[paths]]") == 2
    assert 'alias = "a"' in out and 'alias = "b"' in out
    assert "mass_mode_tools" in out
    assert "http://127.0.0.1:8005" in out


def test_merge_updates_existing_alias():
    text = render_daemon_toml("a", "/old", 8005)
    out = merge_path(text, alias="a", path="/new")
    assert out.count('alias = "a"') == 1
    assert 'path = "/new"' in out and 'path = "/old"' not in out


def test_merge_appends_to_text_without_paths():
    out = merge_path("[daemon]\nhttp_port = 0\n", alias="a", path="/a")
    assert out.startswith("[daemon]")
    assert "[[paths]]" in out and 'alias = "a"' in out


def test_merge_escapes_quotes_and_backslashes():
    out = merge_path("", alias='a"b', path="C:\\x")
    assert 'alias = "a\\"b"' in out
    assert 'path = "C:\\\\x"' in out


def test_ensure_sections_adds_missing_and_is_idempotent():
    out = ensure_sections('[[paths]]\nalias = "a"\n', 8005)
    assert "[mcp]" in out and "mass_mode_tools" in out
    assert "[[cache_targets]]" in out
    assert out.count("[[cache_targets]]") == 1
    assert ensure_sections(out, 8005).count("[[cache_targets]]") == 1
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_toml.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Создать `code_index_toml.py`**

```python
"""Минимальная работа с daemon.toml code-index без TOML-зависимостей."""
from __future__ import annotations

import re

_PATH_HEADER = re.compile(r"(?m)^\[\[paths\]\][ \t]*$")
_ALIAS = re.compile(r'(?m)^[ \t]*alias[ \t]*=[ \t]*"((?:[^"\\]|\\.)*)"')
_MCP_HEADER = re.compile(r"(?m)^\[mcp\][ \t]*$")


def _quote(value: str) -> str:
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'


def _unescape(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            out.append({"n": "\n", "t": "\t", "r": "\r",
                        '"': '"', "\\": "\\"}.get(nxt, nxt))
            i += 2
        else:
            out.append(value[i])
            i += 1
    return "".join(out)


def _path_block(alias: str, path: str, language: str) -> str:
    return (f"[[paths]]\npath = {_quote(path)}\n"
            f"alias = {_quote(alias)}\nlanguage = {_quote(language)}\n")


def render_daemon_toml(alias: str, path: str, port: int | None = None) -> str:
    text = ('[daemon]\nhttp_host = "127.0.0.1"\nhttp_port = 0\n'
            'log_level = "info"\n\n')
    if port is not None:
        text += f"[[cache_targets]]\nurl = {_quote(f'http://127.0.0.1:{port}')}\n\n"
    text += '[mcp]\nmass_mode_tools = ["get_object_structure"]\n\n'
    return text + _path_block(alias, path, "bsl")


def merge_path(text: str, *, alias: str, path: str,
               language: str = "bsl") -> str:
    block = _path_block(alias, path, language)
    matches = list(_PATH_HEADER.finditer(text))
    if not matches:
        base = text.rstrip()
        return (base + "\n\n" if base else "") + block
    starts = [m.start() for m in matches]
    preamble = text[:starts[0]]
    segments = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        segments.append(text[start:end])
    found = False
    result = [preamble]
    for segment in segments:
        header_end = _PATH_HEADER.search(segment).end()
        body = segment[header_end:]
        match = _ALIAS.search(body)
        if match and _unescape(match.group(1)) == alias:
            result.append(block)
            found = True
        else:
            result.append(segment)
    if not found:
        if not result[-1].endswith("\n"):
            result.append("\n")
        result.append(block)
    return "".join(result)


def ensure_sections(text: str, port: int) -> str:
    out = text
    if not _MCP_HEADER.search(out):
        out = out.rstrip() + '\n\n[mcp]\nmass_mode_tools = ["get_object_structure"]\n'
    elif "mass_mode_tools" not in out:
        out = _MCP_HEADER.sub(
            '[mcp]\nmass_mode_tools = ["get_object_structure"]', out, count=1)
    cache_url = f"http://127.0.0.1:{port}"
    if cache_url not in out:
        out = out.rstrip() + f"\n\n[[cache_targets]]\nurl = {_quote(cache_url)}\n"
    return out
```

- [ ] **Step 4: Делегировать `mcp_docker_recipes._daemon_toml`**

В `app/src/agentmon/env/mcp_docker_recipes.py`:

```python
from .code_index_toml import render_daemon_toml as _render_daemon_toml
...
def _daemon_toml(alias: str, path: str, cache_target_url: str | None = None) -> str:
    port = None
    if cache_target_url:
        port = int(str(cache_target_url).rsplit(":", 1)[-1])
    return _render_daemon_toml(alias, path, port)
```

Убедиться, что старые тесты `_daemon_toml` (alias/path, отсутствие `/repos/src`, отсутствие `[[cache_targets]]` без URL) проходят.

- [ ] **Step 5: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_code_index_toml.py \
    app/tests/env/test_mcp_docker_recipes.py -q
```
Expected: зелёные.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/code_index_toml.py app/tests/env/test_code_index_toml.py \
        app/src/agentmon/env/mcp_docker_recipes.py
git commit -m "feat(code-index): merge путей daemon.toml без затирания баз"
```

---

### Task 2: Нативный сервис agentmon — `service.json`, multi-base, autostart restart

**Files:**
- Modify: `app/src/agentmon/env/autostart.py`
- Modify: `app/src/agentmon/env/code_index_local.py`
- Modify: `app/tests/env/test_autostart.py`
- Modify: `app/tests/env/test_code_index_local.py`

**Interfaces:**
- Produces:
  - `autostart.stop(name, *, state_dir=None, home=None, run=subprocess.run, platform_name=None) -> list[str]`
  - `autostart.restart(name, *, state_dir=None, home=None, run=subprocess.run, platform_name=None) -> list[str]`
  - `code_index_local.service_id(code_index_dir) -> str`
  - `code_index_local.read_service_port(code_index_dir) -> int | None`
  - `code_index_local.write_service_port(code_index_dir, port) -> None`
  - `code_index_local.deploy_local(*, code_index_dir, catalog_dir, project_name, port, mid=None, download=..., install=..., restart=..., stop=..., run=subprocess.run)` — generator строк.
- Consumes: `code_index_toml.merge_path/ensure_sections/render_daemon_toml`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_autostart.py` добавить:

```python
from agentmon.env import autostart


def _fake_run(calls):
    def run(cmd, **kwargs):
        calls.append(list(cmd))
        from types import SimpleNamespace
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


def test_stop_linux_stops_disables_and_removes_unit(tmp_path):
    calls = []
    autostart.stop("svc", home=tmp_path, platform_name="linux",
                   run=_fake_run(calls))
    assert ["systemctl", "--user", "stop", "svc"] in calls
    assert ["systemctl", "--user", "disable", "svc"] in calls


def test_restart_windows_ends_and_runs(tmp_path):
    calls = []
    autostart.restart("svc", state_dir=tmp_path, platform_name="win32",
                      run=_fake_run(calls))
    assert ["schtasks", "/End", "/TN", "svc"] in calls
    assert ["schtasks", "/Run", "/TN", "svc"] in calls


def test_restart_linux_restarts_unit(tmp_path):
    calls = []
    autostart.restart("svc", home=tmp_path, platform_name="linux",
                      run=_fake_run(calls))
    assert ["systemctl", "--user", "restart", "svc"] in calls
```

В `app/tests/env/test_code_index_local.py` заменить/расширить:

```python
from pathlib import Path
from agentmon.env import code_index_local as L


def _fake_download(code_index_dir, *, log=None, **k):
    if log:
        log("скачал")
    path = Path(code_index_dir) / "bsl-indexer"
    path.write_text("bin", encoding="utf-8")
    return path


def _install(calls):
    def install(name, argv, *, env, state_dir):
        calls.append(("install", name, tuple(argv), dict(env)))
        return [f"install {name}"]
    return install


def test_first_deploy_creates_service_and_starts(tmp_path):
    ci = tmp_path / "ci"
    calls = []
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(calls),
        restart=lambda *a, **k: [], stop=lambda *a, **k: []))
    assert (ci / "service.json").is_file()
    assert L.read_service_port(ci) == 8005
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "a"' in text and 'path = "/code/a"' in text
    names = [c[1] for c in calls if c[0] == "install"]
    assert names == [L.service_names(ci)[0], L.service_names(ci)[1]]
    assert "8005" in "\n".join(log)


def test_second_deploy_adds_base_without_reinstall(tmp_path):
    ci = tmp_path / "ci"
    installs, restarts, reloads = [], [], []
    L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/a", project_name="a",
        port=8005, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: restarts.append(a) or [],
        stop=lambda *a, **k: [])
    log = list(L.deploy_local(
        code_index_dir=str(ci), catalog_dir="/code/b", project_name="b",
        port=9999, download=_fake_download, install=_install(installs),
        restart=lambda *a, **k: restarts.append(a) or [],
        stop=lambda *a, **k: [],
        run=lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "",
                                           "stderr": ""})()))
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert text.count("[[paths]]") == 2
    assert 'alias = "a"' in text and 'alias = "b"' in text
    assert L.read_service_port(ci) == 8005
    assert len(installs) == 2          # только первое развёртывание
    assert restarts and restarts[0][0] == L.service_names(ci)[1]
    assert "8005" in "\n".join(log)
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_autostart.py app/tests/env/test_code_index_local.py -q
```
Expected: FAIL — нет `stop`/`restart`/`service_names`/`read_service_port`.

- [ ] **Step 3: Добавить `stop`/`restart` в `autostart.py`**

```python
def stop(name, *, state_dir=None, home=None, run=subprocess.run,
         platform_name=None):
    home = Path(home) if home is not None else Path.home()
    pf = platform_name or sys.platform
    log = []
    if pf.startswith("win"):
        _run_logged(run, ["schtasks", "/End", "/TN", name], log, check=False)
        _run_logged(run, ["schtasks", "/Delete", "/TN", name, "/F"],
                    log, check=False)
        if state_dir:
            try:
                (Path(state_dir) / f"{name}.cmd").unlink()
            except OSError:
                pass
    elif pf.startswith("linux"):
        _run_logged(run, ["systemctl", "--user", "stop", name], log, check=False)
        _run_logged(run, ["systemctl", "--user", "disable", name],
                    log, check=False)
        unit = Path(home) / ".config" / "systemd" / "user" / f"{name}.service"
        try:
            unit.unlink()
        except OSError:
            pass
        _run_logged(run, ["systemctl", "--user", "daemon-reload"],
                    log, check=False)
    elif pf == "darwin":
        plist = Path(home) / "Library" / "LaunchAgents" / f"{name}.plist"
        _run_logged(run, ["launchctl", "unload", str(plist)],
                    log, check=False)
        try:
            plist.unlink()
        except OSError:
            pass
    else:
        raise ValueError(f"автозапуск не поддержан на платформе {pf}")
    return log


def restart(name, *, state_dir=None, home=None, run=subprocess.run,
            platform_name=None):
    home = Path(home) if home is not None else Path.home()
    pf = platform_name or sys.platform
    log = []
    if pf.startswith("win"):
        _run_logged(run, ["schtasks", "/End", "/TN", name], log, check=False)
        _run_logged(run, ["schtasks", "/Run", "/TN", name], log, check=True)
    elif pf.startswith("linux"):
        res = _run_logged(run, ["systemctl", "--user", "restart", name],
                          log, check=False)
        if getattr(res, "returncode", 1) != 0:
            _run_logged(run, ["systemctl", "--user", "enable", "--now", name],
                        log, check=True)
    elif pf == "darwin":
        plist = Path(home) / "Library" / "LaunchAgents" / f"{name}.plist"
        _run_logged(run, ["launchctl", "unload", str(plist)],
                    log, check=False)
        _run_logged(run, ["launchctl", "load", "-w", str(plist)],
                    log, check=True)
    else:
        raise ValueError(f"автозапуск не поддержан на платформе {pf}")
    return log
```

- [ ] **Step 4: Переписать `code_index_local.py`**

```python
"""Нативное развёртывание code-index: один сервис на code_index_dir."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from . import autostart
from .code_index_release import download_binary as _download
from .code_index_toml import ensure_sections, merge_path, render_daemon_toml

SERVICE_FILE = "service.json"


def service_id(code_index_dir) -> str:
    raw = str(Path(code_index_dir).resolve()).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:8]


def service_names(code_index_dir) -> tuple[str, str]:
    sid = service_id(code_index_dir)
    return (f"ai1c-code-index-daemon-{sid}",
            f"ai1c-code-index-mcp-{sid}")


def read_service_port(code_index_dir) -> int | None:
    try:
        data = json.loads((Path(code_index_dir) / SERVICE_FILE)
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    port = data.get("port")
    return port if isinstance(port, int) and 1 <= port <= 65535 else None


def write_service_port(code_index_dir, port: int) -> None:
    path = Path(code_index_dir) / SERVICE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"port": int(port), "version": 1}) + "\n",
                   encoding="utf-8")
    tmp.replace(path)


def _find_binary(code_index_dir) -> Path | None:
    for name in ("bsl-indexer.exe", "bsl-indexer"):
        for path in Path(code_index_dir).rglob(name):
            if path.is_file():
                return path
    return None


def _reload_daemon(binary, code_index_dir, run) -> str | None:
    env = {**os.environ, "CODE_INDEX_HOME": str(code_index_dir)}
    try:
        res = run([str(binary), "daemon", "reload"], env=env,
                  capture_output=True, text=True)
    except OSError as exc:
        return str(exc)
    if getattr(res, "returncode", 1) != 0:
        return ((getattr(res, "stderr", "") or "")
                + (getattr(res, "stdout", "") or "")).strip()
    return None


def deploy_local(*, code_index_dir, catalog_dir, project_name, port,
                 mid=None, download=_download, install=autostart.install_and_start,
                 restart=autostart.restart, stop=autostart.stop,
                 run=subprocess.run):
    ci = Path(code_index_dir)
    ci.mkdir(parents=True, exist_ok=True)
    existing_port = read_service_port(ci)
    effective_port = existing_port or int(port)
    first = existing_port is None
    yield (f"▶ code-index: {ci} (alias={project_name}, "
           f"порт {effective_port}, {'новый сервис' if first else 'добавление базы'})")

    binary = _find_binary(ci)
    if binary is None:
        buf = []
        binary = download(str(ci), log=buf.append)
        yield from buf
    toml_path = ci / "daemon.toml"
    text = toml_path.read_text(encoding="utf-8") if toml_path.is_file() else ""
    text = merge_path(text, alias=project_name, path=str(catalog_dir))
    text = ensure_sections(text, effective_port)
    toml_path.write_text(text, encoding="utf-8")
    yield f"✓ daemon.toml: alias={project_name}, path={catalog_dir}"

    daemon_name, serve_name = service_names(ci)
    home_env = {"CODE_INDEX_HOME": str(ci)}
    serve_env = {**home_env, "MCP_HTTP_HOST": "127.0.0.1",
                 "MCP_HTTP_PORT": str(effective_port)}
    serve_argv = [str(binary), "serve", "--transport", "http",
                  "--host", "127.0.0.1", "--port", str(effective_port),
                  "--config", str(toml_path)]

    if first:
        yield from install(daemon_name, [str(binary), "daemon", "run"],
                           env=home_env, state_dir=str(ci))
        yield from install(serve_name, serve_argv, env=serve_env,
                           state_dir=str(ci))
        write_service_port(ci, effective_port)
        if mid is not None:
            for legacy in (f"ai1c-code-index-daemon-{mid}",
                           f"ai1c-code-index-mcp-{mid}"):
                try:
                    yield from stop(legacy, state_dir=str(ci))
                except Exception as exc:                       # noqa: BLE001
                    yield f"⚠ legacy {legacy}: {exc}"
    else:
        error = _reload_daemon(binary, ci, run)
        if error:
            yield f"⚠ daemon reload: {error}"
        else:
            yield "✓ daemon reload"
        yield from restart(serve_name, state_dir=str(ci))

    yield (f"✓ code-index готов: {ci}, alias={project_name}, "
           f"порт {effective_port}")
```

- [ ] **Step 5: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_autostart.py app/tests/env/test_code_index_local.py -q
```
Expected: зелёные.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/autostart.py app/src/agentmon/env/code_index_local.py \
        app/tests/env/test_autostart.py app/tests/env/test_code_index_local.py
git commit -m "feat(code-index): общий нативный сервис с несколькими базами"
```

---

### Task 3: Один нативный вид в agentmon UI/API

**Files:**
- Modify: `app/src/agentmon/env/mcp_types.py`
- Modify: `app/src/agentmon/env/mcp_api.py`
- Modify: `app/web/mcp.js`
- Modify: `app/tests/env/test_mcp_types.py`
- Modify: `app/tests/env/test_mcp_api.py`

**Interfaces:**
- Consumes: `code_index_local.read_service_port`, `deploy_local`.
- Produces: `types_payload` без скрытых видов; `_resolve_local` для `code-index` и `code-index-local`; миграция `kind=local`.

- [ ] **Step 1: Написать падающие тесты**

В `test_mcp_types.py`:

```python
def test_code_index_is_one_native_type():
    from agentmon.env.mcp_types import get_type, types_payload
    t = get_type("code-index")
    assert t.action == "local"
    assert "code_index_dir" in t.fields
    assert "code_index_dir" in t.required
    assert "port" in t.required
    assert "code-index-local" not in {x["key"] for x in types_payload()}
    legacy = get_type("code-index-local")
    assert legacy.hidden is True
```

В `test_mcp_api.py`:

```python
def test_deploy_local_accepts_code_index_and_migrates_kind(tmp_path, monkeypatch):
    from agentmon.env import code_index_local
    seen = {}
    monkeypatch.setattr(
        code_index_local, "deploy_local",
        lambda **kw: seen.update(kw) or iter(["ok"]))
    c = make(tmp_path)
    ci = tmp_path / "ci"; ci.mkdir()
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8005, "catalog_dir": "/code/cfg", "project_name": "proj",
        "code_index_dir": str(ci),
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/deploy-local/stream", json={})
    assert r.status_code == 200 and "ok" in r.text
    row = c.get("/api/mcp").json()["mcp"]
    row = next(item for item in row if item["id"] == mid)
    assert row["kind"] == "local"
    assert seen["port"] == 8005


def test_deploy_local_reuses_service_port(tmp_path, monkeypatch):
    from agentmon.env import code_index_local
    seen = {}
    monkeypatch.setattr(
        code_index_local, "deploy_local",
        lambda **kw: seen.update(kw) or iter(["ok"]))
    c = make(tmp_path)
    ci = tmp_path / "ci"; ci.mkdir()
    code_index_local.write_service_port(ci, 8010)
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "local", "standard_key": "code-index",
        "port": 8005, "catalog_dir": "/code/cfg", "project_name": "proj",
        "code_index_dir": str(ci),
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/deploy-local/stream", json={})
    assert r.status_code == 200
    assert seen["port"] == 8010
    row = next(item for item in c.get("/api/mcp").json()["mcp"]
               if item["id"] == mid)
    assert row["port"] == 8010
    assert "8010" in row["connection_json"]


def test_launch_docker_rejects_code_index(tmp_path):
    c = make(tmp_path)
    mid = c.post("/api/mcp", json={
        "name": "idx", "kind": "docker", "standard_key": "code-index",
        "port": 8004, "catalog_dir": "/code/cfg", "project_name": "proj",
    }).json()["mcp"]["id"]
    r = c.post(f"/api/mcp/{mid}/launch", json={})
    assert r.status_code == 400
    assert "натив" in r.json()["detail"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_mcp_types.py app/tests/env/test_mcp_api.py -q -k "code_index or deploy_local or native"`
Expected: FAIL.

- [ ] **Step 3: Обновить `mcp_types.py`**

- В `McpType` добавить `hidden: bool = False`.
- Для `code-index`:
  - title `"Индексированная кодовая база (нативно)"`;
  - fields `("name", "mcp_name", "purpose", "url", "port", "catalog_dir", "project_name", "code_index_dir", "connection")`;
  - defaults port `8005`;
  - `action="local"`;
  - `required=("catalog_dir", "project_name", "code_index_dir", "port")`.
- Для `code-index-local`:
  - `hidden=True`, title `"Индексированная кодовая база (локально, legacy)"`;
  - остальные поля/action/required как у code-index.
- `types_payload()`: `for t in MCP_TYPES if not t.hidden`.

- [ ] **Step 4: Обновить `mcp_api.py`**

В `_resolve_docker` в начале после получения `row`:

```python
        if row.get("standard_key") == "code-index":
            raise HTTPException(
                status_code=400,
                detail="code-index разворачивается нативно; используйте "
                       "/deploy-local")
```

В `_resolve_local`:

```python
        if row.get("standard_key") not in ("code-index", "code-index-local"):
            raise HTTPException(status_code=400,
                                detail="это не code-index")
        missing = [k for k in ("catalog_dir", "project_name",
                               "code_index_dir") if not row.get(k)]
        if missing:
            raise HTTPException(status_code=400,
                                detail=f"не заданы поля: {', '.join(missing)}")
        port = code_index_local.read_service_port(row["code_index_dir"])
        if port is None:
            port = row.get("port")
        if not port:
            raise HTTPException(status_code=400,
                                detail="не задан порт и нет service.json")
        updates = {"kind": "local"}
        if int(row.get("port") or 0) != int(port):
            from .mcp_types import build_connection
            updates["port"] = int(port)
            updates["connection_json"] = build_connection(
                "code-index", mcp_name=row.get("mcp_name") or "code_index",
                url=row.get("url") or "localhost", port=int(port))
        repo.update(mid, **updates)
        return {
            "mid": mid,
            "code_index_dir": row["code_index_dir"],
            "catalog_dir": row["catalog_dir"],
            "project_name": row["project_name"],
            "port": int(port),
        }
```

- [ ] **Step 5: Обновить `mcp.js`**

- `renderTypeFields`: для `action === "local"` текст кнопки `Развернуть`.
- В `showMcpCard`:
  ```js
  const isDocker = type ? type.action === "docker" : mcp.kind === "docker";
  const isLocal = type ? type.action === "local" : mcp.kind === "local";
  ```
- Текст кнопки локальной карточки — `Развернуть`.
- Обновить комментарии, где написано «Развернуть локально»/«Docker».

- [ ] **Step 6: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_mcp_types.py \
    app/tests/env/test_mcp_api.py app/tests/env/test_mcp_catalog.py \
    app/tests/env/test_mcp_catalog_from_connection.py -q
```
Expected: зелёные.

- [ ] **Step 7: Коммит**

```bash
git add app/src/agentmon/env/mcp_types.py app/src/agentmon/env/mcp_api.py \
        app/web/mcp.js app/tests/env/test_mcp_types.py app/tests/env/test_mcp_api.py
git commit -m "feat(agentmon): один нативный вид code-index с кнопкой Развернуть"
```

---

### Task 4: `code_index_bench.py` — нативные процессы benchmark

**Files:**
- Create: `app/src/agentmon/env/code_index_bench.py`
- Create: `app/tests/env/test_code_index_bench.py`
- Modify: `app/src/agentmon/env/code_index_release.py` (публичный `existing_binary`)

**Interfaces:**
- Produces:
  - `existing_binary(code_index_dir) -> Path | None`
  - `NativeIndex(code_index_dir: Path, binary: Path, daemon_pid: int, serve_pid: int)`
  - `stop_code_index(code_index_dir, *, run=subprocess.run, kill=os.kill, sleep=time.sleep, log=print) -> None`
  - `clean_code_index(code_index_dir, catalog_dir, *, run=subprocess.run, log=print) -> None`
  - `start_code_index(*, code_index_dir, catalog_dir, alias, port, host="127.0.0.1", download=..., popen=subprocess.Popen, run=subprocess.run, log=print) -> NativeIndex`
  - `wait_code_index_ready(index, *, wait_minutes, host, port, run=subprocess.run, sleep=time.sleep, clock=time.monotonic, tcp_ok=default_tcp_ok, log=print) -> None`
- Consumes: `code_index_toml.render_daemon_toml`, `code_index_release.download_binary`.

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/env/test_code_index_bench.py` (ключевые кейсы):

```python
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentmon.env import code_index_bench as B


def test_clean_removes_dirs_and_legacy_container(tmp_path):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 0, "serve": 0}')
    catalog = tmp_path / "catalog"; (catalog / ".code-index").mkdir(parents=True)
    calls = []
    B.clean_code_index(ci, catalog, run=lambda cmd, **k: calls.append(cmd),
                       log=lambda _m: None)
    assert not ci.exists()
    assert not (catalog / ".code-index").exists()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


def test_start_writes_pid_and_toml(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    def fake_download(dest, *, log=None):
        Path(dest).mkdir(parents=True, exist_ok=True)
        bin_path.write_text("bin", encoding="utf-8")
        return bin_path
    pids = iter([111, 222])
    class Proc:
        def __init__(self):
            self.pid = next(pids)
    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    index = B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=fake_download, popen=lambda *a, **k: Proc(),
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""))
    assert index.daemon_pid == 111 and index.serve_pid == 222
    assert (ci / "benchmark-pids.json").is_file()
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "a"' in text and str(catalog.resolve()) in text


def test_stop_kills_own_pids(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    killed, calls = [], []
    checks = {"n": 0}

    def ours(pid, run):
        checks["n"] += 1
        return checks["n"] <= 2          # живы только до SIGTERM

    monkeypatch.setattr(B, "_is_our_process", ours)
    B.stop_code_index(ci, run=lambda cmd, **k: calls.append(cmd),
                      kill=lambda pid, sig: killed.append(pid),
                      sleep=lambda _s: None, clock=lambda: 0.0,
                      log=lambda _m: None)
    assert killed == [10, 11]
    assert not (ci / "benchmark-pids.json").exists()
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_bench.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Реализовать `code_index_release.existing_binary`**

```python
def existing_binary(code_index_dir):
    """Найти уже скачанный bsl-indexer в каталоге (без сети)."""
    from pathlib import Path as _Path
    for name in ("bsl-indexer.exe", "bsl-indexer"):
        for path in _Path(code_index_dir).rglob(name):
            if path.is_file():
                return path
    return None
```

- [ ] **Step 4: Создать `code_index_bench.py`**

```python
"""Нативный code-index для benchmark: detached daemon/serve + PID-файл."""
from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .code_index_release import download_binary
from .code_index_toml import render_daemon_toml
from .net_probe import default_tcp_ok

PID_FILE = "benchmark-pids.json"
LEGACY_CONTAINER = "ai1c-mcp-code_index"


@dataclass(frozen=True)
class NativeIndex:
    code_index_dir: Path
    binary: Path
    daemon_pid: int
    serve_pid: int


def _pid_path(code_index_dir) -> Path:
    return Path(code_index_dir) / PID_FILE


def _read_pids(code_index_dir) -> list[int]:
    try:
        data = json.loads(_pid_path(code_index_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [int(v) for v in (data.get("daemon"), data.get("serve"))
            if isinstance(v, int)]


def _write_pids(code_index_dir, daemon: int, serve: int) -> None:
    path = _pid_path(code_index_dir)
    path.write_text(json.dumps({"daemon": int(daemon),
                                "serve": int(serve)}) + "\n",
                    encoding="utf-8")


def _is_our_process(pid: int, run=subprocess.run) -> bool:
    if os.name == "nt":
        try:
            res = run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                      capture_output=True, text=True)
        except OSError:
            return False
        return "bsl-indexer" in (getattr(res, "stdout", "") or "").lower()
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return False
    return "bsl-indexer" in raw.decode("utf-8", "replace")


def _spawn_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS}
    return {"start_new_session": True}


def stop_code_index(code_index_dir, *, run=subprocess.run, kill=os.kill,
                    sleep=time.sleep, clock=time.monotonic, log=print) -> None:
    pids = [pid for pid in _read_pids(code_index_dir)
            if _is_our_process(pid, run)]
    for pid in pids:
        if os.name == "nt":
            try:
                run(["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, text=True)
            except OSError:
                pass
        else:
            try:
                kill(pid, signal.SIGTERM)
            except OSError:
                pass
    deadline = clock() + 10
    alive = list(pids)
    while alive and clock() < deadline:
        alive = [pid for pid in alive if _is_our_process(pid, run)]
        if alive:
            sleep(0.2)
    if os.name != "nt":
        for pid in alive:
            try:
                kill(pid, signal.SIGKILL)
            except OSError:
                pass
    try:
        _pid_path(code_index_dir).unlink()
    except OSError:
        pass


def clean_code_index(code_index_dir, catalog_dir, *, run=subprocess.run,
                     log=print) -> None:
    stop_code_index(code_index_dir, run=run, log=log)
    if Path(code_index_dir).exists():
        shutil.rmtree(code_index_dir, ignore_errors=False)
    index_dir = Path(catalog_dir) / ".code-index"
    if index_dir.exists():
        shutil.rmtree(index_dir, ignore_errors=False)
    if shutil.which("docker"):
        try:
            run(["docker", "rm", "-f", LEGACY_CONTAINER],
                capture_output=True, text=True)
            log(f"✓ legacy Docker-контейнер {LEGACY_CONTAINER} удалён "
                "(если был)")
        except OSError:
            pass


def start_code_index(*, code_index_dir, catalog_dir, alias, port,
                     host="127.0.0.1", download=download_binary,
                     popen=subprocess.Popen, run=subprocess.run,
                     log=print) -> NativeIndex:
    clean_code_index(code_index_dir, catalog_dir, run=run, log=log)
    ci = Path(code_index_dir)
    ci.mkdir(parents=True, exist_ok=True)
    binary = download(str(ci), log=log)
    toml_path = ci / "daemon.toml"
    toml_path.write_text(
        render_daemon_toml(alias, str(Path(catalog_dir).resolve()), int(port)),
        encoding="utf-8")
    env = {**os.environ, "CODE_INDEX_HOME": str(ci)}
    with (ci / "daemon.log").open("ab") as daemon_log:
        daemon = popen([str(binary), "daemon", "run"], cwd=str(ci),
                       env=env, stdout=daemon_log, stderr=subprocess.STDOUT,
                       **_spawn_kwargs())
    serve_env = {**env, "MCP_HTTP_HOST": host, "MCP_HTTP_PORT": str(port)}
    with (ci / "serve.log").open("ab") as serve_log:
        serve = popen([str(binary), "serve", "--transport", "http",
                       "--host", host, "--port", str(port),
                       "--config", str(toml_path)],
                      cwd=str(ci), env=serve_env, stdout=serve_log,
                      stderr=subprocess.STDOUT, **_spawn_kwargs())
    _write_pids(ci, daemon.pid, serve.pid)
    log(f"✓ code-index запущен: daemon pid={daemon.pid}, "
        f"serve pid={serve.pid}, порт {port}")
    return NativeIndex(ci, Path(binary), daemon.pid, serve.pid)


def _daemon_status(index: NativeIndex, run=subprocess.run):
    env = {**os.environ, "CODE_INDEX_HOME": str(index.code_index_dir)}
    try:
        res = run([str(index.binary), "daemon", "status", "--json"],
                  env=env, capture_output=True, text=True)
    except OSError:
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def wait_code_index_ready(index: NativeIndex, *, wait_minutes: int, host: str,
                          port: int, run=subprocess.run, sleep=time.sleep,
                          clock=time.monotonic, tcp_ok=default_tcp_ok,
                          log=print) -> None:
    from .bench_setup import SetupError
    deadline = clock() + wait_minutes * 60
    while True:
        data = _daemon_status(index, run)
        paths = (data or {}).get("paths") or []
        ready = bool(paths) and all(p.get("status") == "ready"
                                    for p in paths)
        if ready and tcp_ok(f"http://{host}:{port}"):
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if not _is_our_process(index.daemon_pid, run) or \
                not _is_our_process(index.serve_pid, run):
            raise SetupError("native code-index завершился; смотрите "
                             f"{index.code_index_dir}/daemon.log и serve.log")
        if clock() >= deadline:
            raise SetupError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {index.code_index_dir}/daemon.log")
        sleep(5)
```

- [ ] **Step 5: Вынести `default_tcp_ok` в `net_probe.py`**

Создать `app/src/agentmon/env/net_probe.py`:

```python
"""TCP/HTTP-пробы без зависимостей от bench_setup."""
import socket
import urllib.error
import urllib.request
from urllib.parse import urlparse


def url_host_port(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise ValueError(f"некорректный порт в URL: {url}")
    return parsed.hostname or "", port


def default_tcp_ok(url: str, timeout: float = 3.0) -> bool:
    host, port = url_host_port(url)
    if not host:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def default_http_ok(url: str, timeout: float = 5.0) -> bool:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ai1c-agentmon"})
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True
    except OSError:
        return False
```

В `bench_setup.py` заменить локальные `_url_host_port`, `default_tcp_ok`,
`default_http_ok` на импорт/реэкспорт из `net_probe`:

```python
from .net_probe import default_http_ok, default_tcp_ok, url_host_port
```

`_url_host_port` можно оставить как алиас `url_host_port` для существующих
тестов, либо обновить тесты на новое имя.

- [ ] **Step 6: Запустить тесты**

Run: `.venv/bin/python -m pytest app/tests/env/test_code_index_bench.py app/tests/env/test_bench_setup.py -q`
Expected: зелёные.

- [ ] **Step 7: Коммит**

```bash
git add app/src/agentmon/env/code_index_bench.py app/src/agentmon/env/net_probe.py \
        app/src/agentmon/env/code_index_release.py app/src/agentmon/env/bench_setup.py \
        app/tests/env/test_code_index_bench.py
git commit -m "feat(bench): нативный code-index с detached daemon/serve и PID"
```

---

### Task 5: Benchmark setup на нативный code-index; удалить `bench_index`

**Files:**
- Modify: `app/src/agentmon/env/bench_setup.py`
- Modify: `app/src/agentmon/env/code_index_bench.py` (если нужно для интеграции)
- Modify: `app/tests/env/test_bench_setup.py`
- Modify: `benchmark/setup_benchmark.py`
- Modify: `benchmark/example.test.env`
- Modify: `benchmark/bench_run.py`
- Modify: `benchmark/bench_metrics.py`
- Delete: `benchmark/bench_index.py`, `benchmark/tests/test_bench_index.py`
- Modify: `benchmark/tests/test_bench_run.py`, `benchmark/tests/test_bench_metrics.py`, `benchmark/tests/test_bench_e2e.py`
- Modify: `benchmark/README.md`
- Modify: `template/.claude/skills/mcp-usage/SKILL.md`

**Interfaces:**
- Consumes: `code_index_bench.clean_code_index/start_code_index/wait_code_index_ready/stop_code_index`; `code_index_local.read_service_port`.
- Produces: `BenchConfig.code_index_dir`; `McpPlan.code_index_dir`; `SetupResult.code_index`.

- [ ] **Step 1: Написать падающие тесты**

В `test_bench_setup.py`:
- В `write_env`/конфиг добавить `CODE_INDEX_DIR=<tmp>/ci`.
- `test_load_config_code_index_dir_default` / required:
  ```python
  def test_code_index_dir_required(tmp_path):
      env = write_env(tmp_path)
      text = env.read_text(encoding="utf-8").replace(
          f"CODE_INDEX_DIR={tmp_path / 'ci'}\n", "")
      env.write_text(text, encoding="utf-8")
      with pytest.raises(SetupError, match="CODE_INDEX_DIR"):
          load_config(env, repo_root=tmp_path)
  ```
- `test_code_index_dir_must_be_outside_project`:
  ```python
  def test_code_index_dir_must_be_outside_project(tmp_path):
      project = tmp_path / "project"
      env = write_env(tmp_path, code_index_dir=project / "ci")
      with pytest.raises(SetupError, match="внутри"):
          load_config(env, repo_root=tmp_path)
  ```
- Планы: `code_index.kind == "local"`, `code_index.code_index_dir == str(cfg.code_index_dir)`.
- `test_run_setup_uses_native_index` (заменяет Docker-fake happy path):
  ```python
  def test_run_setup_uses_native_index(tmp_path):
      root = make_repo_root(tmp_path)
      make_tasks(root)
      cfg = load_config(write_env(tmp_path), repo_root=root)
      store, registry = make_store(tmp_path), make_registry(tmp_path)
      launched, waited = [], []
      from types import SimpleNamespace

      def launch(**kwargs):
          launched.append(kwargs)
          return SimpleNamespace(code_index_dir=cfg.code_index_dir)

      def wait(index, **kwargs):
          waited.append((index, kwargs))

      result = run_setup(
          cfg, repo_root=root, store=store, registry=registry,
          prov=OrchestratorProv(), tcp_ok=lambda url: True,
          http_ok=lambda url: True, install_env=fake_install_env,
          batch_run=lambda project_dir, args, **kwargs: None,
          launch_index=launch, wait_index=wait, log=lambda line: None,
      )
      assert launched[0]["code_index_dir"] == cfg.code_index_dir
      assert launched[0]["catalog_dir"].endswith(
          str(Path("src") / "cf"))
      assert launched[0]["alias"] == cfg.project_name
      assert launched[0]["port"] == cfg.code_index_port
      assert waited[0][0].code_index_dir == cfg.code_index_dir
      assert result.code_index == cfg.code_index_dir
  ```
- В `write_env` добавить `CODE_INDEX_DIR={tmp_path / 'ci'}`; в
  `test_load_config` проверить `cfg.code_index_dir`.
- Удалить Docker-тесты `test_launch_code_index_*`, `test_wait_code_index_ready_*`, rollback `docker rm` assertions; заменить на `stop_code_index`/native cleanup assertions.

В `benchmark/tests/test_bench_run.py` удалить:
```python
    assert opts.index_refresh is True
    ...
    assert parse_args(["--no-index-refresh"]).index_refresh is False
```
В `test_bench_metrics.py` удалить `test_render_digest_shows_index_refresh_only_when_present`.
В `test_bench_e2e.py` удалить:
```python
    assert [task["index_refresh"] for task in metrics["tasks"]] == ["fresh", "fresh"]
```
Удалить `benchmark/tests/test_bench_index.py` и `benchmark/bench_index.py`.

- [ ] **Step 2: Убедиться, что тесты падают**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_bench_setup.py benchmark/tests/test_bench_run.py -q
```
Expected: FAIL — нет `code_index_dir`, старые импорты.

- [ ] **Step 3: Обновить `BenchConfig`/`load_config`**

- `REQUIRED_KEYS` += `"CODE_INDEX_DIR"`.
- `BenchConfig` += `code_index_dir: str`.
- В `load_config` после `project_dir`:
  ```python
  code_index_raw = (data.get("CODE_INDEX_DIR") or "").strip()
  if not code_index_raw:
      raise SetupError("не задан CODE_INDEX_DIR")
  code_index_dir = Path(os.path.expanduser(code_index_raw))
  if not code_index_dir.is_absolute():
      raise SetupError("CODE_INDEX_DIR должен быть абсолютным путём")
  if code_index_dir == project_dir or project_dir in code_index_dir.parents:
      raise SetupError("CODE_INDEX_DIR не должен находиться внутри "
                       "BENCH_PROJECT_DIR")
  ```
  Передать `code_index_dir=str(code_index_dir.resolve())`.
- `example.test.env`:
  ```ini
  # Каталог нативного code-index (бинарь, daemon.toml, PID, логи).
  # При каждом setup удаляется и создаётся заново — не указывайте общий
  # каталог другого сервиса.
  CODE_INDEX_DIR=/home/uam/projects/bench-code-index
  ```
  Для Windows пример в комментарии `D:\projects\bench-code-index`.

- [ ] **Step 4: `McpPlan`/планы/конфиг**

- `McpPlan` += `code_index_dir: str | None = None`.
- `build_mcp_plans` code-index:
  ```python
  McpPlan(standard_key="code-index", mcp_name="code_index", kind="local",
          connection_json=_connection_http("code_index", f"http://{host}:{port}/mcp"),
          purpose=..., url=host, port=port,
          catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
          project_name=cfg.project_name,
          code_index_dir=cfg.code_index_dir)
  ```
- `resolve_mcp_cards`: для `standard_key in ("code-index", "code-index-local")`
  сравнить и `code_index_dir`.
- `build_env_config` передать `code_index_dir=plan.code_index_dir`.

- [ ] **Step 5: `run_setup` на нативный launch**

- Импортировать `start_code_index`, `wait_code_index_ready`, `stop_code_index`,
  `clean_code_index`.
- `RollbackState.container` → `code_index: code_index_bench.NativeIndex | None`.
- `rollback`: если `state.code_index`, вызвать
  `stop_code_index(state.code_index.code_index_dir, run=run, log=log)`.
- `run_setup` сигнатура:
  ```python
  def run_setup(..., launch_index=start_code_index,
                wait_index=wait_code_index_ready, ...)
  ```
- Внутри:
  ```python
  log("▶ code_index (native)")
  code_index = launch_index(
      code_index_dir=cfg.code_index_dir,
      catalog_dir=str(Path(cfg.project_dir) / "src" / "cf"),
      alias=cfg.project_name, port=cfg.code_index_port,
      host=cfg.code_index_host, run=run, log=log)
  state.code_index = code_index
  ...
  wait_index(code_index, wait_minutes=cfg.code_index_wait_minutes,
             host=cfg.code_index_host, port=cfg.code_index_port,
             run=run, sleep=sleep, clock=clock, log=log)
  ```
  Удалить `log("▶ ожидание индексации code_index")`? Оставить перед wait.
- `SetupResult.container` → `code_index: str`; вернуть
  `str(code_index.code_index_dir)`.
- `setup_benchmark.py`: `print(f"  code_index:  {result.code_index} (native)")`.
- Удалить Docker-функции/константы/импорты из `bench_setup.py`:
  `CODE_INDEX_CONTAINER`, `_build_code_index_image`, `launch_code_index`,
  `_daemon_status`, `CODE_INDEX_DAEMON_JSON`, `_container_running`,
  `wait_code_index_ready`, `mcp_sources`, `recipe_for`, `launch_params`,
  `container_name` (если больше не нужны). Проверить импорты.

- [ ] **Step 6: Удалить `bench_index`**

- Удалить `benchmark/bench_index.py`, `benchmark/tests/test_bench_index.py`.
- `bench_run.py`: убрать импорт, поле `index_refresh`, `--no-index-refresh`,
  `index_refresh=...`, вызов `refresh_index`, `task_metrics["index_refresh"]`,
  лог.
- `bench_metrics.py`: убрать блок
  `index_status = task.get("index_refresh")` и строку дайджеста.
- Удалить/поправить тесты (см. шаг 1).
- `benchmark/README.md`: убрать «пересоздаст контейнер», описать
  `CODE_INDEX_DIR`, нативный запуск, очистку.
- `template/.claude/skills/mcp-usage/SKILL.md`: заменить
  «The benchmark runner refreshes the index between tasks.» на
  «Нативное развёртывание обновляет индекс в секунды; при сомнении используй
  native fallback».

- [ ] **Step 7: Запустить тесты**

Run:
```bash
.venv/bin/python -m pytest app/tests/env/test_bench_setup.py \
    app/tests/env/test_code_index_bench.py benchmark/tests -q
```
Expected: зелёные.

- [ ] **Step 8: Коммит**

```bash
git add -A app/src/agentmon/env/bench_setup.py app/src/agentmon/env/code_index_bench.py \
        app/tests/env/test_bench_setup.py benchmark/setup_benchmark.py \
        benchmark/example.test.env benchmark/bench_run.py benchmark/bench_metrics.py \
        benchmark/tests benchmark/README.md \
        template/.claude/skills/mcp-usage/SKILL.md
git rm benchmark/bench_index.py benchmark/tests/test_bench_index.py
git commit -m "feat(bench): нативный code-index из CODE_INDEX_DIR, без рестартов"
```

---

### Task 6: Удалить Docker-рецепт code-index, обновить документацию

**Files:**
- Modify: `app/src/agentmon/env/mcp_docker_recipes.py`
- Modify: `app/src/agentmon/env/code_index_local.py` (если ещё импортирует `_daemon_toml`)
- Modify: `app/tests/env/test_mcp_docker_recipes.py`
- Modify: `app/tests/env/test_mcp_api.py`
- Modify: `docs/mcp/code-index.md`, `docs/mcp/code-index-common.md`,
  `docs/mcp/code-index-local.md`
- Modify: `README.md`, `benchmark/README.md`
- Modify: `docs/superpowers/specs/2026-11-21-benchmark-environment-fixes-design.md`
- Modify: `docs/superpowers/plans/2026-11-21-benchmark-environment-fixes.md`

**Interfaces:**
- Docker-рецепт code-index удалён; code-index в `_resolve_docker` отдаёт 400.
- Документация описывает один нативный вид и мульти-базу.

- [ ] **Step 1: Обновить тесты**

- `test_mcp_docker_recipes.py`: удалить `test_code_index_requires_catalog_dir`,
  `test_code_index_requires_project_name`, тесты `_daemon_toml` с code-index
  (или перенести их в `test_code_index_toml.py`, если ещё не там).
- `test_mcp_api.py`: `test_launch_code_index_uses_recipe` заменить на
  проверку 400 (из Task 3) — если уже сделано, удалить дубль.
- Убедиться, что `RECIPES` не содержит `code-index`:
  ```python
  assert "code-index" not in R.RECIPES
  ```

- [ ] **Step 2: Удалить рецепт и мёртвый код**

В `mcp_docker_recipes.py`:
- удалить `"code-index"` из `RECIPES`;
- удалить `_daemon_toml`, если он больше нигде не используется;
- убрать импорт `code_index_toml`, если он был только для `_daemon_toml`.
Проверить `grep -rn "_daemon_toml\|launch_params(\"code-index\"" app benchmark`
— не должно остаться.

- [ ] **Step 3: Обновить документацию**

- `docs/mcp/code-index.md`: в начало добавить:
  ```markdown
  > **Legacy.** Docker-развёртывание code-index больше не поддерживается
  > agentmon: на Windows bind-mount не даёт inotify-событий, индекс не
  > обновляется. Используйте нативный вид — см. `code-index-local.md`.
  ```
- `docs/mcp/code-index-common.md`: добавить раздел «Один сервис — несколько
  баз»: `code_index_dir`, `service.json`, `merge_path`, `daemon reload`,
  перезапуск serve; Docker-вариант назвать legacy.
- `docs/mcp/code-index-local.md`: обновить подпись «при развёртывании из UI»,
  добавить пример `daemon.toml` с двумя `[[paths]]`, сервисный порт из
  `service.json`.
- `README.md`: раздел «Индексированная кодовая база» — нативный вид; убрать
  Docker/host-network упоминания для code-index.
- `benchmark/README.md`: `CODE_INDEX_DIR`, нативный setup, очистка,
  отсутствие Docker-контейнера.
- Старая спека/план: в начало каждого файла добавить:
  ```markdown
  > **Superseded (2026-11-21):** обход с перезапуском контейнера
  > (`bench_index.py`) удалён — code-index переведён на нативный запуск,
  > см. `docs/superpowers/specs/2026-11-21-native-code-index-design.md`.
  ```

- [ ] **Step 4: Полные тесты**

Run:
```bash
.venv/bin/python -m pytest benchmark/tests -q
.venv/bin/python -m pytest app/tests/env -q
```
Expected: зелёные.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/mcp_docker_recipes.py \
        app/tests/env/test_mcp_docker_recipes.py app/tests/env/test_mcp_api.py \
        docs/mcp README.md benchmark/README.md \
        docs/superpowers/specs/2026-11-21-benchmark-environment-fixes-design.md \
        docs/superpowers/plans/2026-11-21-benchmark-environment-fixes.md
git commit -m "docs(code-index): нативный вид, Docker — legacy; удалён рецепт"
```

---

## Финальная проверка (оркестратор)

- [ ] `git status --short` — чисто; все коммиты в `main`, push не выполнялся.
- [ ] Полные suites: `.venv/bin/python -m pytest benchmark/tests -q` и
  `.venv/bin/python -m pytest app/tests/env -q`.
- [ ] `grep -rn "bench_index\|index_refresh\|no-index-refresh" benchmark app template`
  — пусто (кроме архивных docs с пометкой Superseded).
- [ ] `grep -rn "Развернуть в Docker" app/web/mcp.js` — остаётся только для
  не-code-index видов; для code-index в форме/карточке нет.
- [ ] Сверить спеку по каждому критерию приёмки.

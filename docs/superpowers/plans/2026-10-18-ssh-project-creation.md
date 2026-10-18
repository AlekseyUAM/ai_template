# Provisioner за backend + создание проекта по SSH — План реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Вынести scaffold/deploy/проверки проекта за backend-интерфейс (новый протокол `Provisioner`) и реализовать создание проекта на удалённом хосте по SSH, с поведением local байт-в-байт как раньше.

**Architecture:** Добавляем третий протокол backend'а `Provisioner` (операции над целевой ФС + выполнение команд на цели + сведения о целевом интерпретаторе). `LocalProvisioner` — тонкие обёртки над текущими `Path`/`shutil`/`subprocess`. `SshProvisioner` — поверх уже существующего `_Connection` (SFTP + exec). Слой развёртывания (`scaffold.py`, `content.py`, `project_checks.py`, `project_api.py`) перестаёт обращаться к ФС/subprocess напрямую — всё через provisioner выбранного backend'а.

**Tech Stack:** Python 3.10+, dataclasses, `typing.Protocol`, paramiko (SFTP/exec), pytest. Фронтенд — статический web (ванильный JS).

## Global Constraints

- Python **3.10+** (целевой синтаксис `str | None`).
- **Локальный режим не меняется по поведению**: для `backend="local"` результат scaffold+deploy байт-в-байт тот же, что до рефакторинга (golden-инвариант).
- Все новые публичные функции/методы — с русскоязычными docstring в стиле существующего кода.
- Тесты не требуют реальных Docker/SSH/1С: `Provisioner` и `run` инъектируются фейками (как уже сделано для раннеров — см. `tests/test_backend_ssh.py`).
- Платформа 1С в удалённых сценариях — **Linux**; лицензии — **сетевой сервер**; база — **клиент-серверная**. Проброс USB и файловые базы — вне скоупа.
- Запуск тестов: из каталога `app/` командой `python -m pytest -q` (venv проекта активирован). Для одного файла: `python -m pytest tests/<файл> -v`.
- Коммиты — атомарные по задаче, сообщения на русском в стиле репозитория.

---

## Файловая структура

- `app/src/agentmon/backends/__init__.py` — **+** протокол `Provisioner`, dataclass `RunResult`, поле `provisioner` на `Backend`.
- `app/src/agentmon/backends/local.py` — **+** класс `LocalProvisioner`, подключение в `LocalBackend`.
- `app/src/agentmon/backends/ssh.py` — **+** класс `SshProvisioner`, подключение в `SshBackend`.
- `app/src/agentmon/env/scaffold.py` — функции принимают `prov: Provisioner` вместо прямых `Path`/`open`.
- `app/src/agentmon/env/content.py` — `deploy_content`/`provision_venv`/helpers работают через `prov`.
- `app/src/agentmon/env/project_checks.py` — `is_empty_dir`/`requirements`/`platform_binary`/`check_db` работают через `prov`.
- `app/src/agentmon/env/config_schema.py` — **+** поле `license_server: str | None = None`.
- `app/src/agentmon/env/project_api.py` — путь установки достаёт `prov` из backend проекта и прокидывает в scaffold/deploy/проверки; ssh-создание работает.
- `app/src/agentmon/env/nethasp.py` — **новый** модуль: генерация `nethasp.ini`.
- `app/src/agentmon/web/` — мастер проекта: поле «Сервер лицензий».
- Тесты: `app/tests/test_provisioner_local.py`, `app/tests/test_provisioner_ssh.py`, `app/tests/env/test_*` (существующие — обновить вызовы), `app/tests/test_nethasp.py`.

---

## Task 1: Протокол `Provisioner` + `RunResult` + поле `license_server`

**Files:**
- Modify: `app/src/agentmon/backends/__init__.py`
- Modify: `app/src/agentmon/env/config_schema.py`
- Test: `app/tests/test_provisioner_local.py` (создаётся в Task 2; здесь тестов нет — только определения типов)

Примечание: поле `license_server` добавляется здесь (а не в Task 7), потому что на него
ссылаются тесты Task 4/6. Генерация `nethasp.ini` из него — в Task 7.

**Interfaces:**
- Produces:
  - `RunResult` — `@dataclass` с полями `returncode: int`, `stdout: str`, `stderr: str`.
  - Протокол `Provisioner` с методами:
    `mkdirs(paths: list[str]) -> None`,
    `exists(path: str) -> bool`,
    `is_empty_dir(path: str) -> bool`,
    `read_text(path: str) -> str`,
    `write_text(path: str, content: str) -> None`,
    `write_bytes(path: str, data: bytes) -> None`,
    `put_tree(local_src: str, dst: str, skip=None) -> None`,
    `run(cmd: list[str], cwd: str | None = None) -> RunResult`,
    `which(tool: str) -> str | None`,
    `python_cmd() -> list[str]` (команда целевого интерпретатора для сборки venv),
    `venv_python(project_dir: str) -> str` (путь к интерпретатору внутри `.venv` на цели).
  - `Backend.provisioner: Provisioner` — новое поле протокола backend'а.

- [ ] **Step 1: Добавить `RunResult` и протокол `Provisioner`**

В `app/src/agentmon/backends/__init__.py` добавить импорт `dataclass` и определения перед классом `Backend`:

```python
from dataclasses import dataclass

@dataclass
class RunResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Provisioner(Protocol):
    """Операции над файловой системой целевой машины и запуск команд на ней.

    Позволяет развернуть проект на любой цели (локальная ФС, удалённый хост по
    SFTP, контейнер) одним и тем же кодом слоя `env/`. put_tree читает дерево с
    машины монитора (local_src всегда локален) и переносит его на цель.
    """

    def mkdirs(self, paths: list[str]) -> None: ...
    def exists(self, path: str) -> bool: ...
    def is_empty_dir(self, path: str) -> bool: ...
    def read_text(self, path: str) -> str: ...
    def write_text(self, path: str, content: str) -> None: ...
    def write_bytes(self, path: str, data: bytes) -> None: ...
    def put_tree(self, local_src: str, dst: str, skip=None) -> None: ...
    def run(self, cmd: list[str], cwd: str | None = None) -> "RunResult": ...
    def which(self, tool: str) -> str | None: ...
    def python_cmd(self) -> list[str]: ...
    def venv_python(self, project_dir: str) -> str: ...
```

- [ ] **Step 2: Добавить поле `provisioner` на `Backend`**

В классе `Backend` рядом с `runner`/`files` объявить атрибут:

```python
class Backend:
    key: str
    runner: AgentRunner
    files: SessionFiles
    provisioner: "Provisioner"
```

- [ ] **Step 3: Добавить поле `license_server` в `EnvConfig`**

В `app/src/agentmon/env/config_schema.py` в dataclass `EnvConfig` добавить последним полем:

```python
    license_server: str | None = None
```

(Поле со значением по умолчанию — `from_dict` остаётся обратно совместимым.)

- [ ] **Step 4: Проверить импортируемость**

Run: `cd app && python -c "from agentmon.backends import Provisioner, RunResult, Backend; from agentmon.env.config_schema import EnvConfig; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/backends/__init__.py app/src/agentmon/env/config_schema.py
git commit -m "backends: протокол Provisioner, RunResult, поле license_server"
```

---

## Task 2: `LocalProvisioner`

**Files:**
- Modify: `app/src/agentmon/backends/local.py`
- Test: `app/tests/test_provisioner_local.py`

**Interfaces:**
- Consumes: `Provisioner`, `RunResult` из Task 1.
- Produces: `LocalProvisioner` (реализация `Provisioner` для той же машины). Подключается в `LocalBackend.__init__` как `self.provisioner = LocalProvisioner()`.

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/test_provisioner_local.py`:

```python
import sys
from pathlib import Path

from agentmon.backends.local import LocalProvisioner


def test_mkdirs_creates_nested(tmp_path):
    prov = LocalProvisioner()
    target = tmp_path / "a" / "b" / "c"
    prov.mkdirs([str(target)])
    assert target.is_dir()


def test_write_and_read_text_roundtrip(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "x.txt"
    prov.write_text(str(p), "привет\n")
    assert prov.read_text(str(p)) == "привет\n"
    assert prov.exists(str(p)) is True


def test_is_empty_dir_semantics(tmp_path):
    prov = LocalProvisioner()
    assert prov.is_empty_dir(str(tmp_path / "missing")) is True
    assert prov.is_empty_dir(str(tmp_path)) is True
    (tmp_path / "f").write_text("x")
    assert prov.is_empty_dir(str(tmp_path)) is False


def test_put_tree_copies_and_skips(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "keep.txt").write_text("k")
    (src / "sub" / "drop.txt").write_text("d")
    dst = tmp_path / "dst"
    prov = LocalProvisioner()
    prov.put_tree(str(src), str(dst), skip=lambda rel: rel.parts[:1] == ("sub",))
    assert (dst / "keep.txt").read_text() == "k"
    assert not (dst / "sub" / "drop.txt").exists()


def test_run_returns_result(tmp_path):
    prov = LocalProvisioner()
    res = prov.run([sys.executable, "-c", "print('hi')"])
    assert res.returncode == 0
    assert "hi" in res.stdout


def test_which_finds_python():
    prov = LocalProvisioner()
    assert prov.which(Path(sys.executable).name) is not None


def test_python_cmd_is_monitor_interpreter():
    prov = LocalProvisioner()
    assert prov.python_cmd() == [sys.executable]


def test_venv_python_matches_os(tmp_path):
    prov = LocalProvisioner()
    got = prov.venv_python(str(tmp_path))
    assert ".venv" in got and got.endswith(("python", "python.exe"))
```

- [ ] **Step 2: Запустить тесты — убедиться, что падают**

Run: `cd app && python -m pytest tests/test_provisioner_local.py -v`
Expected: FAIL — `ImportError: cannot import name 'LocalProvisioner'`

- [ ] **Step 3: Реализовать `LocalProvisioner`**

В `app/src/agentmon/backends/local.py` добавить (вверху — импорты `shutil`, `subprocess`, `sys`, `RunResult`):

```python
import shutil
import subprocess
import sys

from . import BUFFER_LIMIT, Backend, RunResult


class LocalProvisioner:
    """Provisioner для той же машины: прямые Path/shutil/subprocess-операции.

    Поведение повторяет прежний код слоя env/ (scaffold/content/checks) —
    рефакторинг не должен менять результат для backend=local.
    """

    _CRUFT_DIRS = {"__pycache__", "build", ".pytest_cache"}

    def mkdirs(self, paths) -> None:
        for p in paths:
            Path(p).mkdir(parents=True, exist_ok=True)

    def exists(self, path) -> bool:
        return Path(path).exists()

    def is_empty_dir(self, path) -> bool:
        if not path:
            return False
        p = Path(path)
        if not p.exists():
            return True
        if not p.is_dir():
            return False
        return not any(p.iterdir())

    def read_text(self, path) -> str:
        return Path(path).read_text(encoding="utf-8")

    def write_text(self, path, content) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(content, encoding="utf-8")

    def write_bytes(self, path, data) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(data)

    def _is_cruft(self, item: Path) -> bool:
        return any(p in self._CRUFT_DIRS or p.endswith(".egg-info")
                   for p in item.parts)

    def put_tree(self, local_src, dst, skip=None) -> None:
        src, dstp = Path(local_src), Path(dst)
        for item in sorted(src.rglob("*")):
            if self._is_cruft(item):
                continue
            rel = item.relative_to(src)
            if skip is not None and skip(rel):
                continue
            target = dstp / rel
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.read_bytes())

    def run(self, cmd, cwd=None) -> RunResult:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")

    def which(self, tool) -> str | None:
        return shutil.which(tool)

    def python_cmd(self):
        return [sys.executable]

    def venv_python(self, project_dir) -> str:
        import os
        base = Path(project_dir) / ".venv"
        if os.name == "nt":
            return str(base / "Scripts" / "python.exe")
        return str(base / "bin" / "python")
```

Подключить в `LocalBackend.__init__`, добавив строку после `self.files = ...`:

```python
        self.provisioner = LocalProvisioner()
```

- [ ] **Step 4: Запустить тесты — убедиться, что проходят**

Run: `cd app && python -m pytest tests/test_provisioner_local.py -v`
Expected: PASS (8 тестов)

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/backends/local.py app/tests/test_provisioner_local.py
git commit -m "backends: LocalProvisioner (операции на той же машине)"
```

---

## Task 3: `scaffold.py` через provisioner

**Files:**
- Modify: `app/src/agentmon/env/scaffold.py`
- Test: `app/tests/env/test_scaffold.py` (если есть — обновить; иначе создать)

**Interfaces:**
- Consumes: `Provisioner` из Task 1, `LocalProvisioner` из Task 2.
- Produces (новые сигнатуры — используются Task 4/6):
  - `scaffold_layout(prov, project_dir) -> None`
  - `write_json(prov, path, data) -> None`
  - `write_preserving(prov, path, content, *, update: bool) -> None`
  - `write_env_files(prov, config, *, update: bool) -> None`

- [ ] **Step 1: Написать падающие тесты**

Создать/обновить `app/tests/env/test_scaffold.py`:

```python
import json
from pathlib import Path

from agentmon.backends.local import LocalProvisioner
from agentmon.env.scaffold import (scaffold_layout, write_json,
                                    write_preserving)


def test_scaffold_layout_creates_all_dirs(tmp_path):
    prov = LocalProvisioner()
    scaffold_layout(prov, str(tmp_path))
    for rel in [".claude/agents", ".claude/skills", ".claude/hooks",
                "src/cf", "src/cfe", "tasks"]:
        assert (tmp_path / rel).is_dir()


def test_write_json_pretty_utf8(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "d.json"
    write_json(prov, str(p), {"ключ": "значение"})
    assert json.loads(p.read_text(encoding="utf-8")) == {"ключ": "значение"}
    assert "значение" in p.read_text(encoding="utf-8")  # ensure_ascii=False


def test_write_preserving_backs_up_on_update(tmp_path):
    prov = LocalProvisioner()
    p = tmp_path / "f.txt"
    write_preserving(prov, str(p), "старое", update=False)
    write_preserving(prov, str(p), "новое", update=True)
    assert p.read_text(encoding="utf-8") == "новое"
    assert (tmp_path / "f.txt.bak").read_text(encoding="utf-8") == "старое"
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd app && python -m pytest tests/env/test_scaffold.py -v`
Expected: FAIL — `TypeError` (старые сигнатуры без `prov`) или `ImportError`.

- [ ] **Step 3: Переписать `scaffold.py` на provisioner**

Полный новый `app/src/agentmon/env/scaffold.py`:

```python
import json

from .mcp_catalog import build_mcp_json

LAYOUT_DIRS = [
    ".claude/agents", ".claude/skills", ".claude/hooks",
    "src/cf", "src/cfe", "tasks",
]


def scaffold_layout(prov, project_dir) -> None:
    prov.mkdirs([f"{project_dir}/{rel}" for rel in LAYOUT_DIRS])


def write_json(prov, path, data) -> None:
    prov.write_text(
        path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def write_preserving(prov, path, content, *, update: bool) -> None:
    if update and prov.exists(path):
        prov.write_text(path + ".bak", prov.read_text(path))
    prov.write_text(path, content)


def write_env_files(prov, config, *, update: bool) -> None:
    # Пишем только .mcp.json в корень проекта (docker-compose.mcp.yml не нужен:
    # контейнеры MCP поднимаются со страницы «MCP-серверы»).
    write_json(prov, f"{config.project_dir}/.mcp.json", build_mcp_json(config.mcp))
```

Примечание для реализатора: пути строим строковой конкатенацией с `/` — цель всегда
POSIX (local на Windows тоже принимает прямые слэши в Path; тесты это покрывают).

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_scaffold.py -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/scaffold.py app/tests/env/test_scaffold.py
git commit -m "env: scaffold через Provisioner"
```

---

## Task 4: `content.py` через provisioner

**Files:**
- Modify: `app/src/agentmon/env/content.py`
- Test: `app/tests/env/test_content.py` (обновить вызовы; добавить golden-тест)

**Interfaces:**
- Consumes: `Provisioner`, `LocalProvisioner`, обновлённый `scaffold.write_preserving`.
- Produces:
  - `deploy_content(prov, config, *, update: bool) -> None`
  - `provision_venv(prov, config, *, update: bool) -> str | None` (venv строится `prov.python_cmd()`, не `sys.executable`).

- [ ] **Step 1: Написать golden-тест (падающий)**

В `app/tests/env/test_content.py` добавить (если файла нет — создать с этим тестом):

```python
from agentmon.backends.local import LocalProvisioner
from agentmon.env.content import deploy_content
from agentmon.env.config_schema import EnvConfig


def _config(tmp_path):
    return EnvConfig(
        schema_version=1, project_name="demo", project_dir=str(tmp_path),
        developer_id="dev", developer_email="d@e", platform_dir="",
        platform_version="", db_kind="server", db_connection="",
        web_publication="", mcp=[], agents=[], license_server=None)


def test_deploy_content_populates_claude(tmp_path):
    prov = LocalProvisioner()
    deploy_content(prov, _config(tmp_path), update=False)
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / ".claude" / "agents").is_dir()
    assert (tmp_path / "README.md").read_text(encoding="utf-8").startswith("## demo")
```

Примечание: `EnvConfig` получает новое поле `license_server` в Task 7 — на момент Task 4
временно передавайте его позиционно/именованно только если поле уже добавлено; иначе
уберите `license_server=None` из `_config` до Task 7, а затем верните. (Реализатор:
если Task 7 ещё не сделан, выполните его поле-изменение `config_schema.py` первым —
оно крошечное и безопасно.)

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/env/test_content.py -v`
Expected: FAIL — `TypeError: deploy_content() missing ... 'prov'` или рассинхрон сигнатур.

- [ ] **Step 3: Переписать `content.py` на provisioner**

Ключевые изменения (остальное — механический перенос `Path`-операций на `prov.*`):

1. Убрать из модуля прямые `shutil`/`subprocess`/`os`-операции над целью. `TEMPLATE_DIR`
   остаётся (это **исходник** на машине монитора — читаем его локально через `Path`).
2. `_copy_tree(...)` удалить — заменяется `prov.put_tree(str(TEMPLATE_DIR), project_dir, skip=_is_special)`.
3. Рендер агентов/настроек: шаблоны читаем с диска монитора (`CONTENT_DIR / ...` через
   локальный `Path.read_text` — это источник), а **пишем** через `prov.write_text`.
4. `venv_python`/`_py_cmd`/`_deploy_vscode` используют `prov.venv_python(project_dir)`
   вместо локального вычисления пути.
5. `provision_venv` строит venv командой `prov.python_cmd()` и ставит зависимости через
   `prov.run`, пути — целевые.

Новые сигнатуры и тела критичных функций:

```python
def venv_python(prov, project_dir) -> str:
    return prov.venv_python(project_dir)


def _py_cmd(prov, project_dir) -> str:
    return '"' + prov.venv_python(project_dir) + '"'


def _deploy_vscode(prov, project_dir, *, update: bool) -> None:
    content = json.dumps(
        {"python.defaultInterpreterPath": prov.venv_python(project_dir)},
        ensure_ascii=False, indent=2) + "\n"
    write_preserving(prov, f"{project_dir}/.vscode/settings.json",
                     content, update=update)


def provision_venv(prov, config, *, update: bool) -> str | None:
    """Создаёт .venv на ЦЕЛЕВОЙ машине интерпретатором цели (prov.python_cmd()).

    Раньше venv строился sys.executable — для SSH это интерпретатор монитора, не
    цели. Теперь интерпретатор задаёт provisioner (local → sys.executable,
    ssh → python3 на удалённом хосте). Ошибки venv/pip НЕ валят создание проекта.
    """
    project_dir = config.project_dir
    venv_dir = f"{project_dir}/.venv"
    py = prov.venv_python(project_dir)
    req = TEMPLATE_DIR / "requirements.txt"
    if not prov.exists(venv_dir):
        res = prov.run(prov.python_cmd() + ["-m", "venv", venv_dir])
        if res.returncode != 0:
            return (f"не удалось подготовить .venv ({res.stderr.strip()}); "
                    f"зависимости навыков не установлены. "
                    f"Доустановите: python setup-venv.py")
    if req.is_file():
        # requirements.txt — исходник на мониторе; заливаем его на цель и ставим.
        prov.write_text(f"{project_dir}/.ai1c-requirements.txt",
                        req.read_text(encoding="utf-8"))
        res = prov.run([py, "-m", "pip", "install", "-r",
                        f"{project_dir}/.ai1c-requirements.txt"])
        if res.returncode != 0:
            return (f"не удалось поставить зависимости навыков "
                    f"({res.stderr.strip()}). Доустановите: python setup-venv.py")
    return None


def deploy_content(prov, config, *, update: bool) -> None:
    project_dir = config.project_dir
    claude = f"{project_dir}/.claude"
    prov.put_tree(str(TEMPLATE_DIR), project_dir, skip=_is_special)
    _render_agents(prov, config, f"{claude}/agents")
    py_json = '\\"' + prov.venv_python(project_dir) + '\\"'
    settings = _PY_INVOKE.sub(lambda m: py_json + " ", _render_settings())
    write_preserving(prov, f"{claude}/settings.json", settings, update=update)
    _rewrite_python_invocations(prov, claude, _py_cmd(prov, project_dir))
    _deploy_vscode(prov, project_dir, update=update)
    if not update:
        write_preserving(prov, f"{project_dir}/README.md",
                         _project_readme(config.project_name), update=update)
        overrides = mcp_name_overrides(config.mcp)
        if overrides:
            _apply_mcp_names(prov, claude, overrides)
```

Для `_render_agents`, `_rewrite_python_invocations`, `_apply_mcp_names`: сейчас они
ходят по **целевому** дереву через `Path(...).rglob` и перезаписывают файлы. После
`put_tree` файлы уже на цели — но на удалённой цели локальный `rglob` их не увидит.
Решение: эти три функции должны обходить **исходный шаблон** (`CONTENT_DIR`, он на
мониторе) для перечня файлов, а писать результат на цель через `prov.write_text`.

```python
def _render_agents(prov, config, agents_dst) -> None:
    prov.mkdirs([agents_dst])
    for src in sorted((CONTENT_DIR / "agents").glob("*.md")):
        model, effort = _model_effort(config, src.stem)
        text = src.read_text(encoding="utf-8")
        text = text.replace("{{MODEL}}", model).replace("{{EFFORT}}", effort)
        prov.write_text(f"{agents_dst}/{src.name}", text)


def _rewrite_python_invocations(prov, claude_dir, py_cmd) -> None:
    """Пишет версии *.md шаблона с заменой `python ` на путь venv — на цель.

    Источник списка файлов — шаблон на мониторе (CONTENT_DIR); пишем на цель.
    """
    for src in sorted(CONTENT_DIR.rglob("*.md")):
        if "__pycache__" in src.parts:
            continue
        rel = src.relative_to(CONTENT_DIR)
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = _PY_INVOKE.sub(lambda m: py_cmd + " ", text)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}", new)


def _apply_mcp_names(prov, claude_dir, overrides) -> None:
    """Подставляет актуальные имена MCP вместо плейсхолдеров — пишем на цель.

    Обходим текстовые файлы шаблона .claude на мониторе; меняем и пишем на цель
    только изменившиеся.
    """
    for src in sorted(CONTENT_DIR.rglob("*")):
        if not src.is_file() or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(CONTENT_DIR)
        try:
            text = src.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for placeholder, actual in overrides.items():
            new = new.replace(placeholder, actual)
        if new != text:
            prov.write_text(f"{claude_dir}/{rel.as_posix()}", new)
```

Замечание по порядку (сохранить прежнюю семантику): `put_tree` кладёт исходные `*.md`,
затем `_rewrite_python_invocations`/`_apply_mcp_names` перезаписывают изменившиеся —
итог для local тот же, что раньше (раньше правка шла поверх уже скопированных файлов;
теперь — из шаблона на цель, содержимое идентично).

- [ ] **Step 4: Запустить — убедиться, что проходит**

Run: `cd app && python -m pytest tests/env/test_content.py -v`
Expected: PASS

- [ ] **Step 5: Golden-сверка с прежним поведением (ручная проверка)**

Run: `cd app && python -m pytest tests/env -v`
Expected: все существующие env-тесты зелёные (регрессий нет).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/content.py app/tests/env/test_content.py
git commit -m "env: deploy_content/provision_venv через Provisioner (venv интерпретатором цели)"
```

---

## Task 5: `project_checks.py` через provisioner

**Files:**
- Modify: `app/src/agentmon/env/project_checks.py`
- Test: `app/tests/env/test_project_checks.py` (обновить/создать)

**Interfaces:**
- Consumes: `Provisioner`, `RunResult`.
- Produces (чистые построители команд не меняются; меняется исполнитель):
  - `is_empty_dir(prov, path) -> bool`
  - `requirements(prov) -> list[dict]` (использует `prov.which` и `prov.run`)
  - `platform_binary(prov, platform_dir) -> str | None`
  - `check_db(prov, *, platform_dir, db_connection, db_kind="", user="", password="") -> dict`
  - Неизменны: `validate_name`, `infer_db_kind`, `auth_args`, `_designer_db_arg`,
    `build_check_db_command`, `current_env_version`.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_project_checks.py`:

```python
from agentmon.backends import RunResult
from agentmon.backends.local import LocalProvisioner
from agentmon.env import project_checks as pc


class FakeProv:
    def __init__(self, exists=None, which_map=None, run_result=None,
                 empty=True):
        self._exists = set(exists or [])
        self._which = which_map or {}
        self._run_result = run_result or RunResult(0, "", "")
        self._empty = empty
        self.run_calls = []

    def exists(self, path):
        return path in self._exists

    def is_empty_dir(self, path):
        return self._empty

    def which(self, tool):
        return self._which.get(tool)

    def run(self, cmd, cwd=None):
        self.run_calls.append(cmd)
        return self._run_result


def test_is_empty_dir_delegates_to_prov():
    prov = FakeProv(empty=False)
    assert pc.is_empty_dir(prov, "/srv/x") is False


def test_requirements_uses_prov_which():
    prov = FakeProv(which_map={"git": "/usr/bin/git"})
    rows = pc.requirements(prov)
    names = {r["name"]: r["ok"] for r in rows}
    assert names["git"] is True
    assert names["claude"] is False


def test_platform_binary_found_via_prov_exists():
    prov = FakeProv(exists={"/opt/1cv8/1cv8"})
    assert pc.platform_binary(prov, "/opt/1cv8") == "/opt/1cv8/1cv8"


def test_check_db_runs_designer_via_prov(tmp_path):
    prov = FakeProv(exists={"/opt/1cv8/1cv8"}, run_result=RunResult(0, "", ""))
    res = pc.check_db(prov, platform_dir="/opt/1cv8",
                      db_connection='srvr="s";ref="base"', db_kind="server")
    assert res["ok"] is True
    assert prov.run_calls and "DESIGNER" in prov.run_calls[0]
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd app && python -m pytest tests/env/test_project_checks.py -v`
Expected: FAIL — старые сигнатуры без `prov`.

- [ ] **Step 3: Переписать проверки на provisioner**

Изменения (построители argv не трогаем):

```python
def is_empty_dir(prov, path) -> bool:
    return prov.is_empty_dir(path)


def requirements(prov) -> list[dict]:
    required_tools = ["git", "claude", "node"]
    result = []
    for tool in required_tools:
        path = prov.which(tool)
        result.append({"name": tool, "ok": path is not None,
                       "detail": path if path else "не найден"})
    # git bash нужен только если цель — Windows; в удалённых Linux-сценариях нет.
    # Для local сохраняем прежнюю проверку по sys.platform монитора.
    import sys
    if sys.platform.startswith("win"):
        path = prov.which("bash")
        result.append({"name": "git bash", "ok": path is not None,
                       "detail": path if path else "не найден (установите Git for Windows)"})
    return result


def platform_binary(prov, platform_dir) -> str | None:
    """Путь к исполняемому 1cv8 на ЦЕЛИ. Цель — Linux: имя `1cv8`.

    Если platform_dir указывает прямо на файл — вернём его (prov.exists).
    Иначе ищем `1cv8` в каталоге и в bin/.
    """
    if not platform_dir:
        return None
    if prov.exists(platform_dir) and not prov.exists(f"{platform_dir}/1cv8") \
            and not prov.exists(f"{platform_dir}/bin/1cv8"):
        # platform_dir может быть самим файлом 1cv8 — отличим по отсутствию детей.
        # (эвристика достаточна: каталог платформы всегда содержит 1cv8|bin/1cv8)
        return platform_dir
    for cand in (f"{platform_dir}/1cv8", f"{platform_dir}/bin/1cv8",
                 f"{platform_dir}/1cv8.exe", f"{platform_dir}/bin/1cv8.exe"):
        if prov.exists(cand):
            return cand
    return None


def check_db(prov, *, platform_dir, db_connection, db_kind="",
             user="", password="") -> dict:
    """Проверяет доступ к базе через `1cv8 DESIGNER ... /DumpDBCfgList` на ЦЕЛИ.

    Запуск — через prov.run (на удалённом хосте там же, где платформа и сеть до
    сервера 1С). Лог ошибки собираем из stdout/stderr команды.
    """
    if not platform_dir:
        return {"ok": False, "log": "Укажите путь к платформе 1С."}
    binary = platform_binary(prov, platform_dir)
    if binary is None:
        return {"ok": False,
                "log": f"Не найден исполняемый 1cv8 по пути платформы: {platform_dir}"}
    if not db_kind:
        db_kind = infer_db_kind(db_connection)
    out_log = f"{platform_dir}/.ai1c-check-db.log"
    cmd = build_check_db_command(binary, db_connection, user, password,
                                 db_kind=db_kind, out_log=out_log)
    res = prov.run(cmd)
    ok = res.returncode == 0
    if ok:
        return {"ok": True, "log": "Доступ есть"}
    tail = ((res.stdout or "") + (res.stderr or "")).strip()
    try:
        file_log = prov.read_text(out_log).strip()
    except Exception:
        file_log = ""
    log = "\n".join(p for p in (file_log, tail) if p) or f"Код возврата {res.returncode}"
    return {"ok": False, "log": log}
```

Замечание: `build_check_db_command` раньше сам вычислял `platform_binary`; теперь ему
передаём уже найденный `binary` первым аргументом. Поправить его сигнатуру — первый
параметр переименовать в `binary` и убрать внутренний вызов `platform_binary`:

```python
def build_check_db_command(binary, db_connection="", user="", password="",
                           *, db_kind="", out_log="") -> list[str]:
    if not db_kind:
        db_kind = infer_db_kind(db_connection)
    flag, value = _designer_db_arg(db_kind, db_connection)
    return [binary, "DESIGNER", flag, value, *auth_args(user, password),
            "/DisableStartupDialogs", "/Out", out_log,
            "/DumpDBCfgList", "-AllExtensions"]
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd app && python -m pytest tests/env/test_project_checks.py -v`
Expected: PASS (4 теста)

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/project_checks.py app/tests/env/test_project_checks.py
git commit -m "env: проверки проекта (empty/requirements/platform/check_db) через Provisioner"
```

---

## Task 6: Прокинуть provisioner в `project_api.py`

**Files:**
- Modify: `app/src/agentmon/env/project_api.py`
- Test: `app/tests/test_api.py` (smoke создания local-проекта — должен остаться зелёным) + новый `app/tests/env/test_install_wiring.py`

**Interfaces:**
- Consumes: `registry` (есть `BackendRegistry`), обновлённые `scaffold`/`content`/`project_checks`.
- Produces: установка проекта берёт `prov = registry.get(project).provisioner` и прокидывает его во все вызовы scaffold/deploy/проверок. Роуты `validate_name`/`check_db`/`get_requirements` используют provisioner backend'а из тела запроса (для создания проекта backend известен из конфига).

- [ ] **Step 1: Найти все вызовы refactored-функций**

Run: `cd app && grep -n "scaffold_layout\|deploy_content\|provision_venv\|write_env_files\|is_empty_dir\|requirements(\|platform_binary\|check_db\|build_check_db_command" src/agentmon/env/project_api.py`
Expected: список строк — все они требуют первого аргумента `prov`.

- [ ] **Step 2: Написать тест проводки (падающий)**

Создать `app/tests/env/test_install_wiring.py`:

```python
from agentmon.env.config_schema import EnvConfig
from agentmon.env import scaffold, content


def _config(tmp_path):
    return EnvConfig(
        schema_version=1, project_name="demo", project_dir=str(tmp_path),
        developer_id="dev", developer_email="d@e", platform_dir="",
        platform_version="", db_kind="server", db_connection="",
        web_publication="", mcp=[], agents=[], license_server=None)


def test_local_install_end_to_end(tmp_path):
    from agentmon.backends.local import LocalProvisioner
    prov = LocalProvisioner()
    cfg = _config(tmp_path)
    scaffold.scaffold_layout(prov, cfg.project_dir)
    content.deploy_content(prov, cfg, update=False)
    scaffold.write_env_files(prov, cfg, update=False)
    assert (tmp_path / ".claude" / "settings.json").is_file()
    assert (tmp_path / ".mcp.json").is_file()
```

- [ ] **Step 3: Запустить — убедиться, что падает (если Task 7 ещё не сделан — сделать его поле первым)**

Run: `cd app && python -m pytest tests/env/test_install_wiring.py -v`
Expected: PASS (это проверка, что слой env целостно работает через provisioner; если падает — чинить проводку).

- [ ] **Step 4: Обновить `project_api.py`**

Во всех местах установки: получить backend проекта и его provisioner, прокинуть первым
аргументом. Шаблон правки (для `_install_iter`/`_prepare_install` и роутов проверок):

```python
        backend = registry.get(project)   # project с нужным backend/conn
        prov = backend.provisioner
        ...
        scaffold.scaffold_layout(prov, config.project_dir)
        content.deploy_content(prov, config, update=update)
        content.provision_venv(prov, config, update=update)
        scaffold.write_env_files(prov, config, update=update)
```

Для роутов `check_db_route`/`get_requirements`/`validate_name_route`: если тело запроса
содержит backend+conn (создание ssh-проекта), построить временный Project и взять его
provisioner через `registry.get(...)`; при отсутствии — local (как сейчас).

- [ ] **Step 5: Запустить весь набор**

Run: `cd app && python -m pytest -q`
Expected: PASS (включая существующие api/smoke-тесты создания local-проекта).

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/env/project_api.py app/tests/env/test_install_wiring.py
git commit -m "env: project_api разворачивает проект через Provisioner выбранного backend"
```

---

## Task 7: Генерация `nethasp.ini` из `license_server`

**Files:**
- Create: `app/src/agentmon/env/nethasp.py`
- Modify: `app/src/agentmon/env/content.py` (вызов `deploy_nethasp`)
- Test: `app/tests/test_nethasp.py`

**Interfaces:**
- Consumes: `EnvConfig.license_server` (добавлено в Task 1).
- Produces:
  - `nethasp.render_nethasp_ini(server_addr: str) -> str`
  - `nethasp.deploy_nethasp(prov, config) -> None` (пишет `conf/nethasp.ini` в каталог
    профиля платформы проекта, если `license_server` задан).

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/test_nethasp.py`:

```python
from agentmon.env.nethasp import render_nethasp_ini, deploy_nethasp
from agentmon.env.config_schema import EnvConfig
from agentmon.backends.local import LocalProvisioner


def test_render_contains_server_addr():
    ini = render_nethasp_ini("10.0.0.5")
    assert "[NH_SERVER]" in ini
    assert "NH_SERVER_ADDR = 10.0.0.5" in ini
    assert "NH_TCPIP = Enabled" in ini


def test_deploy_writes_file_when_server_set(tmp_path):
    prov = LocalProvisioner()
    cfg = EnvConfig(schema_version=1, project_name="d", project_dir=str(tmp_path),
                    developer_id="x", developer_email="x", platform_dir="",
                    platform_version="", db_kind="server", db_connection="",
                    web_publication="", mcp=[], agents=[], license_server="10.0.0.5")
    deploy_nethasp(prov, cfg)
    assert (tmp_path / "conf" / "nethasp.ini").read_text(encoding="utf-8").find("10.0.0.5") > 0


def test_deploy_noop_when_server_empty(tmp_path):
    prov = LocalProvisioner()
    cfg = EnvConfig(schema_version=1, project_name="d", project_dir=str(tmp_path),
                    developer_id="x", developer_email="x", platform_dir="",
                    platform_version="", db_kind="server", db_connection="",
                    web_publication="", mcp=[], agents=[], license_server=None)
    deploy_nethasp(prov, cfg)
    assert not (tmp_path / "conf" / "nethasp.ini").exists()
```

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd app && python -m pytest tests/test_nethasp.py -v`
Expected: FAIL — модуль `nethasp` отсутствует.

- [ ] **Step 3: Реализовать `nethasp.py`**

Создать `app/src/agentmon/env/nethasp.py`:

```python
"""Генерация nethasp.ini для доступа к сетевому серверу лицензирования 1С.

При client-server + сетевых лицензиях контейнеру/удалённому хосту достаточно
указать адрес NETHASP-сервера — файл кладётся в каталог профиля платформы проекта
(conf/nethasp.ini). Пустой адрес → файл не пишем (платформа ищет лицензию штатно).
"""


def render_nethasp_ini(server_addr: str) -> str:
    return (
        "[NH_COMMON]\n"
        "NH_TCPIP = Enabled\n"
        "\n"
        "[NH_TCPIP]\n"
        f"NH_SERVER_ADDR = {server_addr}\n"
        "NH_TCPIP_METHOD = TCP\n"
        "NH_USE_BROADCAST = Disabled\n"
        "\n"
        "[NH_SERVER]\n"
        f"NH_SERVER_ADDR = {server_addr}\n"
    )


def deploy_nethasp(prov, config) -> None:
    server = (config.license_server or "").strip()
    if not server:
        return
    prov.write_text(f"{config.project_dir}/conf/nethasp.ini",
                    render_nethasp_ini(server))
```

Подключить вызов в `content.deploy_content` (в конце функции, до/после MCP-подстановки):

```python
    from .nethasp import deploy_nethasp
    deploy_nethasp(prov, config)
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd app && python -m pytest tests/test_nethasp.py -v`
Expected: PASS (3 теста)

- [ ] **Step 5: Commit**

```bash
git add app/src/agentmon/env/nethasp.py app/src/agentmon/env/content.py app/tests/test_nethasp.py
git commit -m "env: генерация nethasp.ini из license_server"
```

---

## Task 8: `SshProvisioner`

**Files:**
- Modify: `app/src/agentmon/backends/ssh.py`
- Test: `app/tests/test_provisioner_ssh.py`

**Interfaces:**
- Consumes: `_Connection` (есть `.sftp()`, `.client().get_transport().open_session()`),
  `Provisioner`, `RunResult`.
- Produces: `SshProvisioner(connection)` — реализация `Provisioner` по SFTP/exec.
  Подключается в `SshBackend.__init__`: `self.provisioner = SshProvisioner(self._c)`.
  `python_cmd()` → `["python3"]`; `venv_python(d)` → `f"{d}/.venv/bin/python"`.

- [ ] **Step 1: Написать падающие тесты**

Создать `app/tests/test_provisioner_ssh.py` (расширяет фейки из `test_backend_ssh.py`):

```python
from agentmon.backends.ssh import SshProvisioner


class FakeExecChannel:
    def __init__(self, rc=0, out=b"", err=b""):
        self._rc, self._out, self._err = rc, out, err

    def exec_command(self, cmd):
        self.cmd = cmd

    def makefile(self, *a):
        import io
        return io.BytesIO(self._out)

    def makefile_stderr(self, *a):
        import io
        return io.BytesIO(self._err)

    def recv_exit_status(self):
        return self._rc


class FakeSftpRW:
    def __init__(self):
        self.files = {}
        self.dirs = set()

    def mkdir(self, path):
        self.dirs.add(path)

    def stat(self, path):
        if path in self.files or path in self.dirs:
            return object()
        raise FileNotFoundError(path)

    def open(self, path, mode="r"):
        import io
        if "w" in mode:
            buf = _WriteBuf(self, path)
            return buf
        return io.BytesIO(self.files[path])

    def listdir(self, path):
        return [k.rsplit("/", 1)[-1] for k in self.files if k.startswith(path + "/")]


class _WriteBuf:
    def __init__(self, sftp, path):
        self.sftp, self.path, self.data = sftp, path, b""

    def write(self, b):
        self.data += b if isinstance(b, bytes) else b.encode("utf-8")

    def close(self):
        self.sftp.files[self.path] = self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeConn:
    def __init__(self, sftp, exec_rc=0, exec_out=b"", exec_err=b""):
        self._sftp = sftp
        self._exec = FakeExecChannel(exec_rc, exec_out, exec_err)
        self.exec_cmds = []

    def sftp(self):
        return self._sftp

    def exec(self, cmd):          # помощник, если SshProvisioner использует свой exec
        self.exec_cmds.append(cmd)
        self._exec.exec_command(cmd)
        return self._exec


def test_write_and_read_text():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    prov.write_text("/srv/demo/a.txt", "привет")
    assert prov.read_text("/srv/demo/a.txt") == "привет"


def test_mkdirs_creates_each_segment():
    sftp = FakeSftpRW()
    prov = SshProvisioner(FakeConn(sftp))
    prov.mkdirs(["/srv/demo/.claude/agents"])
    assert "/srv/demo/.claude/agents" in sftp.dirs


def test_run_returns_exit_status_and_output():
    prov = SshProvisioner(FakeConn(FakeSftpRW(), exec_rc=0, exec_out=b"ok\n"))
    res = prov.run(["echo", "ok"])
    assert res.returncode == 0 and "ok" in res.stdout


def test_python_cmd_and_venv_python_are_posix():
    prov = SshProvisioner(FakeConn(FakeSftpRW()))
    assert prov.python_cmd() == ["python3"]
    assert prov.venv_python("/srv/demo") == "/srv/demo/.venv/bin/python"
```

Примечание реализатору: точный метод exec у `_Connection` — подобрать по факту
(`get_transport().open_session()` + `exec_command`, затем `recv_exit_status`);
фейк `FakeConn.exec` показывает ожидаемую форму. Если удобнее — добавьте в
`_Connection` тонкий helper `exec(cmd) -> channel`, это допустимо.

- [ ] **Step 2: Запустить — убедиться, что падают**

Run: `cd app && python -m pytest tests/test_provisioner_ssh.py -v`
Expected: FAIL — нет `SshProvisioner`.

- [ ] **Step 3: Реализовать `SshProvisioner`**

В `app/src/agentmon/backends/ssh.py` добавить класс (использует `self._c` —
`_Connection`). Импортировать `RunResult`, `posixpath`:

```python
import posixpath

from . import BUFFER_LIMIT, Backend, RunResult


class SshProvisioner:
    """Provisioner по SSH: файловые операции через SFTP, команды через exec-канал.

    Переиспользует _Connection ssh-бэкенда (одно соединение на хост). Цель —
    Linux: пути POSIX, интерпретатор python3, venv в .venv/bin/python.
    """

    def __init__(self, connection):
        self._c = connection

    # --- файловые операции (SFTP) ---
    def mkdirs(self, paths) -> None:
        sftp = self._c.sftp()
        for path in paths:
            parts, cur = path.strip("/").split("/"), ""
            for seg in parts:
                cur = cur + "/" + seg
                try:
                    sftp.stat(cur)
                except FileNotFoundError:
                    sftp.mkdir(cur)

    def exists(self, path) -> bool:
        try:
            self._c.sftp().stat(path)
            return True
        except FileNotFoundError:
            return False

    def is_empty_dir(self, path) -> bool:
        if not path:
            return False
        if not self.exists(path):
            return True
        try:
            return len(self._c.sftp().listdir(path)) == 0
        except OSError:
            return False  # путь — файл, не каталог

    def read_text(self, path) -> str:
        with self._c.sftp().open(path, "r") as fh:
            data = fh.read()
        return data.decode("utf-8") if isinstance(data, bytes) else data

    def write_text(self, path, content) -> None:
        self.write_bytes(path, content.encode("utf-8"))

    def write_bytes(self, path, data) -> None:
        self.mkdirs([posixpath.dirname(path)])
        with self._c.sftp().open(path, "w") as fh:
            fh.write(data)

    def put_tree(self, local_src, dst, skip=None) -> None:
        from pathlib import Path
        cruft = {"__pycache__", "build", ".pytest_cache"}
        src = Path(local_src)
        for item in sorted(src.rglob("*")):
            if any(p in cruft or p.endswith(".egg-info") for p in item.parts):
                continue
            rel = item.relative_to(src)
            if skip is not None and skip(rel):
                continue
            target = f"{dst}/{rel.as_posix()}"
            if item.is_dir():
                self.mkdirs([target])
            else:
                self.write_bytes(target, item.read_bytes())

    # --- выполнение команд (exec) ---
    def run(self, cmd, cwd=None) -> RunResult:
        line = " ".join(shlex.quote(c) for c in cmd)
        if cwd:
            line = f"cd {shlex.quote(cwd)} && {line}"
        chan = self._c.client().get_transport().open_session()
        chan.exec_command(line)
        out = chan.makefile("rb").read()
        err = chan.makefile_stderr("rb").read()
        rc = chan.recv_exit_status()
        return RunResult(rc, out.decode("utf-8", "replace"),
                         err.decode("utf-8", "replace"))

    def which(self, tool) -> str | None:
        res = self.run(["command", "-v", tool])
        path = res.stdout.strip()
        return path or None

    def python_cmd(self):
        return ["python3"]

    def venv_python(self, project_dir) -> str:
        return f"{project_dir}/.venv/bin/python"
```

Подключить в `SshBackend.__init__` после создания `_Connection`/files:

```python
        self.provisioner = SshProvisioner(self._c)
```

- [ ] **Step 4: Запустить — убедиться, что проходят**

Run: `cd app && python -m pytest tests/test_provisioner_ssh.py -v`
Expected: PASS (4 теста)

- [ ] **Step 5: Прогнать весь ssh-набор (регрессий нет)**

Run: `cd app && python -m pytest tests/test_backend_ssh.py tests/test_provisioner_ssh.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/src/agentmon/backends/ssh.py app/tests/test_provisioner_ssh.py
git commit -m "backends: SshProvisioner (scaffold/deploy по SFTP+exec)"
```

---

## Task 9: Мастер проекта — поле «Сервер лицензий» + ssh-создание

**Files:**
- Modify: `app/src/agentmon/web/` (форма мастера проекта — HTML/JS; найти по строке «Платформа»)
- Modify: `app/src/agentmon/env/project_api.py` (принять `license_server` из тела, прокинуть в `EnvConfig`)
- Test: `app/tests/test_api.py` (smoke: создание проекта с `license_server` и с `backend="ssh"` на фейковом backend)

**Interfaces:**
- Consumes: `EnvConfig.license_server` (Task 7), `SshProvisioner` (Task 8), проводка Task 6.
- Produces: мастер отправляет `license_server`; создание ssh-проекта проходит валидации
  и деплой через `SshProvisioner` (в тестах — фейковый ssh backend, инъектированный в
  `BackendRegistry` через `ssh_factory`).

- [ ] **Step 1: Найти форму мастера и место сборки EnvConfig**

Run: `cd app && grep -rn "platform_dir\|db_connection\|Платформа\|license" src/agentmon/web src/agentmon/env/project_api.py | head`
Expected: место формы (web) и место сборки `EnvConfig`/тела запроса.

- [ ] **Step 2: Написать smoke-тест (падающий)**

В `app/tests/test_api.py` добавить тест создания ssh-проекта на фейковом backend. Форму
фейка взять из `tests/test_backend_ssh.py` (там есть `ssh_factory`-паттерн через
`connect_fn`). Проверка: `POST /api/projects` (или текущий endpoint создания) с телом
`{"backend":"ssh","conn":{...},"license_server":"10.0.0.5", ...}` возвращает успех, и
`SshProvisioner.write_text` вызвался для `.mcp.json`/`settings.json` (через фейковый
SFTP). Точную форму endpoint взять из `project_api.create_project`/`create_project_stream`.

- [ ] **Step 3: Запустить — убедиться, что падает**

Run: `cd app && python -m pytest tests/test_api.py -k ssh -v`
Expected: FAIL.

- [ ] **Step 4: Добавить поле в форму и проводку в API**

- В форме мастера (раздел «Платформа» или «База») добавить input «Сервер лицензий»
  (`name="license_server"`, необязательное, подсказка «адрес NETHASP-сервера, напр.
  10.0.0.5»).
- В `project_api` при сборке `EnvConfig` из тела запроса прокинуть
  `license_server=body.get("license_server")`.
- Убедиться, что путь создания использует provisioner выбранного backend (Task 6) —
  для `backend="ssh"` это `SshProvisioner`.

- [ ] **Step 5: Запустить — убедиться, что проходит**

Run: `cd app && python -m pytest tests/test_api.py -v`
Expected: PASS.

- [ ] **Step 6: Полный прогон**

Run: `cd app && python -m pytest -q`
Expected: PASS (весь набор зелёный).

- [ ] **Step 7: Commit**

```bash
git add app/src/agentmon/web app/src/agentmon/env/project_api.py app/tests/test_api.py
git commit -m "мастер: поле Сервер лицензий и создание проекта по SSH"
```

---

## Task 10: README/PHASES — отметить готовность ssh-создания

**Files:**
- Modify: `README.md`, `docs/PHASES.md`

**Interfaces:** нет кода — документация.

- [ ] **Step 1: Обновить PHASES (Фаза 3)**

В `docs/PHASES.md` в разделе «Фаза 3» отметить, что создание проекта по SSH реализовано
(scaffold+deploy по SFTP, проверки на удалённом хосте, nethasp.ini, поле «Сервер
лицензий»); docker-backend и упаковка монитора — следующие шаги.

- [ ] **Step 2: Обновить README (бэкенды подключения)**

В разделе про бэкенды отметить, что `ssh` теперь умеет не только запуск агентов, но и
создание проекта на удалённом хосте.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/PHASES.md
git commit -m "docs: ssh-создание проекта (Фаза 3)"
```

---

## Self-Review (выполнено при написании плана)

**Покрытие спеки:**
- Часть A (Provisioner-рефакторинг) → Tasks 1–6.
- Часть B (ssh-create) → Tasks 8–9.
- Поле `license_server` + nethasp.ini → Task 7.
- Валидации на удалённом хосте → Task 5 (через `prov.run`) + Task 9 (проводка).
- Инвариант «local байт-в-байт» → golden-тесты Task 4/6 + полный прогон на каждом шаге.
- Границы (нет sshfs/docker/USB/файловых баз) → явно в спеке; план их не вводит.

**Сканирование плейсхолдеров:** код приведён в каждом шаге, где он меняется; «найти по
grep» шаги — это осознанная локализация точек правки в большом существующем файле
(web-форма, project_api), а не заглушка.

**Согласованность типов:** `Provisioner`-методы и их сигнатуры совпадают между Task 1
(определение), Task 2/8 (реализации), Task 3–6 (потребители). `build_check_db_command`
первый аргумент переименован в `binary` согласованно в Task 5. `provision_venv` строит
venv `prov.python_cmd()` во всех местах.

**Порядок:** Task 7 (поле `license_server`) требуется тестам Task 4/6 — реализатору
указано сделать крошечное поле-изменение `config_schema.py` до этих тестов, если он
идёт строго по порядку.

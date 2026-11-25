# Мастер проекта: code index и docker-схема — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task (без субагентов — требование пользователя). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Мастер проекта AgentMon получает галочку code index с автосозданием сервиса и карточки MCP (мульти-база по alias), а docker-проект поднимается по работающей схеме benchmark: тома `/workspace` и `/code-index`, нативный code-index внутри контейнера, обёртка агента и лицензии.

**Architecture:** Новые модули `agent_setup.py` (обёртка/ключ/Strata в контейнере), `code_index_docker.py` (развёртывание `bsl-indexer` в контейнере), `code_index_project.py` (валидация, порт, карточка, ожидание). `backends/docker.py` получает том code-index, копирование/exec с env, seed доверия и нормализацию команды агента. `project_api.py` создаёт карточку до установки (чтобы она попала в `.mcp.json`), разворачивает сервис после установки и ждёт готовности; мастер (`project-wizard.*`) отправляет `code_index` и `license_dir`.

**Tech Stack:** Python 3.12, FastAPI, pytest, нативный `bsl-indexer`, Docker CLI (`docker exec`/`docker cp`), vanilla JS.

## Global Constraints

- Коммиты — локально в `main`, **push не выполняется**.
- Субагенты не используются: все задачи выполняются последовательно в этой сессии.
- Тесты запускать из `app/`: `cd app && ../.venv/bin/python -m pytest ... -q`.
- Все пользовательские тексты ошибок — на русском, в стиле существующих сообщений.
- Никаких изменений в `deps/code-index-mcp` и benchmark-коде, кроме обратной совместимости `DockerProvisioner`.
- Docker-проект: пользователь `root`, `HOME=/root`, тома `<name>-work:/workspace`, `<name>-codeindex:/code-index`, `<name>-claude:/root/.claude`; `/home/uam` и репозиторий template не монтируются.
- Сеть: `--network host` только на Linux с локальным Docker-демоном; иначе bridge + `host.docker.internal`.
- Лицензии: каталог монтируется только для docker при пустом `license_server`, как `<license_dir>:/var/1C/licenses` (rw).
- Code-index alias всегда равен имени проекта.
- Таймаут ожидания индекса — 360 минут.

---

### Task 1: Общие тестовые фейки и подготовка агента в контейнере

**Files:**
- Create: `app/tests/env/fakes_code_index.py`
- Create: `app/src/agentmon/env/agent_setup.py`
- Test: `app/tests/env/test_agent_setup.py`

**Interfaces:**
- Produces:
  - `fakes_code_index.FakeProvisioner` — `write_text(path, content)`, `read_text(path)`, `exists(path)`, `mkdirs(paths)`, `run(cmd, cwd=None, timeout=None, env=None)`, `exec_detached(argv, cwd=None, env=None)`, `copy_in(local_path, dst)`; поля `writes`, `runs`, `detached`, `copies`, `home`, `run_results`.
  - `agent_setup.container_command(command: str) -> str`
  - `agent_setup.prepare(prov, project_dir, command, *, repo_root=REPO_ROOT, key_path=None, environ=None, strata_cmd="strata", fetch_strata=None, build_settings=None, log=print) -> None`
  - `agent_setup.AgentSetupError`

- [ ] **Step 1: Создать общий фейк-провижионер**

`app/tests/env/fakes_code_index.py`:

```python
"""Фейковый Provisioner для тестов code-index и подготовки агента."""
from agentmon.backends import RunResult


class FakeProvisioner:
    def __init__(self):
        self.writes = {}
        self.runs = []
        self.detached = []
        self.copies = []
        self.dirs = []
        self.home = "/root"
        self.run_results = {}       # подстрока argv → RunResult

    def write_text(self, path, content):
        self.writes[path] = content

    def read_text(self, path):
        return self.writes.get(path, "")

    def exists(self, path):
        return path in self.writes

    def mkdirs(self, paths):
        self.dirs.extend(paths)

    def run(self, cmd, cwd=None, timeout=None, env=None):
        self.runs.append({"argv": list(cmd), "cwd": cwd, "env": dict(env or {})})
        joined = " ".join(cmd)
        if 'printf %s "$HOME"' in joined:
            return RunResult(0, self.home, "")
        for key, result in self.run_results.items():
            if key in joined:
                return result
        return RunResult(0, "", "")

    def exec_detached(self, argv, cwd=None, env=None):
        self.detached.append({"argv": list(argv), "cwd": cwd, "env": dict(env or {})})
        return RunResult(0, "", "")

    def copy_in(self, local_path, dst):
        self.copies.append((str(local_path), dst))
        return RunResult(0, "", "")
```

- [ ] **Step 2: Написать падающие тесты**

`app/tests/env/test_agent_setup.py`:

```python
import json
from pathlib import Path

import pytest

from agentmon.env import agent_setup
from agentmon.env.agent_setup import AgentSetupError
from env.fakes_code_index import FakeProvisioner


def _repo(tmp_path):
    d = tmp_path / "deploy" / "claude"
    d.mkdir(parents=True)
    (d / "claude-ds.sh").write_text(
        "#!/usr/bin/env sh\r\necho ds\r\n", encoding="utf-8")
    (d / "claude-local.sh").write_text(
        "#!/usr/bin/env sh\necho local\n", encoding="utf-8")
    return tmp_path


def test_container_command_replaces_host_path():
    assert agent_setup.container_command(
        '"/opt/My Tools/claude" --flag') == "claude --flag"


def test_container_command_keeps_wrapper_and_args():
    assert agent_setup.container_command("claude-ds --x") == "claude-ds --x"


def test_container_command_unknown_unchanged():
    assert agent_setup.container_command("my-agent --x") == "my-agent --x"


def test_prepare_claude_is_noop():
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude --x", repo_root=Path("/nowhere"))
    assert prov.writes == {} and prov.runs == []


def test_prepare_claude_ds_copies_wrapper_and_key(tmp_path):
    repo = _repo(tmp_path)
    key = tmp_path / "key"
    key.write_text("secret\n", encoding="utf-8")
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                        key_path=key, environ={})
    wrapper = prov.writes["/usr/local/bin/claude-ds"]
    assert "\r" not in wrapper
    assert prov.writes["/root/.config/deepseek/key"] == "secret\n"
    assert any(r["argv"] == ["chmod", "0755", "/usr/local/bin/claude-ds"]
               for r in prov.runs)
    assert any(r["argv"] == ["chmod", "0600", "/root/.config/deepseek/key"]
               for r in prov.runs)


def test_prepare_claude_ds_uses_env_token(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                        key_path=tmp_path / "missing", environ={"DEEPSEEK_API_KEY": "tok"})
    assert prov.writes["/root/.config/deepseek/key"] == "tok\n"


def test_prepare_claude_ds_without_key_raises(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    with pytest.raises(AgentSetupError, match="ключ DeepSeek"):
        agent_setup.prepare(prov, "/workspace", "claude-ds", repo_root=repo,
                            key_path=tmp_path / "missing", environ={})


def test_prepare_claude_local_writes_strata_settings(tmp_path):
    repo = _repo(tmp_path)
    prov = FakeProvisioner()
    seen = {}

    def fetch(cmd):
        seen["cmd"] = cmd
        return {"ANTHROPIC_MODEL": "m"}

    agent_setup.prepare(
        prov, "/workspace", "claude-local", repo_root=repo,
        fetch_strata=fetch, build_settings=lambda env: {"env": env})
    assert seen["cmd"] == "strata"
    text = prov.writes["/workspace/.claude/settings.local.json"]
    assert json.loads(text) == {"env": {"ANTHROPIC_MODEL": "m"}}
    assert "/usr/local/bin/claude-local" in prov.writes


def test_prepare_unknown_command_raises():
    prov = FakeProvisioner()
    with pytest.raises(AgentSetupError, match="поддерживаются"):
        agent_setup.prepare(prov, "/workspace", "other", repo_root=Path("/nowhere"))
```

- [ ] **Step 3: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_agent_setup.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'agentmon.env.agent_setup'`.

- [ ] **Step 4: Реализовать `agent_setup.py`**

`app/src/agentmon/env/agent_setup.py`:

```python
"""Подготовка агента внутри docker-контейнера: обёртка, ключ, Strata."""
from __future__ import annotations

import json
import os
import shlex
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
WRAPPERS = {"claude-ds": "claude-ds.sh", "claude-local": "claude-local.sh"}
CLAUDE_BASENAMES = {"claude", "claude.exe", "claude.cmd", "claude.bat"}


class AgentSetupError(RuntimeError):
    """Ошибка подготовки агента (сообщение — для пользователя)."""


def split_command(command: str) -> list[str]:
    cmd = (command or "").strip()
    if not cmd:
        raise AgentSetupError("пустая команда агента")
    posix = os.name != "nt" and "\\" not in cmd
    try:
        argv = shlex.split(cmd, posix=posix)
    except ValueError as exc:
        raise AgentSetupError(f"команда агента: {exc}") from None
    if not posix:
        argv = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] == '"' else a
                for a in argv]
    argv = [a for a in argv if a]
    if not argv:
        raise AgentSetupError("пустая команда агента")
    return argv


def _basename(executable: str) -> str:
    return executable.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]


def container_command(command: str) -> str:
    """Команда для docker exec: хостовый путь заменяется именем из образа."""
    argv = split_command(command)
    base = _basename(argv[0])
    if base.lower() in CLAUDE_BASENAMES:
        argv = ["claude", *argv[1:]]
    elif base in WRAPPERS:
        argv = [base, *argv[1:]]
    else:
        return command
    return " ".join(shlex.quote(a) for a in argv)


def container_home(prov) -> str:
    try:
        res = prov.run(["sh", "-c", 'printf %s "$HOME"'])
        home = (getattr(res, "stdout", "") or "").strip()
        if getattr(res, "returncode", 1) == 0 and home.startswith("/"):
            return home.rstrip("/") or "/root"
    except Exception:                                  # noqa: BLE001
        pass
    return "/root"


def _copy_wrapper(prov, *, name, repo_root, log):
    src = Path(repo_root) / "deploy" / "claude" / WRAPPERS[name]
    if not src.is_file():
        raise AgentSetupError(f"не найдена обёртка {src}")
    text = src.read_text(encoding="utf-8").replace("\r\n", "\n")
    dst = f"/usr/local/bin/{name}"
    prov.write_text(dst, text)
    res = prov.run(["chmod", "0755", dst])
    if getattr(res, "returncode", 1) != 0:
        raise AgentSetupError(
            f"не удалось сделать обёртку исполняемой: {dst}: "
            f"{(getattr(res, 'stderr', '') or '').strip()}")
    log(f"✓ обёртка агента: {dst}")


def _deepseek_token(*, key_path=None, environ=None) -> str:
    env = environ if environ is not None else os.environ
    token = (env.get("DEEPSEEK_API_KEY") or "").strip()
    if token:
        return token
    path = Path(key_path) if key_path is not None else (
        Path.home() / ".config" / "deepseek" / "key")
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if not token:
        raise AgentSetupError(
            "не найден ключ DeepSeek: задайте DEEPSEEK_API_KEY или положите "
            f"ключ в {path}")
    return token


def _write_key(prov, *, token, log):
    path = f"{container_home(prov)}/.config/deepseek/key"
    prov.write_text(path, token + "\n")
    res = prov.run(["chmod", "0600", path])
    if getattr(res, "returncode", 1) != 0:
        raise AgentSetupError(f"не удалось выставить права на ключ: {path}")
    log(f"✓ ключ DeepSeek: {path}")


def _write_strata_settings(prov, *, project_dir, strata_cmd, fetch_strata,
                           build_settings, log):
    env = fetch_strata(strata_cmd)
    settings = build_settings(env)
    path = f"{str(project_dir).rstrip('/')}/.claude/settings.local.json"
    prov.write_text(path, json.dumps(settings, ensure_ascii=False, indent=2) + "\n")
    log(f"✓ настройки Strata: {path}")


def prepare(prov, project_dir, command, *, repo_root=REPO_ROOT, key_path=None,
            environ=None, strata_cmd="strata", fetch_strata=None,
            build_settings=None, log=print) -> None:
    """Скопировать в контейнер всё, что нужно команде агента."""
    argv = split_command(command)
    base = _basename(argv[0])
    if base.lower() in CLAUDE_BASENAMES:
        log("✓ агент claude уже в образе")
        return
    if base not in WRAPPERS:
        raise AgentSetupError(
            "для docker-проекта поддерживаются команды claude, claude-ds, "
            f"claude-local (получено {base!r})")
    _copy_wrapper(prov, name=base, repo_root=repo_root, log=log)
    if base == "claude-ds":
        _write_key(prov, token=_deepseek_token(key_path=key_path,
                                               environ=environ), log=log)
        return
    if fetch_strata is None or build_settings is None:
        from .bench_setup import build_strata_settings, fetch_strata_env
        fetch_strata = fetch_strata or fetch_strata_env
        build_settings = build_settings or build_strata_settings
    _write_strata_settings(prov, project_dir=project_dir,
                           strata_cmd=strata_cmd,
                           fetch_strata=fetch_strata,
                           build_settings=build_settings, log=log)
```

- [ ] **Step 5: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_agent_setup.py -q`
Expected: `8 passed`.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/agent_setup.py app/tests/env/test_agent_setup.py app/tests/env/fakes_code_index.py
git commit -m "feat(env): подготовка обёртки агента и ключа в docker-контейнере

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Docker-бэкенд — тома, сеть, лицензии, copy_in, seed доверия

**Files:**
- Modify: `app/src/agentmon/backends/docker.py`
- Modify: `app/src/agentmon/backends/factory.py`
- Test: `app/tests/test_backend_docker.py`

**Interfaces:**
- Produces:
  - `_DockerContainer.exec_run(argv, cwd=None, timeout=None, env=None)`
  - `_DockerContainer.exec_detached(argv, cwd=None, env=None)`
  - `_DockerContainer.copy_in(local_path, dst) -> RunResult`
  - `DockerProvisioner(container, workdir=..., seed_trust_project=None)`
  - `DockerProvisioner.run(cmd, cwd=None, timeout=None, env=None)`
  - `DockerProvisioner.exec_detached(argv, cwd=None, env=None)`
  - `DockerProvisioner.copy_in(local_path, dst)`
  - `DockerBackend(project_path, *, claude_cmd, image=..., workdir=..., run=..., spawn_fn=..., home=None, docker_host=None, license_dir=None)`

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `app/tests/test_backend_docker.py`:

```python
# ---------------------------------------------------------------------------
# Docker-схема проекта: code-index том, лицензии, сеть, copy_in, seed trust
# ---------------------------------------------------------------------------

def test_exec_run_supports_env():
    fake = FakeRun()
    c = _make_container(fake, name="ai1c-env")
    c.exec_run(["sh", "-c", "echo $X"], env={"X": "1"})
    cmd = fake.called_with("docker exec")[0]
    assert "-e" in cmd and "X=1" in cmd
    assert cmd.index("-e") < cmd.index("ai1c-env")


def test_exec_detached_has_d_flag_and_env():
    fake = FakeRun()
    c = _make_container(fake, name="ai1c-det")
    c.exec_detached(["daemon"], env={"CODE_INDEX_HOME": "/ci"})
    cmd = fake.called_with("docker exec")[0]
    assert cmd[2] == "-d"
    assert "CODE_INDEX_HOME=/ci" in cmd


def test_copy_in_uses_docker_cp(tmp_path):
    fake = FakeRun()
    c = _make_container(fake, name="ai1c-cp")
    local = tmp_path / "bsl-indexer"
    local.write_bytes(b"bin")
    c.copy_in(str(local), "/code-index/bsl-indexer")
    cp = fake.called_with("docker cp")
    assert cp and cp[0][-2:] == [str(local), "ai1c-cp:/code-index/bsl-indexer"]


def test_provisioner_seed_trust_merges_json():
    class _TrustContainer(_FakeContainer):
        def __init__(self):
            super().__init__()
            self.set_result(RunResult(0, "/root\n", ""))          # echo $HOME
            self.set_result(RunResult(0, "", ""))                # test -e
            self.set_result(RunResult(0, '{"projects": {"/other": {}}}', ""))
            # exec_input → rc=0 по умолчанию

        def exec_run(self, argv, cwd=None, timeout=None, env=None):
            return super().exec_run(argv, cwd, timeout)

    container = _TrustContainer()
    prov = DockerProvisioner(container, seed_trust_project="/workspace")
    prov.mkdirs(["/workspace"])
    data = json.loads(container.input_calls[0]["data"].decode("utf-8"))
    assert data["projects"]["/workspace"]["hasTrustDialogAccepted"] is True
    assert "/other" in data["projects"]
    # повторный _ensure не пишет снова
    prov.mkdirs(["/workspace"])
    assert len(container.input_calls) == 1


def test_backend_container_spec_has_codeindex_and_network():
    fake = FakeRun(routes=[
        ("docker images -q", 0, "abc\n", ""),
        ("docker inspect", 1, "", "No such object"),
    ])

    def fake_spawn(cmd, cwd, env=None):
        return _FakePty(cmd, cwd)

    backend = DockerBackend("/workspace", claude_cmd="claude", run=fake,
                            spawn_fn=fake_spawn)
    backend.check()
    cmd = fake.called_with("docker run")[0]
    joined = " ".join(cmd)
    name = backend._container.name
    assert f"{name}-codeindex:/code-index" in joined
    assert f"{name}-claude:/root/.claude" in joined
    assert "HOME=/root" in joined
    assert "--network host" in joined


def test_backend_container_spec_license_bind(tmp_path):
    fake = FakeRun(routes=[
        ("docker images -q", 0, "abc\n", ""),
        ("docker inspect", 1, "", "No such object"),
    ])

    def fake_spawn(cmd, cwd, env=None):
        return _FakePty(cmd, cwd)

    lic = tmp_path / "licenses"
    lic.mkdir()
    backend = DockerBackend("/workspace", claude_cmd="claude", run=fake,
                            spawn_fn=fake_spawn, license_dir=str(lic))
    backend.check()
    joined = " ".join(fake.called_with("docker run")[0])
    assert f"{lic}:/var/1C/licenses" in joined


def test_remote_backend_no_host_network():
    fake = FakeRun(routes=[
        ("docker images -q", 0, "abc\n", ""),
        ("docker inspect", 1, "", "No such object"),
    ])

    def fake_spawn(cmd, cwd, env=None):
        return _FakePty(cmd, cwd)

    backend = DockerBackend("/workspace", claude_cmd="claude", run=fake,
                            spawn_fn=fake_spawn, docker_host="ssh://u@h")
    backend.check()
    assert "--network host" not in " ".join(fake.called_with("docker run")[0])


def test_windows_backend_no_host_network(monkeypatch):
    import agentmon.backends.docker as docker_mod
    monkeypatch.setattr(docker_mod.sys, "platform", "win32")
    fake = FakeRun(routes=[
        ("docker images -q", 0, "abc\n", ""),
        ("docker inspect", 1, "", "No such object"),
    ])

    def fake_spawn(cmd, cwd, env=None):
        return _FakePty(cmd, cwd)

    backend = DockerBackend("/workspace", claude_cmd="claude", run=fake,
                            spawn_fn=fake_spawn)
    backend.check()
    assert "--network host" not in " ".join(fake.called_with("docker run")[0])


def test_runner_normalizes_host_claude_path():
    runner, _, spawned = _make_runner(claude_cmd="claude --go")
    runner.start(_project(claude_cmd='"/opt/My Tools/claude" --flag'))
    assert "claude --flag" in spawned[0].cmd
    assert "/opt/My Tools" not in spawned[0].cmd
```

Не забыть добавить `import json` в начало файла рядом с `import subprocess`.

- [ ] **Step 2: Убедиться, что новые тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/test_backend_docker.py -q -k "env or detached or copy_in or seed or host_network or normalizes or license or spec"`
Expected: FAIL (`TypeError: exec_run() got an unexpected keyword argument 'env'` и др.).

- [ ] **Step 3: Расширить `_DockerContainer`**

В `__init__` заменить строку env — HOME должен быть задан явно (docker exec
не наследует окружение клиента, а образ может не задавать HOME):

```python
        self._env = {"DISPLAY": ":99", "HOME": "/root", **(env or {})}
```

В `app/src/agentmon/backends/docker.py` заменить `exec_run` и добавить методы после него:

```python
    def exec_run(self, argv: list[str], cwd: str | None = None,
                 timeout: float | None = None,
                 env: dict | None = None) -> RunResult:
        """Выполнить команду внутри контейнера через ``docker exec``."""
        tail = ["exec"]
        for key, value in (env or {}).items():
            tail += ["-e", f"{key}={value}"]
        if cwd:
            tail += ["-w", cwd]
        tail.append(self._name)
        tail.extend(argv)
        cmd = self._argv(tail)
        try:
            r = self._run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            stdout = (e.stdout or "") if isinstance(e.stdout, str) else ""
            stderr = (e.stderr or "") if isinstance(e.stderr, str) else ""
            return RunResult(124, stdout, stderr + "\n<timeout>")
        return RunResult(
            returncode=r.returncode,
            stdout=(r.stdout or ""),
            stderr=(r.stderr or ""),
        )

    def exec_detached(self, argv: list[str], cwd: str | None = None,
                      env: dict | None = None) -> RunResult:
        """Запустить процесс в контейнере detached (``docker exec -d``)."""
        tail = ["exec", "-d"]
        for key, value in (env or {}).items():
            tail += ["-e", f"{key}={value}"]
        if cwd:
            tail += ["-w", cwd]
        tail.append(self._name)
        tail.extend(argv)
        r = self._run(self._argv(tail), capture_output=True, text=True)
        return RunResult(
            returncode=r.returncode,
            stdout=(r.stdout or ""),
            stderr=(r.stderr or ""),
        )

    def copy_in(self, local_path, dst: str) -> RunResult:
        """Скопировать файл с хоста в контейнер (``docker cp``)."""
        parent = posixpath.dirname(dst)
        if parent:
            self.exec_run(["mkdir", "-p", parent])
        r = self._run(
            self._argv(["cp", str(local_path), f"{self._name}:{dst}"]),
            capture_output=True, text=True)
        return RunResult(
            returncode=r.returncode,
            stdout=(r.stdout or ""),
            stderr=(r.stderr or ""),
        )
```

- [ ] **Step 4: Расширить `DockerProvisioner`**

Изменить `__init__`, `_ensure`, добавить `_seed_trust`, `exec_detached`, `copy_in`, и передачу env в `run`:

```python
    def __init__(self, container: _DockerContainer, workdir: str = DEFAULT_WORKDIR,
                 seed_trust_project: str | None = None):
        self._container = container
        self._workdir = workdir
        self._seed_project = seed_trust_project
        self._trust_seeded = False

    def _ensure(self) -> None:
        """Убедиться, что контейнер запущен (вызывается в начале каждой операции)."""
        self._container.ensure()
        self._seed_trust()

    def _seed_trust(self) -> None:
        """Отметить каталог проекта доверенным для claude (best-effort)."""
        if self._trust_seeded or not self._seed_project:
            return
        try:
            res = self._container.exec_run(["sh", "-c", 'printf %s "$HOME"'])
            home = (res.stdout or "").strip() or "/root"
            path = f"{home.rstrip('/')}/.claude.json"
            data = {}
            if self._container.exec_run(["test", "-e", path]).returncode == 0:
                raw = self._container.exec_run(["cat", path]).stdout or ""
                try:
                    data = json.loads(raw)
                except ValueError:
                    data = {}
            if not isinstance(data, dict):
                data = {}
            projects = data.setdefault("projects", {})
            if not isinstance(projects, dict):
                projects = data["projects"] = {}
            entry = projects.setdefault(str(self._seed_project), {})
            if not isinstance(entry, dict):
                entry = projects[str(self._seed_project)] = {}
            entry["hasTrustDialogAccepted"] = True
            payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            res = self._container.exec_input(
                ["sh", "-c", f"cat > {shlex.quote(path)}"],
                payload.encode("utf-8"))
            if res.returncode == 0:
                self._trust_seeded = True
        except Exception:                                  # noqa: BLE001
            pass

    def run(self, cmd: list[str], cwd: str | None = None,
            timeout: float | None = None,
            env: dict | None = None) -> RunResult:
        """Выполнить команду внутри контейнера. При timeout → RunResult(124, ...)."""
        self._ensure()
        if env is None:
            return self._container.exec_run(cmd, cwd, timeout=timeout)
        return self._container.exec_run(cmd, cwd, timeout=timeout, env=env)

    def exec_detached(self, argv: list[str], cwd: str | None = None,
                      env: dict | None = None) -> RunResult:
        self._ensure()
        return self._container.exec_detached(argv, cwd, env=env)

    def copy_in(self, local_path, dst: str) -> None:
        self._ensure()
        result = self._container.copy_in(local_path, dst)
        if result.returncode != 0:
            self._raise_if_down(result, f"copy_in {dst}")
```

Нужен `import json` в шапке файла (добавить рядом с `import hashlib`).

- [ ] **Step 5: Обновить `DockerBackend` и `DockerRunner`**

В `DockerBackend.__init__` добавить параметр `license_dir: str | None = None` и собрать тома/флаги:

```python
    def __init__(
        self,
        project_path: str,
        *,
        claude_cmd: str,
        image: str = DEFAULT_IMAGE,
        workdir: str = DEFAULT_WORKDIR,
        run=subprocess.run,
        spawn_fn=pty_process.spawn,
        home: str | None = None,
        docker_host: str | None = None,
        license_dir: str | None = None,
    ):
        name = container_name(project_path)
        volume = f"{name}-work"
        claude_volume = f"{name}-claude"
        extra_volumes = [f"{name}-codeindex:/code-index"]
        if license_dir:
            extra_volumes.append(f"{license_dir}:/var/1C/licenses")
        extra_run_args = []
        if os.name == "posix" and sys.platform.startswith("linux") and not docker_host:
            extra_run_args += ["--network", "host"]
        self.key = f"docker|{docker_host_token(docker_host)}|{project_path}"
        self._container = _DockerContainer(
            name,
            image,
            workdir=workdir,
            volume=volume,
            claude_volume=claude_volume,
            run=run,
            docker_host=docker_host,
            extra_volumes=extra_volumes,
            extra_run_args=extra_run_args,
        )
        self.runner = DockerRunner(self._container, claude_cmd, workdir=workdir, spawn_fn=spawn_fn)
        self.files = DockerFiles(self._container, home=home)
        self.provisioner = DockerProvisioner(
            self._container, workdir=workdir,
            seed_trust_project=project_path)
```

В шапке `docker.py` добавить `import sys` и `from ..env.agent_setup import container_command` (импорт на уровне модуля).

В `DockerRunner.start` заменить формирование команды:

```python
        cmd = container_command(project.claude_cmd or self.claude_cmd)
```

- [ ] **Step 6: Прокинуть `license_dir` из реестра**

`app/src/agentmon/backends/factory.py`, `docker_factory`:

```python
        self._docker_factory = docker_factory or (
            lambda project: DockerBackend(
                project.path,
                claude_cmd=claude_cmd,
                image=(project.conn or {}).get("image") or DEFAULT_IMAGE,
                license_dir=(project.conn or {}).get("license_dir"),
                docker_host=docker_host_from_conn(project.conn),
            )
        )
```

- [ ] **Step 7: Обновить фейк-контейнер в тестах под env/detached/copy_in**

В `app/tests/test_backend_docker.py` в классе `_FakeContainer`:

```python
    def __init__(self, default_rc=0, default_stdout="", default_stderr=""):
        ...
        self.detached_calls = []
        self.copy_calls = []

    def exec_run(self, argv, cwd=None, timeout=None, env=None):
        call = {"argv": list(argv), "cwd": cwd}
        if env is not None:
            call["env"] = dict(env)
        self.exec_calls.append(call)
        return self._pop_result()

    def exec_detached(self, argv, cwd=None, env=None):
        self.detached_calls.append({"argv": list(argv), "env": dict(env or {})})
        return self._pop_result()

    def copy_in(self, local_path, dst):
        self.copy_calls.append((str(local_path), dst))
        return self._pop_result()
```

(Остальные поля и методы класса сохранить.)

- [ ] **Step 8: Прогнать тесты файла**

Run: `cd app && ../.venv/bin/python -m pytest tests/test_backend_docker.py -q`
Expected: все тесты проходят.

- [ ] **Step 9: Коммит**

```bash
git add app/src/agentmon/backends/docker.py app/src/agentmon/backends/factory.py app/tests/test_backend_docker.py
git commit -m "feat(docker): тома code-index, лицензии, env/detached/copy_in и seed доверия

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Развёртывание и ожидание code-index внутри контейнера

**Files:**
- Create: `app/src/agentmon/env/code_index_docker.py`
- Test: `app/tests/env/test_code_index_docker.py`

**Interfaces:**
- Consumes: `DockerProvisioner.run(..., env=...)`, `exec_detached`, `copy_in` (Task 2); `FakeProvisioner` (Task 1).
- Produces:
  - `code_index_docker.deploy(prov, *, code_index_dir, catalog_dir, alias, port, download=download_binary, log=print) -> Iterator[str]`
  - `code_index_docker.wait_ready(prov, *, code_index_dir, port, wait_minutes=360, status=None, alive=None, log_tail=None, sleep=time.sleep, clock=time.monotonic, log=print)`
  - `code_index_docker.stop(prov, code_index_dir)`

- [ ] **Step 1: Написать падающие тесты**

`app/tests/env/test_code_index_docker.py`:

```python
import json

import pytest

from agentmon.env import code_index_docker
from env.fakes_code_index import FakeProvisioner


class _Err(RuntimeError):
    pass


def _download(tmp, log=None, platform_name=None):
    assert platform_name == "linux"
    from pathlib import Path
    path = Path(tmp) / "bsl-indexer"
    path.write_bytes(b"bin")
    return path


def test_deploy_installs_binary_and_starts_processes():
    prov = FakeProvisioner()
    lines = list(code_index_docker.deploy(
        prov, code_index_dir="/code-index", catalog_dir="/workspace/src/cf",
        alias="demo", port=8005, download=_download))
    assert any("бинарь установлен" in line for line in lines)
    assert prov.copies and prov.copies[0][1] == "/code-index/bsl-indexer"
    assert ["chmod", "+x", "/code-index/bsl-indexer"] in [r["argv"] for r in prov.runs]
    toml = prov.writes["/code-index/daemon.toml"]
    assert 'alias = "demo"' in toml and 'path = "/workspace/src/cf"' in toml
    assert len(prov.detached) == 2
    assert prov.detached[0]["env"]["CODE_INDEX_HOME"] == "/code-index"
    assert prov.detached[1]["env"]["MCP_HTTP_PORT"] == "8005"


def test_deploy_keeps_existing_paths():
    prov = FakeProvisioner()
    prov.writes["/code-index/bsl-indexer"] = "bin"
    prov.writes["/code-index/daemon.toml"] = (
        '[daemon]\nhttp_host = "127.0.0.1"\n\n'
        '[[paths]]\npath = "/other/src/cf"\nalias = "other"\nlanguage = "bsl"\n')
    list(code_index_docker.deploy(
        prov, code_index_dir="/code-index", catalog_dir="/workspace/src/cf",
        alias="demo", port=8005, download=_download))
    toml = prov.writes["/code-index/daemon.toml"]
    assert 'alias = "other"' in toml and 'alias = "demo"' in toml
    assert not prov.copies


def test_wait_ready_success():
    calls = {"n": 0}

    def status():
        calls["n"] += 1
        return {"paths": [{"path": "/workspace/src/cf", "status": "ready"}]}

    code_index_docker.wait_ready(
        FakeProvisioner(), code_index_dir="/code-index", port=8005,
        status=status, alive=lambda: True, log_tail=lambda name: "",
        sleep=lambda _s: None, clock=lambda: 0.0)
    assert calls["n"] == 1


def test_wait_ready_error_status_raises():
    def status():
        return {"paths": [{"path": "/workspace/src/cf", "status": "error",
                           "error": "boom"}]}

    with pytest.raises(Exception, match="boom"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            status=status, alive=lambda: True, log_tail=lambda name: "",
            sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_dead_process_raises_with_logs():
    with pytest.raises(Exception, match="завершился"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            status=lambda: None, alive=lambda: False,
            log_tail=lambda name: f"{name}-tail",
            sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_timeout():
    times = iter([0.0, 0.0, 1.0])
    with pytest.raises(Exception, match="не проиндексировал"):
        code_index_docker.wait_ready(
            FakeProvisioner(), code_index_dir="/code-index", port=8005,
            wait_minutes=1, status=lambda: {"paths": []}, alive=lambda: True,
            log_tail=lambda name: "", sleep=lambda _s: None,
            clock=lambda: next(times, 10_000.0))


def test_stop_pkills_bsl_indexer():
    prov = FakeProvisioner()
    code_index_docker.stop(prov, "/code-index")
    joined = " ".join(prov.runs[-1]["argv"])
    assert "pkill" in joined and "bsl-indexer" in joined
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_code_index_docker.py -q`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Реализовать модуль**

`app/src/agentmon/env/code_index_docker.py`:

```python
"""Нативный code-index внутри docker-контейнера проекта."""
from __future__ import annotations

import json
import shlex
import shutil
import tempfile
import time
from pathlib import Path

from .code_index_release import download_binary
from .code_index_toml import ensure_sections, merge_path

BINARY = "bsl-indexer"
WAIT_MINUTES = 360


def _ci(path) -> str:
    return str(path).rstrip("/")


def _binary(ci: str) -> str:
    return f"{ci}/{BINARY}"


def _stop_processes(prov) -> None:
    try:
        prov.run(["sh", "-c", "pkill -f '[b]sl-indexer' || true"])
    except Exception:                                  # noqa: BLE001
        pass


def _spawn(prov, ci: str, tail: str, log_name: str,
           env: dict | None = None) -> None:
    argv = ["sh", "-c",
            f"cd {shlex.quote(ci)} && ./{BINARY} {tail} "
            f">> {log_name}.log 2>&1"]
    result = prov.exec_detached(argv, env={"CODE_INDEX_HOME": ci, **(env or {})})
    if getattr(result, "returncode", 1) != 0:
        raise RuntimeError(
            f"code-index не запустился ({tail}): "
            f"{(getattr(result, 'stderr', '') or '').strip()}")


def deploy(prov, *, code_index_dir, catalog_dir, alias, port,
           download=download_binary, log=print):
    """Развернуть/обновить сервис code-index внутри контейнера."""
    ci = _ci(code_index_dir)
    prov.mkdirs([ci])
    yield f"▶ code-index в контейнере: {ci} (alias={alias}, порт {port})"
    if not prov.exists(_binary(ci)):
        tmp = tempfile.mkdtemp(prefix="bsl-indexer-")
        try:
            buf = []
            binary = download(tmp, log=buf.append, platform_name="linux")
            yield from buf
            prov.copy_in(str(binary), _binary(ci))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        prov.run(["chmod", "+x", _binary(ci)])
        yield "✓ бинарь установлен в контейнер"
    toml_path = f"{ci}/daemon.toml"
    text = prov.read_text(toml_path) if prov.exists(toml_path) else ""
    text = merge_path(text, alias=alias, path=str(catalog_dir))
    text = ensure_sections(text, int(port))
    prov.write_text(toml_path, text)
    yield f"✓ daemon.toml: alias={alias}, path={catalog_dir}"
    _stop_processes(prov)
    _spawn(prov, ci, "daemon run", "daemon")
    _spawn(prov, ci,
           f"serve --transport http --host 127.0.0.1 --port {int(port)} "
           f"--config {toml_path}", "serve",
           env={"MCP_HTTP_HOST": "127.0.0.1", "MCP_HTTP_PORT": str(int(port))})
    yield f"✓ code-index запущен в контейнере, порт {port}"


def _status(prov, ci: str):
    try:
        res = prov.run([_binary(ci), "daemon", "status", "--json"],
                       env={"CODE_INDEX_HOME": ci})
    except Exception:                                  # noqa: BLE001
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def _alive(prov) -> bool:
    try:
        res = prov.run(["sh", "-c",
                        "pgrep -f '[b]sl-indexer' >/dev/null && echo y"])
    except Exception:                                  # noqa: BLE001
        return False
    return (getattr(res, "stdout", "") or "").strip() == "y"


def _tail(prov, path: str) -> str:
    try:
        res = prov.run(["sh", "-c", 'tail -n 15 "$1" 2>/dev/null', "sh", path])
    except Exception:                                  # noqa: BLE001
        return ""
    return (getattr(res, "stdout", "") or "").strip()


def wait_ready(prov, *, code_index_dir, port, wait_minutes=WAIT_MINUTES,
               status=None, alive=None, log_tail=None,
               sleep=time.sleep, clock=time.monotonic, log=print) -> None:
    """Дождаться готовности индекса внутри контейнера."""
    ci = _ci(code_index_dir)
    status = status or (lambda: _status(prov, ci))
    alive = alive or (lambda: _alive(prov))
    log_tail = log_tail or (lambda name: _tail(prov, f"{ci}/{name}.log"))
    deadline = clock() + wait_minutes * 60
    while True:
        data = status()
        paths = (data or {}).get("paths") or []
        for p in paths:
            if p.get("status") == "error":
                raise RuntimeError(
                    f"code-index: ошибка индексации {p.get('path', '?')}: "
                    f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
        if not alive():
            raise RuntimeError(
                "code-index в контейнере завершился; последние строки логов:\n"
                f"--- serve.log ---\n{log_tail('serve') or '(пусто)'}\n"
                f"--- daemon.log ---\n{log_tail('daemon') or '(пусто)'}")
        ready = bool(paths) and all(p.get("status") == "ready" for p in paths)
        if ready:
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if clock() >= deadline:
            raise RuntimeError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {ci}/daemon.log в контейнере")
        sleep(5)


def stop(prov, code_index_dir) -> None:
    """Погасить bsl-indexer внутри контейнера (best-effort)."""
    _stop_processes(prov)
```

- [ ] **Step 4: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_code_index_docker.py -q`
Expected: `7 passed`.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/code_index_docker.py app/tests/env/test_code_index_docker.py
git commit -m "feat(code-index): развёртывание bsl-indexer внутри docker-контейнера

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Code-index проекта — валидация, порт, карточка, ожидание local

**Files:**
- Create: `app/src/agentmon/env/code_index_project.py`
- Test: `app/tests/env/test_code_index_project.py`

**Interfaces:**
- Consumes: `code_index_docker.deploy/wait_ready/stop` (Task 3), `code_index_local.deploy_local/read_service_port/service_names`, `McpRepo`.
- Produces:
  - `CodeIndexRequest(catalog_dir: str, code_index_dir: str)`
  - `CodeIndexError`
  - `WAIT_MINUTES = 360`
  - `validate_request(backend, project_dir, request) -> CodeIndexRequest`
  - `pick_port(read_port, *, tcp_ok=default_tcp_ok, host_check=True, start=8005) -> int`
  - `pick_port_for_local(code_index_dir, *, tcp_ok=default_tcp_ok) -> int`
  - `container_service_port(prov, code_index_dir) -> int | None`
  - `resolve_card(mcp_repo, *, project_id, project_name, backend, request, port) -> tuple[int, McpSelection, bool]`
  - `service_is_new(backend, *, prov=None, code_index_dir) -> bool`
  - `deploy(backend, *, prov=None, code_index_dir, catalog_dir, project_name, port, mid=None, log=print) -> Iterator[str]`
  - `wait_ready(backend, *, prov=None, code_index_dir, port, wait_minutes=WAIT_MINUTES, ...) -> None`
  - `stop_new_service(backend, *, prov=None, code_index_dir) -> None`

- [ ] **Step 1: Написать падающие тесты**

`app/tests/env/test_code_index_project.py`:

```python
import pytest

from agentmon.env import code_index_project
from agentmon.env.code_index_project import (
    CodeIndexError, CodeIndexRequest, pick_port, resolve_card, validate_request)
from env.fakes_code_index import FakeProvisioner


class _Repo:
    def __init__(self):
        self.rows = []
        self.links = {}

    def list(self):
        return list(self.rows)

    def add(self, **fields):
        mid = len(self.rows) + 1
        row = {"id": mid, **fields}
        self.rows.append(row)
        return mid

    def for_project(self, pid):
        ids = self.links.get(pid, [])
        return [r for r in self.rows if r["id"] in ids]

    def set_for_project(self, pid, ids):
        self.links[pid] = list(ids)


def test_validate_local_absolute_and_outside():
    req = validate_request("local", "/work/demo",
                           CodeIndexRequest("/work/demo/src/cf",
                                            "/work/demo-code-index"))
    assert req.code_index_dir.endswith("demo-code-index")
    with pytest.raises(CodeIndexError, match="абсолютным"):
        validate_request("local", "/work/demo",
                         CodeIndexRequest("src/cf", "/work/demo-code-index"))
    with pytest.raises(CodeIndexError, match="внутри"):
        validate_request("local", "/work/demo",
                         CodeIndexRequest("/work/demo/src/cf", "/work/demo/ci"))


def test_validate_docker_paths():
    req = validate_request("docker", "/workspace",
                           CodeIndexRequest("/workspace/src/cf", "/code-index"))
    assert req.code_index_dir == "/code-index"
    with pytest.raises(CodeIndexError, match="внутри"):
        validate_request("docker", "/workspace",
                         CodeIndexRequest("/workspace/src/cf", "/workspace/ci"))
    with pytest.raises(CodeIndexError, match="только для local"):
        validate_request("ssh", "/workspace",
                         CodeIndexRequest("/workspace/src/cf", "/code-index"))


def test_pick_port_reads_service_json(tmp_path):
    assert pick_port(lambda: 8010, host_check=False) == 8010


def test_pick_port_first_free():
    busy = {"http://127.0.0.1:8005", "http://127.0.0.1:8006"}
    port = pick_port(lambda: None, tcp_ok=lambda url: url in busy)
    assert port == 8007


def test_pick_port_no_host_check():
    assert pick_port(lambda: None, host_check=False) == 8005


def test_pick_port_exhausted():
    with pytest.raises(CodeIndexError, match="свободный порт"):
        pick_port(lambda: None, tcp_ok=lambda url: True)


def test_resolve_card_creates_and_reuses():
    repo = _Repo()
    req = CodeIndexRequest("/work/demo/src/cf", "/work/demo-code-index")
    mid, selection, created = resolve_card(
        repo, project_id=7, project_name="demo", backend="local",
        request=req, port=8005)
    assert created and mid == 1 and selection.id == "code-index"
    assert selection.catalog_dir == req.catalog_dir
    assert "code_index" in selection.connection
    mid2, _, created2 = resolve_card(
        repo, project_id=8, project_name="demo", backend="local",
        request=req, port=8005)
    assert mid2 == mid and created2 is False
    mid3, sel3, created3 = resolve_card(
        repo, project_id=9, project_name="other", backend="local",
        request=req, port=8005)
    assert created3 and mid3 != mid
    assert repo.rows[-1]["name"] == "other: code_index"


def test_resolve_card_docker_standard_key():
    repo = _Repo()
    req = CodeIndexRequest("/workspace/src/cf", "/code-index")
    _, selection, _ = resolve_card(
        repo, project_id=1, project_name="demo", backend="docker",
        request=req, port=8005)
    assert selection.id == "code-index-docker"
    assert repo.rows[0]["standard_key"] == "code-index-docker"
    assert repo.rows[0]["kind"] == "docker"


def test_container_service_port_reads_json():
    prov = FakeProvisioner()
    prov.writes["/code-index/service.json"] = '{"port": 8011}'
    assert code_index_project.container_service_port(prov, "/code-index") == 8011
    prov.writes["/code-index/service.json"] = "bad"
    assert code_index_project.container_service_port(prov, "/code-index") is None


def test_wait_ready_local_success():
    code_index_project.wait_ready_local(
        "/ci", port=8005,
        status=lambda ci: {"paths": [{"path": "/cf", "status": "ready"}]},
        tcp_ok=lambda url: True, sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_local_error():
    with pytest.raises(CodeIndexError, match="ошибка индексации"):
        code_index_project.wait_ready_local(
            "/ci", port=8005,
            status=lambda ci: {"paths": [{"path": "/cf", "status": "error",
                                          "error": "bad"}]},
            tcp_ok=lambda url: True, sleep=lambda _s: None, clock=lambda: 0.0)


def test_wait_ready_local_timeout():
    times = iter([0.0, 0.0, 10_000.0])
    with pytest.raises(CodeIndexError, match="не проиндексировал"):
        code_index_project.wait_ready_local(
            "/ci", port=8005, wait_minutes=1,
            status=lambda ci: {"paths": []}, tcp_ok=lambda url: True,
            sleep=lambda _s: None, clock=lambda: next(times, 10_000.0))
```

Удалить неиспользуемые импорты (`posixpath`, `McpSelection`), если линтер не нужен — в репозитории нет строгого линтера, но лучше не оставлять.

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_code_index_project.py -q`
Expected: FAIL — модуля нет.

- [ ] **Step 3: Реализовать модуль**

`app/src/agentmon/env/code_index_project.py`:

```python
"""Code-index проекта: валидация, порт, карточка MCP, локальное ожидание."""
from __future__ import annotations

import json
import os
import posixpath
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from . import autostart, code_index_local
from .code_index_docker import deploy as docker_deploy
from .code_index_docker import stop as docker_stop
from .code_index_docker import wait_ready as docker_wait_ready
from .code_index_release import existing_binary
from .config_schema import McpSelection
from .mcp_types import get_type
from .net_probe import default_tcp_ok
from ..paths import same_path

WAIT_MINUTES = 360
PORT_START = 8005
PORT_TRIES = 100
LOCAL_KEY = "code-index"
DOCKER_KEY = "code-index-docker"


class CodeIndexError(RuntimeError):
    """Ошибка code-index (сообщение — для пользователя)."""


@dataclass(frozen=True)
class CodeIndexRequest:
    catalog_dir: str
    code_index_dir: str


def validate_request(backend: str, project_dir: str,
                     request: CodeIndexRequest) -> CodeIndexRequest:
    if backend not in ("local", "docker"):
        raise CodeIndexError(
            "code index поддерживается только для local и docker")
    catalog = (request.catalog_dir or "").strip()
    ci = (request.code_index_dir or "").strip()
    if not catalog or not ci:
        raise CodeIndexError(
            "заполните «Каталог кодовой базы» и «Каталог code_index»")
    if backend == "local":
        if not Path(catalog).is_absolute():
            raise CodeIndexError("«Каталог кодовой базы» должен быть абсолютным")
        if not Path(ci).is_absolute():
            raise CodeIndexError("«Каталог code_index» должен быть абсолютным")
        project = Path(project_dir).resolve()
        ci_real = Path(ci).resolve()
        if ci_real == project or project in ci_real.parents:
            raise CodeIndexError(
                "«Каталог code_index» не должен находиться внутри каталога проекта")
    else:
        if not catalog.startswith("/") or not ci.startswith("/"):
            raise CodeIndexError(
                "для docker пути должны быть абсолютными (начинаться с /)")
        project = posixpath.normpath(project_dir)
        ci_norm = posixpath.normpath(ci)
        if ci_norm == project or ci_norm.startswith(project.rstrip("/") + "/"):
            raise CodeIndexError(
                "«Каталог code_index» не должен находиться внутри каталога проекта")
    return CodeIndexRequest(catalog, ci)


def pick_port(read_port, *, tcp_ok=default_tcp_ok, host_check=True,
              start=PORT_START) -> int:
    port = read_port()
    if port is not None:
        return int(port)
    if not host_check:
        return int(start)
    for port in range(int(start), int(start) + PORT_TRIES):
        if not tcp_ok(f"http://127.0.0.1:{port}"):
            return port
    raise CodeIndexError(
        f"не найден свободный порт в диапазоне {start}-{start + PORT_TRIES - 1}")


def pick_port_for_local(code_index_dir, *, tcp_ok=default_tcp_ok) -> int:
    return pick_port(lambda: code_index_local.read_service_port(code_index_dir),
                     tcp_ok=tcp_ok)


def container_service_port(prov, code_index_dir) -> int | None:
    path = posixpath.join(str(code_index_dir).rstrip("/"), "service.json")
    if not prov.exists(path):
        return None
    try:
        data = json.loads(prov.read_text(path))
    except (OSError, ValueError):
        return None
    port = data.get("port") if isinstance(data, dict) else None
    return port if isinstance(port, int) and 1 <= port <= 65535 else None


def _same_path(backend: str, left, right) -> bool:
    if backend == "docker":
        return posixpath.normpath(str(left or "")) == posixpath.normpath(str(right or ""))
    return same_path(str(left or ""), str(right or ""))


def _connection(port: int) -> str:
    entry = json.dumps({"type": "http",
                        "url": f"http://localhost:{int(port)}/mcp"},
                       ensure_ascii=False)
    return f'"code_index": {entry}'


def _selection(*, backend, request, port, project_name) -> McpSelection:
    return McpSelection(
        id=LOCAL_KEY if backend == "local" else DOCKER_KEY,
        enabled=True,
        mode="managed",
        connection=_connection(port),
        catalog_dir=request.catalog_dir,
        project_name=project_name,
        code_index_dir=request.code_index_dir,
    )


def _unique_name(repo, base: str) -> str:
    names = {row.get("name") for row in repo.list()}
    name, index = base, 2
    while name in names:
        name = f"{base} {index}"
        index += 1
    return name


def _connection_equal(left, right) -> bool:
    try:
        return json.loads("{" + (left or "") + "}") == json.loads("{" + right + "}")
    except (TypeError, ValueError):
        return (left or "") == right


def resolve_card(mcp_repo, *, project_id: int, project_name: str,
                 backend: str, request: CodeIndexRequest,
                 port: int) -> tuple[int, McpSelection, bool]:
    key = LOCAL_KEY if backend == "local" else DOCKER_KEY
    kind = "local" if backend == "local" else "docker"
    connection = _connection(port)
    for row in mcp_repo.list():
        if row.get("standard_key") != key:
            continue
        if not _connection_equal(row.get("connection_json"), connection):
            continue
        if not _same_path(backend, row.get("catalog_dir"), request.catalog_dir):
            continue
        if (row.get("project_name") or "") != project_name:
            continue
        if not _same_path(backend, row.get("code_index_dir"),
                          request.code_index_dir):
            continue
        selection = _selection(backend=backend, request=request, port=port,
                               project_name=project_name)
        return row["id"], selection, False
    mid = mcp_repo.add(
        name=_unique_name(mcp_repo, f"{project_name}: code_index"),
        purpose=get_type(LOCAL_KEY).defaults["purpose"],
        kind=kind, standard_key=key, connection_json=connection,
        port=int(port), mcp_name="code_index", url="localhost",
        catalog_dir=request.catalog_dir, project_name=project_name,
        code_index_dir=request.code_index_dir,
    )
    selection = _selection(backend=backend, request=request, port=port,
                           project_name=project_name)
    return mid, selection, True


def service_is_new(backend: str, *, prov=None, code_index_dir) -> bool:
    if backend == "docker":
        return container_service_port(prov, code_index_dir) is None
    return code_index_local.read_service_port(code_index_dir) is None


def deploy(backend: str, *, prov=None, code_index_dir, catalog_dir,
           project_name, port, mid=None, log=print):
    if backend == "local":
        return code_index_local.deploy_local(
            code_index_dir=code_index_dir, catalog_dir=catalog_dir,
            project_name=project_name, port=port, mid=mid)
    return docker_deploy(prov, code_index_dir=code_index_dir,
                         catalog_dir=catalog_dir, alias=project_name,
                         port=port, log=log)


def local_status(code_index_dir, *, binary_finder=existing_binary,
                 run=subprocess.run):
    binary = binary_finder(Path(code_index_dir))
    if binary is None:
        return None
    env = {**os.environ, "CODE_INDEX_HOME": str(code_index_dir)}
    try:
        res = run([str(binary), "daemon", "status", "--json"],
                  env=env, capture_output=True, text=True)
    except OSError:
        return None
    if getattr(res, "returncode", 1) != 0:
        return None
    try:
        return json.loads(getattr(res, "stdout", "") or "")
    except (TypeError, ValueError):
        return None


def wait_ready_local(code_index_dir, *, port, wait_minutes=WAIT_MINUTES,
                     status=local_status, tcp_ok=default_tcp_ok,
                     sleep=time.sleep, clock=time.monotonic, log=print) -> None:
    deadline = clock() + wait_minutes * 60
    while True:
        data = status(code_index_dir)
        paths = (data or {}).get("paths") or []
        for p in paths:
            if p.get("status") == "error":
                raise CodeIndexError(
                    f"code-index: ошибка индексации {p.get('path', '?')}: "
                    f"{p.get('error') or p.get('message') or 'ошибка индексации'}")
        ready = bool(paths) and all(p.get("status") == "ready" for p in paths)
        if ready and tcp_ok(f"http://127.0.0.1:{int(port)}"):
            log("✓ code-index готов: " + ", ".join(
                p.get("path", "?") for p in paths))
            return
        if clock() >= deadline:
            raise CodeIndexError(
                f"code-index не проиндексировал базу за {wait_minutes} мин; "
                f"смотрите {code_index_dir}/daemon.log")
        sleep(5)


def wait_ready(backend: str, *, prov=None, code_index_dir, port,
               wait_minutes=WAIT_MINUTES, log=print) -> None:
    if backend == "docker":
        docker_wait_ready(prov, code_index_dir=code_index_dir, port=port,
                          wait_minutes=wait_minutes, log=log)
    else:
        wait_ready_local(code_index_dir, port=port,
                         wait_minutes=wait_minutes, log=log)


def stop_new_service(backend: str, *, prov=None, code_index_dir) -> None:
    if backend == "docker":
        docker_stop(prov, code_index_dir)
        return
    daemon_name, serve_name = code_index_local.service_names(code_index_dir)
    for name in (serve_name, daemon_name):
        try:
            autostart.stop(name, state_dir=str(code_index_dir))
        except Exception:                              # noqa: BLE001
            pass
    # Новый сервис снят: без service.json повторный запуск снова first=True,
    # а не попытка restart несуществующих юнитов.
    try:
        (Path(code_index_dir) / code_index_local.SERVICE_FILE).unlink()
    except OSError:
        pass
```

- [ ] **Step 4: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_code_index_project.py -q`
Expected: `12 passed`.

- [ ] **Step 5: Коммит**

```bash
git add app/src/agentmon/env/code_index_project.py app/tests/env/test_code_index_project.py
git commit -m "feat(code-index): карточка MCP, порт и мульти-база в мастере проекта

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Скрытый вид MCP `code-index-docker` без кнопки развёртывания

**Files:**
- Modify: `app/src/agentmon/env/mcp_types.py`
- Modify: `app/src/agentmon/env/mcp_catalog.py`
- Modify: `app/web/mcp.js`
- Test: `app/tests/env/test_mcp_types.py`, `app/tests/env/test_mcp_page.py`

**Interfaces:**
- Produces: `get_type("code-index-docker")`; карточка с этим `standard_key` не показывает действий.

- [ ] **Step 1: Написать падающие тесты**

В `app/tests/env/test_mcp_types.py`:

```python
def test_code_index_docker_is_hidden_without_action():
    from agentmon.env.mcp_types import get_type
    t = get_type("code-index-docker")
    assert t.hidden is True
    assert t.action is None
    assert t.defaults["mcp_name"] == "code_index"
```

В `app/tests/env/test_mcp_page.py`:

```python
def test_js_does_not_offer_deploy_for_docker_code_index(tmp_path):
    js = _client(tmp_path).get("/static/mcp.js").text
    assert "code-index-docker" in js
    idx = js.index("code-index-docker")
    assert "managedCodeIndex" in js[idx - 400: idx + 400]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_mcp_types.py tests/env/test_mcp_page.py -q -k "code_index_docker"`
Expected: FAIL (`KeyError: 'code-index-docker'`, в JS нет строки).

- [ ] **Step 3: Добавить вид в `mcp_types.py`**

После `McpType(key="code-index", ...)` добавить:

```python
    McpType(
        key="code-index-docker",
        title="Индексированная кодовая база (в контейнере проекта)",
        fields=("name", "mcp_name", "purpose", "url", "port",
                "catalog_dir", "project_name", "code_index_dir", "connection"),
        connection_template=_HTTP_PORT,
        defaults={
            "mcp_name": "code_index",
            "url": "localhost",
            "port": 8005,
            "purpose": ("Полнотекстовый поиск по функциям и классам, граф "
                        "вызовов, паспорт объекта"),
        },
        action=None,
        required=("catalog_dir", "project_name", "code_index_dir", "port"),
        field_labels={"project_name": "Имя проекта (alias репозитория)",
                      "code_index_dir": "Каталог code_index",
                      "port": "Порт code_index"},
        hidden=True,
    ),
```

- [ ] **Step 4: Добавить id в preload и пропустить действия в `mcp.js`**

В `app/src/agentmon/env/mcp_catalog.py`:

```python
_PRELOAD_IDS = frozenset({"code-index", "code-index-local",
                          "code-index-docker", "bsl-ls"})
```

В `app/web/mcp.js` в `showMcpCard`, после вычисления `isLocal`:

```js
  const managedCodeIndex = mcp.standard_key === "code-index-docker";
```

и в цепочке выбора действий поставить ветку **первой**:

```js
  if (managedCodeIndex) {
    controlsHtml = "";
  } else if (isCfe) {
    controlsHtml = `<button type="button" onclick="downloadCfe('${mcp.id}')">Скачать cfe</button>`;
  } else if (isDocker) {
    controlsHtml = `<button type="button" onclick="launchMcp('${mcp.id}')">Развернуть в Docker локально</button>`;
  } else if (isLocal) {
    controlsHtml = `<button type="button" onclick="deployLocal('${mcp.id}')">Развернуть</button>`;
  }
```

- [ ] **Step 5: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_mcp_types.py tests/env/test_mcp_page.py -q`
Expected: все проходят.

- [ ] **Step 6: Коммит**

```bash
git add app/src/agentmon/env/mcp_types.py app/src/agentmon/env/mcp_catalog.py app/web/mcp.js app/tests/env/test_mcp_types.py app/tests/env/test_mcp_page.py
git commit -m "feat(mcp): скрытый вид code-index-docker без host-развёртывания

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: API мастера — поля code_index/license_dir и дефолт каталога лицензий

**Files:**
- Modify: `app/src/agentmon/env/project_api.py`
- Test: `app/tests/env/test_project_api.py`

**Interfaces:**
- Produces:
  - `license_dir_default(*, os_name=None, environ=None) -> str`
  - `GET /api/env/projects/requirements` → `{"requirements": [...], "license_dir": "..."}`
  - `_prepare_install` возвращает `(pid, config, prov, backend, conn, docker_build, plan)`, где `plan` — `CreatePlan`.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_project_api.py`:

```python
# ─── code_index/license_dir: валидация и дефолты ─────────────────────────────

def test_requirements_license_dir_posix():
    from agentmon.env.project_api import license_dir_default
    assert license_dir_default(os_name="posix", environ={}) == "/var/1C/licenses"


def test_requirements_license_dir_windows():
    from agentmon.env.project_api import license_dir_default
    got = license_dir_default(os_name="nt", environ={"PROGRAMDATA": r"D:\PD"})
    assert got == r"D:\PD\1C\licenses"


def test_requirements_endpoint_includes_license_dir(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.get("/api/env/projects/requirements")
    assert r.status_code == 200
    assert r.json()["license_dir"]


def _local_body(tmp_path, **extra):
    d = tmp_path / "proj"
    d.mkdir()
    return {
        "name": "codeproj", "path": str(d),
        "identifier": "dev", "email": "dev@example.com",
        "platform_dir": "/opt/1cv8", "platform_version": "8.3.25",
        "db_connection": "", "backend": "local", **extra,
    }


def test_code_index_rejected_for_ssh(tmp_path):
    c, _, _ = make_client(tmp_path)
    body = _local_body(tmp_path, backend="ssh", conn={"host": "h"},
                       code_index={"enabled": True,
                                   "catalog_dir": "/x/src/cf",
                                   "code_index_dir": "/x-ci"})
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 400
    assert "local и docker" in r.json()["detail"]


def test_code_index_requires_both_paths(tmp_path):
    c, _, _ = make_client(tmp_path)
    body = _local_body(tmp_path, code_index={"enabled": True,
                                             "catalog_dir": "",
                                             "code_index_dir": "/x-ci"})
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 400
    assert "заполните" in r.json()["detail"]


def test_license_dir_rejected_for_local(tmp_path):
    c, _, _ = make_client(tmp_path)
    body = _local_body(tmp_path, license_dir="/var/1C/licenses")
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 400
    assert "только для docker" in r.json()["detail"]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_api.py -q -k "license_dir or code_index"`
Expected: FAIL.

- [ ] **Step 3: Добавить `license_dir_default` и дефолт в endpoint**

В `project_api.py` добавить импорты:

```python
import os
import sys
from dataclasses import dataclass, field
```

и импорты модуля code-index:

```python
from . import code_index_project
from .code_index_project import CodeIndexError, CodeIndexRequest
```

Перед `build_project_router`:

```python
def license_dir_default(*, os_name=None, environ=None) -> str:
    """Каталог лицензий 1С по умолчанию для хоста AgentMon."""
    name = os_name if os_name is not None else os.name
    env = environ if environ is not None else os.environ
    if name == "nt":
        base = (env.get("PROGRAMDATA") or r"C:\ProgramData").rstrip("\\/")
        return f"{base}\\1C\\licenses"
    return "/var/1C/licenses"


@dataclass
class CreatePlan:
    code_index: CodeIndexRequest | None = None
    license_dir: str | None = None
    code_index_port: int | None = None
    code_index_mid: int | None = None
    code_index_new_service: bool = False
    created_mcp_ids: list[int] = field(default_factory=list)
```

Endpoint:

```python
    @router.get("/api/env/projects/requirements")
    def get_requirements():
        return {"requirements": requirements(LocalProvisioner()),
                "license_dir": license_dir_default()}
```

- [ ] **Step 4: Расширить `_prepare_install`**

Заменить сигнатуру и добавить обработку лицензий/запроса. Полная новая функция:

```python
    def _prepare_install(body: dict):
        """Валидирует тело, сохраняет проект+MCP в БД, строит EnvConfig.

        Возвращает (pid, config, prov, backend, conn, docker_build, plan).
        """
        docker_build = None
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

        missing = [f for f in _REQUIRED_FIELDS if not body.get(f)]
        absent = [f for f in _PRESENT_FIELDS if f not in body]
        if missing or absent:
            all_missing = missing + absent
            raise HTTPException(
                status_code=400,
                detail=f"не заданы обязательные поля: {', '.join(all_missing)}",
            )
        ok, error = validate_name(body["name"])
        if not ok:
            raise HTTPException(status_code=400, detail=error)

        backend = body.get("backend", "local")
        conn = body.get("conn")

        # Валидация code-index/license_dir — до создания Provisioner: для ssh
        # или некорректных путей не нужно поднимать контейнер/соединение.
        license_server = (body.get("license_server") or "").strip()
        license_dir = (body.get("license_dir") or "").strip() or None
        if license_dir:
            if backend != "docker":
                raise HTTPException(
                    status_code=400,
                    detail="license_dir поддерживается только для docker")
            if license_server:
                license_dir = None
            elif (docker_host_from_conn(conn) is None
                  and not Path(license_dir).is_dir()):
                raise HTTPException(
                    status_code=400,
                    detail=f"каталог лицензий не найден: {license_dir}")
            else:
                conn = {**dict(conn or {}), "license_dir": license_dir}
                body = {**body, "conn": conn}

        ci_raw = body.get("code_index") or {}
        ci_request = None
        if ci_raw.get("enabled"):
            try:
                ci_request = code_index_project.validate_request(
                    backend, body["path"],
                    CodeIndexRequest(catalog_dir=ci_raw.get("catalog_dir") or "",
                                     code_index_dir=ci_raw.get("code_index_dir") or ""))
            except CodeIndexError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        prov = _provisioner_for(backend, conn, body.get("path", ""))

        if backend != "docker" and not is_empty_dir(prov, body["path"]):
            raise HTTPException(
                status_code=400,
                detail=f"каталог проекта должен быть пустым: {body['path']}",
            )

        project_repo, mcp_repo = get_repos()
        for existing in project_repo.list():
            if existing["name"] == body["name"] or existing["path"] == body["path"]:
                raise HTTPException(
                    status_code=400,
                    detail=("проект с таким именем или каталогом уже существует: "
                            f"{existing['name']} ({existing['path']})"),
                )
        db_kind = body.get("db_kind") or infer_db_kind(body.get("db_connection", ""))
        pid = project_repo.add(
            name=body["name"], path=body["path"],
            identifier=body["identifier"], email=body["email"],
            platform_dir=body["platform_dir"],
            platform_version=body["platform_version"],
            db_kind=db_kind, db_connection=body["db_connection"],
            web_publication=body.get("web_publication", ""),
            env_version=current_env_version(),
        )

        mcp_selections, valid_mcp_ids = [], []
        for mcp_id in body.get("mcp_ids", []):
            row = mcp_repo.get(mcp_id)
            if row is None:
                continue
            valid_mcp_ids.append(row["id"])
            mcp_selections.append(McpSelection(
                id=row.get("standard_key") or row["name"],
                enabled=True, mode="managed",
                connection=row.get("connection_json"),
                catalog_dir=row.get("catalog_dir"),
                project_name=row.get("project_name"),
                code_index_dir=row.get("code_index_dir"),
            ))
        if valid_mcp_ids:
            mcp_repo.set_for_project(pid, valid_mcp_ids)

        config = EnvConfig(
            schema_version=SCHEMA_VERSION,
            project_name=body["name"], project_dir=body["path"],
            developer_id=body["identifier"], developer_email=body["email"],
            platform_dir=body["platform_dir"],
            platform_version=body["platform_version"],
            db_kind=db_kind, db_connection=body["db_connection"],
            web_publication=body.get("web_publication", ""),
            mcp=mcp_selections,
            agents=[AgentModel(**a) for a in body.get("agents", [])],
            license_server=body.get("license_server"),
        )
        plan = CreatePlan(code_index=ci_request, license_dir=license_dir)
        return pid, config, prov, backend, conn, docker_build, plan
```

- [ ] **Step 5: Не добавлять attach в этой задаче**

`_attach_code_index` появится в Task 7. В этой задаче `_prepare_install`
возвращает `plan` без карточки и без вызова attach; тесты Task 6 проверяют
только валидацию и дефолты.

- [ ] **Step 6: Обновить распаковку в вызовах**

В `create_project`, `create_project_stream` заменить распаковку на 7 значений:

```python
        pid, config, prov, backend, conn, docker_build, plan = _prepare_install(body)
```

и передать `plan` в `_create_produce`:

```python
        job.start(_create_produce(pid, env_config, body, prov, backend, conn,
                                  docker_build, plan))
```

В `_create_produce` принять `plan` (пока не использовать) — сигнатура:

```python
    def _create_produce(pid, env_config, body, prov, backend, conn,
                        docker_build, plan):
```

- [ ] **Step 7: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_api.py -q -k "license_dir or code_index"`
Expected: все проходят. Полный файл — тоже: `... tests/env/test_project_api.py -q`.

- [ ] **Step 8: Коммит**

```bash
git add app/src/agentmon/env/project_api.py app/tests/env/test_project_api.py
git commit -m "feat(api): поля code_index/license_dir и дефолт каталога лицензий

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Создание проекта — карточка, агент, code-index, ожидание, откат

**Files:**
- Modify: `app/src/agentmon/env/project_api.py`
- Test: `app/tests/env/test_project_api.py` (дополнить), `app/tests/env/test_docker_create.py` (дополнить)

**Interfaces:**
- Consumes: `agent_setup.prepare` (Task 1), `DockerProvisioner.mkdirs` (Task 2), `code_index_project.*` (Task 4).
- Produces: полный поток создания.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_project_api.py`:

```python
# ─── создание с code index ───────────────────────────────────────────────────

def _code_index_selection(project_name="codeproj"):
    from agentmon.env.config_schema import McpSelection
    return McpSelection(
        id="code-index", enabled=True, mode="managed",
        connection='"code_index": {"type": "http", "url": "http://localhost:8005/mcp"}',
        catalog_dir="/x/src/cf", project_name=project_name,
        code_index_dir="/x-code-index")


def _fake_code_index(monkeypatch):
    from agentmon.env import code_index_project as cip
    seen = {"resolve": [], "deploy": [], "wait": [], "stop": []}

    def do_deploy(backend, **kw):
        seen["deploy"].append(kw)
        return iter(["deploy\n"])

    def do_wait(backend, **kw):
        seen["wait"].append(kw)

    def do_stop(backend, **kw):
        seen["stop"].append(kw)

    def resolve(repo, **kw):
        seen["resolve"].append(kw)
        return 99, _code_index_selection(kw["project_name"]), True

    monkeypatch.setattr(cip, "pick_port_for_local", lambda d, **kw: 8005)
    monkeypatch.setattr(cip, "pick_port", lambda read, **kw: 8005)
    monkeypatch.setattr(cip, "container_service_port", lambda prov, d: None)
    monkeypatch.setattr(cip, "service_is_new", lambda b, **kw: True)
    monkeypatch.setattr(cip, "resolve_card", resolve)
    monkeypatch.setattr(cip, "deploy", do_deploy)
    monkeypatch.setattr(cip, "wait_ready", do_wait)
    monkeypatch.setattr(cip, "stop_new_service", do_stop)
    return seen


@pytest.fixture(autouse=True)
def _no_agent_prepare(monkeypatch):
    from agentmon.env import agent_setup
    monkeypatch.setattr(agent_setup, "prepare", lambda *a, **kw: None)


def test_local_create_with_code_index_creates_card_and_waits(tmp_path, monkeypatch):
    seen = _fake_code_index(monkeypatch)
    c, _, _ = make_client(tmp_path)
    body = _local_body(
        tmp_path,
        code_index={"enabled": True,
                    "catalog_dir": str(tmp_path / "proj" / "src" / "cf"),
                    "code_index_dir": str(tmp_path / "proj-code-index")})
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    assert seen["resolve"] and seen["resolve"][0]["project_name"] == "codeproj"
    assert seen["deploy"] and seen["deploy"][0]["port"] == 8005
    assert seen["wait"], "wait_ready должен быть вызван"
    assert r.json()["project"]["name"] == "codeproj"


def test_local_create_code_index_error_rolls_back(tmp_path, monkeypatch):
    from agentmon.env import code_index_project as cip
    seen = _fake_code_index(monkeypatch)

    def boom(backend, **kw):
        raise cip.CodeIndexError("index boom")

    monkeypatch.setattr(cip, "wait_ready", boom)
    c, _, _ = make_client(tmp_path)
    body = _local_body(
        tmp_path,
        code_index={"enabled": True,
                    "catalog_dir": str(tmp_path / "proj" / "src" / "cf"),
                    "code_index_dir": str(tmp_path / "proj-code-index")})
    r = c.post("/api/env/projects/create/stream", json=body)
    assert r.status_code == 200
    assert "index boom" in r.text
    names = [p["name"] for p in c.get("/api/env/projects").json()["projects"]]
    assert "codeproj" not in names
    assert seen["stop"], "новый сервис должен быть остановлен при откате"
```

В `test_docker_create.py` добавить:

```python
@pytest.fixture(autouse=True)
def _no_agent_prepare(monkeypatch):
    from agentmon.env import agent_setup
    monkeypatch.setattr(agent_setup, "prepare", lambda *a, **kw: None)


def _docker_code_index_selection():
    from agentmon.env.config_schema import McpSelection
    return McpSelection(
        id="code-index-docker", enabled=True, mode="managed",
        connection='"code_index": {"type": "http", "url": "http://localhost:8005/mcp"}',
        catalog_dir="/workspace/src/cf", project_name="dockerproject",
        code_index_dir="/code-index")


def test_docker_create_attaches_code_index(tmp_path, monkeypatch):
    from agentmon.env import code_index_project as cip
    seen = {"resolve": [], "wait": []}

    monkeypatch.setattr(cip, "pick_port", lambda read, **kw: 8005)
    monkeypatch.setattr(cip, "container_service_port", lambda prov, d: None)
    monkeypatch.setattr(cip, "service_is_new", lambda b, **kw: True)

    def resolve(repo, **kw):
        seen["resolve"].append(kw)
        return 1, _docker_code_index_selection(), True

    monkeypatch.setattr(cip, "resolve_card", resolve)
    monkeypatch.setattr(cip, "deploy", lambda backend, **kw: iter(["deploy\n"]))
    monkeypatch.setattr(cip, "wait_ready", lambda backend, **kw: seen["wait"].append(kw))

    rec = RecordingProvisioner()
    backends = BackendRegistry(
        "claude", docker_factory=lambda project: SimpleNamespace(provisioner=rec))
    monitor = SimpleNamespace(backends=backends)
    client, registry, store = make_client(tmp_path, monitor)
    body = {
        "name": "dockerproject",
        "path": "/workspace",
        "identifier": "dev001",
        "email": "dev@example.com",
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "File=/data/base",
        "web_publication": "",
        "mcp_ids": [],
        "agents": [],
        "backend": "docker",
        "conn": {"image": "ai1c-agent:latest"},
        "code_index": {
            "enabled": True,
            "catalog_dir": "/workspace/src/cf",
            "code_index_dir": "/code-index",
        },
    }
    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    assert seen["resolve"], "resolve_card не вызван"
    assert seen["wait"], "wait_ready не вызван"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_api.py tests/env/test_docker_create.py -q -k "code_index"`
Expected: FAIL.

- [ ] **Step 3: Реализовать `_attach_code_index`**

Добавить в роутер рядом с `_prepare_install`:

```python
    def _attach_code_index(pid, env_config, plan, *, backend, prov, conn):
        req = plan.code_index
        if req is None or plan.code_index_port is not None:
            return
        if backend == "docker":
            host_check = (os.name == "posix"
                          and sys.platform.startswith("linux")
                          and docker_host_from_conn(conn) is None)
            port = code_index_project.pick_port(
                lambda: code_index_project.container_service_port(
                    prov, req.code_index_dir),
                host_check=host_check)
        else:
            port = code_index_project.pick_port_for_local(req.code_index_dir)
        _, mcp_repo = get_repos()
        mid, selection, created = code_index_project.resolve_card(
            mcp_repo, project_id=pid, project_name=env_config.project_name,
            backend=backend, request=req, port=port)
        if created:
            plan.created_mcp_ids.append(mid)
        if not any(s.connection == selection.connection
                   for s in env_config.mcp):
            env_config.mcp.append(selection)
        links = [row["id"] for row in mcp_repo.for_project(pid)]
        if mid not in links:
            mcp_repo.set_for_project(pid, [*links, mid])
        plan.code_index_port = port
        plan.code_index_mid = mid
        plan.code_index_new_service = code_index_project.service_is_new(
            backend, prov=prov, code_index_dir=req.code_index_dir)
```

В конце `_prepare_install` (перед `return`) вернуть блок для local:

```python
        plan = CreatePlan(code_index=ci_request, license_dir=license_dir)
        if ci_request is not None and backend == "local":
            _attach_code_index(pid, config, plan, backend=backend,
                               prov=prov, conn=conn)
        return pid, config, prov, backend, conn, docker_build, plan
```

- [ ] **Step 4: Подключить шаги в `_create_produce`**

Новый вид функции (полностью заменить существующую):

```python
    def _create_produce(pid, env_config, body, prov, backend, conn,
                        docker_build, plan):
        def produce():
            created = False
            try:
                yield (f"▶ Создание проекта «{env_config.project_name}» "
                       f"({env_config.project_dir})\n")
                failed = False
                try:
                    if docker_build is not None:
                        yield (f"[образ] сборка ai1c-agent:{docker_build[1]} "
                               f"из дистрибутива\n")
                        for line in build_image_fn(docker_build[0], docker_build[1],
                                                   docker_host=docker_build[2]):
                            yield line
                    if plan.code_index is not None and backend == "docker":
                        prov.mkdirs([env_config.project_dir])
                        _attach_code_index(pid, env_config, plan, backend=backend,
                                           prov=prov, conn=conn)
                        yield "✓ code-index подключён к проекту\n"
                    for ev in _install_iter(env_config, body, prov, backend, conn):
                        detail = f" {ev.detail}" if ev.detail else ""
                        yield f"[{ev.step}] {ev.status}{detail}\n"
                        if ev.status == "error":
                            failed = True
                    if not failed and backend == "docker":
                        lines = []
                        agent_setup.prepare(
                            prov, env_config.project_dir,
                            body.get("claude_cmd") or config.CLAUDE_CMD,
                            log=lines.append)
                        for line in lines:
                            yield line + "\n"
                    if not failed and plan.code_index is not None:
                        yield "▶ code-index\n"
                        for line in code_index_project.deploy(
                                backend, prov=prov,
                                code_index_dir=plan.code_index.code_index_dir,
                                catalog_dir=plan.code_index.catalog_dir,
                                project_name=env_config.project_name,
                                port=plan.code_index_port,
                                mid=plan.code_index_mid):
                            yield line + "\n"
                        wait_lines = []
                        code_index_project.wait_ready(
                            backend, prov=prov,
                            code_index_dir=plan.code_index.code_index_dir,
                            port=plan.code_index_port,
                            log=wait_lines.append)
                        for line in wait_lines:
                            yield line + "\n"
                except Exception as exc:                   # noqa: BLE001
                    failed = True
                    yield f"✗ Ошибка: {exc}\n"
                if failed:
                    yield "\n✗ Установка завершилась с ошибкой\n"
                else:
                    created = True
                    yield "\n✓ Проект создан\n"
            finally:
                if not created:
                    _rollback_project(pid, env_config.project_dir, plan=plan,
                                      backend=backend, prov=prov)
        return produce
```

Импорт в `project_api.py` (модуль `code_index_project` уже импортирован в Task 6):

```python
from . import agent_setup
```

- [ ] **Step 5: Подключить шаги в блокирующем `create_project`**

```python
    @router.post("/api/env/projects/create")
    def create_project(body: dict):
        pid, config, prov, backend, conn, docker_build, plan = _prepare_install(body)
        try:
            if docker_build is not None:
                for _ in build_image_fn(docker_build[0], docker_build[1],
                                        docker_host=docker_build[2]):
                    pass
            if plan.code_index is not None and backend == "docker":
                prov.mkdirs([config.project_dir])
                _attach_code_index(pid, config, plan, backend=backend,
                                   prov=prov, conn=conn)
            events = list(_install_iter(config, body, prov, backend, conn))
            failed = any(e.status == "error" for e in events)
            if not failed and backend == "docker":
                agent_setup.prepare(
                    prov, config.project_dir,
                    body.get("claude_cmd") or config.CLAUDE_CMD)
            if not failed and plan.code_index is not None:
                for _ in code_index_project.deploy(
                        backend, prov=prov,
                        code_index_dir=plan.code_index.code_index_dir,
                        catalog_dir=plan.code_index.catalog_dir,
                        project_name=config.project_name,
                        port=plan.code_index_port, mid=plan.code_index_mid):
                    pass
                code_index_project.wait_ready(
                    backend, prov=prov,
                    code_index_dir=plan.code_index.code_index_dir,
                    port=plan.code_index_port)
        except BaseException:
            _rollback_project(pid, config.project_dir, plan=plan,
                              backend=backend, prov=prov)
            raise
        project_repo, _ = get_repos()
        project = project_repo.get(pid)
        return {"project": project, "events": [asdict(e) for e in events]}
```

- [ ] **Step 6: Расширить `_rollback_project`**

```python
    def _rollback_project(pid, path="", *, plan=None, backend="local", prov=None):
        """Удалить незавершённый проект (стаб) при ошибке создания."""
        try:
            project_repo, mcp_repo = get_repos()
            try:
                mcp_repo.set_for_project(pid, [])
            except Exception:
                pass
            if plan is not None:
                for mid in plan.created_mcp_ids:
                    try:
                        mcp_repo.delete(mid)
                    except Exception:
                        pass
            project_repo.delete(pid)
            if path:
                for p in registry.list():
                    if same_path(p.path, path):
                        registry.delete(p.id)
                        break
        except Exception:
            pass
        if (plan is not None and plan.code_index is not None
                and plan.code_index_new_service):
            try:
                code_index_project.stop_new_service(
                    backend, prov=prov,
                    code_index_dir=plan.code_index.code_index_dir)
            except Exception:
                pass
```

- [ ] **Step 7: Поправить старые вызовы `_rollback_project`**

Все вызовы без плана оставить совместимыми (`plan=None` по умолчанию) — в `create_project_stream`/`_create_produce` уже передаётся план.

- [ ] **Step 8: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_api.py tests/env/test_docker_create.py -q`
Expected: все проходят. `agent_setup.prepare` в тестах замокан autouse-фикстурой `_no_agent_prepare`, поэтому окружение хоста (ключ DeepSeek/strata) на тесты не влияет.

- [ ] **Step 9: Коммит**

```bash
git add app/src/agentmon/env/project_api.py app/tests/env/test_project_api.py app/tests/env/test_docker_create.py
git commit -m "feat(api): автосоздание code-index и подготовка агента при создании проекта

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Мастер проекта — галочка code index и каталог лицензий

**Files:**
- Modify: `app/web/project-wizard.html`
- Modify: `app/web/project-wizard.js`
- Test: `app/tests/env/test_project_wizard_page.py`

**Interfaces:**
- Produces: тело создания с `code_index` и `license_dir`; видимость полей по backend/режиму.

- [ ] **Step 1: Написать падающие тесты**

Добавить в `app/tests/env/test_project_wizard_page.py`:

```python
def test_html_has_code_index_controls():
    h = _html()
    assert 'id="codeIndexEnabled"' in h
    assert 'id="codeIndexCatalogDir"' in h
    assert 'id="codeIndexDir"' in h
    assert 'id="licenseDir"' in h


def test_js_sends_code_index_and_license_dir():
    js = _js()
    assert "code_index:" in js and "license_dir" in js
    assert "updateCodeIndexDefaults" in js
    assert "src/cf" in js and "/code-index" in js
    assert "-code-index" in js


def test_js_hides_code_index_for_ssh_and_update():
    js = _js()
    assert 'backend === "ssh"' in js
    assert "updateProjectId !== null" in js
    assert "syncCodeIndexUi" in js


def test_js_reads_license_default_from_requirements():
    js = _js()
    assert "license_dir" in js
    assert "licenseDir" in js


def test_js_validates_absolute_paths():
    js = _js()
    assert "isAbsolutePath" in js
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_wizard_page.py -q -k "code_index or license_default or absolute"`
Expected: FAIL.

- [ ] **Step 3: Добавить разметку**

В `project-wizard.html` в секции «Платформа» после поля `licenseServer`:

```html
      <div class="field-group" id="licenseDirField" hidden style="margin-top:12px;">
        <label>
          <span class="label-text">Каталог лицензий 1С (для Docker)</span>
          <input id="licenseDir" type="text" placeholder="/var/1C/licenses">
        </label>
        <p class="mcp-hint">
          Монтируется в контейнер как <code>/var/1C/licenses</code>.
          Оставьте пустым, если лицензии не нужны.
        </p>
      </div>
```

В секции «MCP-серверы» после `mcpHint`:

```html
      <div class="checkbox-item" id="codeIndexItem" style="margin-top:10px;">
        <input id="codeIndexEnabled" type="checkbox">
        <label for="codeIndexEnabled">code index</label>
      </div>
      <div id="codeIndexFields" hidden>
        <label>
          <span class="label-text">Каталог кодовой базы</span>
          <input id="codeIndexCatalogDir" type="text"
                 placeholder="/path/demo/src/cf">
        </label>
        <label>
          <span class="label-text">Каталог code_index</span>
          <input id="codeIndexDir" type="text"
                 placeholder="/path/demo-code-index">
        </label>
        <p class="mcp-hint">
          Один каталог code_index может обслуживать несколько баз;
          обращение по alias — имя проекта.
        </p>
      </div>
```

- [ ] **Step 4: Реализовать JS**

В `project-wizard.js` добавить после `updateProjectId`:

```js
// Автозаполнение полей code index; ручная правка отключает перезапись.
let codeIndexCatalogDirty = false;
let codeIndexDirDirty = false;

function pathSep(base) {
  return (base.includes("\\") || /^[A-Za-z]:/.test(base)) ? "\\" : "/";
}

function joinProjectPath(base, rel) {
  if (!base) return "";
  return base.replace(/[\\/]+$/, "") + pathSep(base) + rel;
}

function isAbsolutePath(value, backend) {
  const v = (value || "").trim();
  if (!v) return false;
  if (backend === "docker") return v.startsWith("/");
  return v.startsWith("/") || /^[A-Za-z]:[\\/]/.test(v);
}

function updateCodeIndexDefaults() {
  const backend = document.getElementById("backend").value;
  const path = (document.getElementById("path").value || "").trim();
  const catalog = document.getElementById("codeIndexCatalogDir");
  const ci = document.getElementById("codeIndexDir");
  if (!codeIndexCatalogDirty) {
    catalog.value = path ? joinProjectPath(path, "src/cf") : "";
  }
  if (!codeIndexDirDirty) {
    ci.value = backend === "docker"
      ? "/code-index"
      : (path ? path.replace(/[\\/]+$/, "") + "-code-index" : "");
  }
}

function syncCodeIndexUi() {
  const backend = document.getElementById("backend").value;
  const item = document.getElementById("codeIndexItem");
  const check = document.getElementById("codeIndexEnabled");
  const block = document.getElementById("codeIndexFields");
  const hidden = backend === "ssh" || updateProjectId !== null;
  item.hidden = hidden;
  check.disabled = hidden;
  if (hidden) {
    check.checked = false;
    block.hidden = true;
    return;
  }
  block.hidden = !check.checked;
  if (check.checked) updateCodeIndexDefaults();
}

function syncLicenseDir() {
  const backend = document.getElementById("backend").value;
  const field = document.getElementById("licenseDirField");
  const server = (document.getElementById("licenseServer").value || "").trim();
  field.hidden = !(backend === "docker" && !server && updateProjectId === null);
}
```

В `DOMContentLoaded` после `syncBackend()`:

```js
  backendSel.addEventListener("change", syncCodeIndexUi);
  backendSel.addEventListener("change", syncLicenseDir);
  document.getElementById("codeIndexEnabled")
    .addEventListener("change", syncCodeIndexUi);
  document.getElementById("licenseServer")
    .addEventListener("input", syncLicenseDir);
  document.getElementById("path")
    .addEventListener("input", updateCodeIndexDefaults);
  document.getElementById("codeIndexCatalogDir")
    .addEventListener("input", () => { codeIndexCatalogDirty = true; });
  document.getElementById("codeIndexDir")
    .addEventListener("input", () => { codeIndexDirDirty = true; });
  syncCodeIndexUi();
  syncLicenseDir();
```

В `loadRequirements`, после получения `data` и заполнения `container`:

```js
    const license = document.getElementById("licenseDir");
    if (license && !license.value) license.value = data.license_dir || "";
    syncLicenseDir();
```

В `syncBackend` в конце добавить:

```js
    syncCodeIndexUi();
    syncLicenseDir();
```

(если `updateProjectId` уже задан — блок скроется).

В `createProject`, перед сборкой `body`, добавить валидацию:

```js
  const backend = document.getElementById("backend").value;
  const ciEnabled = document.getElementById("codeIndexEnabled").checked;
  const ciCatalog = document.getElementById("codeIndexCatalogDir").value.trim();
  const ciDir = document.getElementById("codeIndexDir").value.trim();
  if (ciEnabled) {
    if (!isAbsolutePath(ciCatalog, backend) || !isAbsolutePath(ciDir, backend)) {
      alert("Укажите абсолютные пути для каталога кодовой базы и code_index");
      return;
    }
  }
```

и в `body`:

```js
    code_index: {
      enabled: ciEnabled,
      catalog_dir: ciCatalog,
      code_index_dir: ciDir,
    },
```

После формирования `body.backend`:

```js
  if (body.backend === "docker") {
    const license = document.getElementById("licenseDir").value.trim();
    body.license_dir = license || null;
  }
```

В `checkUrlParams`, после установки `updateProjectId`, вызвать:

```js
    syncCodeIndexUi();
    syncLicenseDir();
```

- [ ] **Step 5: Прогнать тесты**

Run: `cd app && ../.venv/bin/python -m pytest tests/env/test_project_wizard_page.py -q`
Expected: все проходят.

- [ ] **Step 6: Коммит**

```bash
git add app/web/project-wizard.html app/web/project-wizard.js app/tests/env/test_project_wizard_page.py
git commit -m "feat(web): галочка code index и каталог лицензий в мастере проекта

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Документация и полный прогон

**Files:**
- Modify: `docs/running-web-ui.md`
- Modify: `docs/mcp/code-index-common.md`
- Modify: `docs/mcp/code-index-local.md`

- [ ] **Step 1: Обновить `docs/running-web-ui.md`**

Добавить раздел после описания мастера проекта:

```markdown
### Code index при создании проекта

В секции «MCP-серверы» мастера есть галочка **code index**. При включении:

- «Каталог кодовой базы» автозаполняется `<каталог проекта>/src/cf`;
- «Каталог code_index» для local по умолчанию `<каталог проекта>-code-index`,
  для docker — `/code-index`.

При создании проекта agentmon создаёт (или переиспользует) карточку
`code-index`, добавляет её в `.mcp.json` и разворачивает сервис; создание
завершается после готовности индекса. Один каталог `code_index` может
обслуживать несколько баз: alias всегда равен имени проекта. Для docker
сервис работает внутри контейнера проекта.

Если «Сервер лицензий» пуст, для docker показывается поле «Каталог лицензий 1С»
(по умолчанию `/var/1C/licenses` на Linux, `C:\ProgramData\1C\licenses` на
Windows); каталог монтируется в контейнер как `/var/1C/licenses`.
```

- [ ] **Step 2: Обновить `docs/mcp/code-index-common.md`**

Добавить в раздел «Один сервис — несколько баз» абзац:

```markdown
В docker-проекте сервис живёт внутри контейнера проекта (том
`<контейнер>-codeindex:/code-index`), а `path` в `daemon.toml` — путь внутри
контейнера (`/workspace/src/cf`). Карточка такого сервиса —
`standard_key=code-index-docker`: она не предлагает host-развёртывание,
сервисом управляет создание проекта.
```

- [ ] **Step 3: Обновить `docs/mcp/code-index-local.md`**

Добавить в конец раздел:

```markdown
## Code index в docker-проекте

Для docker-проекта code-index разворачивается не на хосте, а внутри
контейнера проекта (том `/code-index`). Агент обращается к нему по
`http://localhost:<порт>/mcp`; alias — имя проекта. Управление — через
создание проекта; карточка `code-index-docker` кнопки «Развернуть» не имеет.
```

- [ ] **Step 4: Полный прогон тестов**

Run:

```bash
cd app && ../.venv/bin/python -m pytest tests -q
```

Expected: все тесты проходят.

Run:

```bash
cd /home/uam/projects/ai_template && .venv/bin/python -m pytest benchmark/tests -q
```

Expected: все тесты проходят.

- [ ] **Step 5: Коммит документации**

```bash
git add docs/running-web-ui.md docs/mcp/code-index-common.md docs/mcp/code-index-local.md
git commit -m "docs: code index мастера проекта и docker-схема

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

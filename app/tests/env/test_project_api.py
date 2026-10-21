"""Тесты API мастера/справочника проектов (project_api.py)."""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.backends import RunResult
from agentmon.backends.factory import BackendRegistry
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa


def make_client(tmp_path):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store)
    return TestClient(app), registry, store


# ─── validate-name ───────────────────────────────────────────────────────────

def test_validate_name_ok(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/validate-name", json={"name": "myproject"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["error"] is None


def test_validate_name_bad(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/validate-name", json={"name": "2bad"})
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["error"]


def test_validate_name_keyword(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/validate-name", json={"name": "import"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ─── version ─────────────────────────────────────────────────────────────────

def test_env_version(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.get("/api/env/version")
    assert r.status_code == 200
    assert r.json()["version"].strip() != ""


# ─── requirements ────────────────────────────────────────────────────────────

def test_requirements(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.get("/api/env/projects/requirements")
    assert r.status_code == 200
    reqs = r.json()["requirements"]
    names = {req["name"] for req in reqs}
    assert {"git", "claude", "node"} <= names
    assert "docker" not in names
    assert "python3" not in names   # python в PATH цели не требуется — скиллам .venv
    assert all({"name", "ok", "detail"} <= set(req) for req in reqs)


# ─── check-db ────────────────────────────────────────────────────────────────

def test_check_db(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/check-db", json={
        "platform_dir": "/opt/1c",
        "db_kind": "postgresql",
        "db_connection": "host=localhost",
        "user": "admin",
        "password": "secret",
    })
    assert r.status_code == 200
    assert "ok" in r.json()
    assert "log" in r.json()


# ─── create ──────────────────────────────────────────────────────────────────

def test_create_project(tmp_path):
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    c, registry, store = make_client(tmp_path)
    body = {
        "name": "myproject",
        "path": str(project_dir),
        "identifier": "dev123",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "File=/data/base",
        "web_publication": "",
        "mcp_ids": [],
        "agents": [],
        "update": False,
        "dump_cf": False,
        "dump_cfe": False,
        "install_tools": False,
    }
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "project" in data
    assert "events" in data
    assert data["project"]["name"] == "myproject"
    assert data["project"]["env_version"] != ""
    # события должны быть — хотя бы layout и register
    assert len(data["events"]) > 0
    # проект должен быть в ProjectRepo
    from agentmon.store.projects import ProjectRepo
    repo = ProjectRepo(store)
    projects = repo.list()
    assert any(p["name"] == "myproject" for p in projects)


def test_create_project_missing_fields(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/create", json={"name": "myproject"})
    assert r.status_code == 400


def test_create_project_bad_name(tmp_path):
    project_dir = tmp_path / "2bad"
    project_dir.mkdir()
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/create", json={
        "name": "2bad",
        "path": str(project_dir),
        "identifier": "dev",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [],
        "agents": [],
    })
    assert r.status_code == 400


def test_create_project_nonempty_dir_rejected(tmp_path):
    """Создание в непустой каталог отклоняется, проект не создаётся."""
    project_dir = tmp_path / "myproject"
    project_dir.mkdir()
    (project_dir / "existing.txt").write_text("data")
    c, _, store = make_client(tmp_path)
    body = {
        "name": "myproject",
        "path": str(project_dir),
        "identifier": "dev123",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [],
        "agents": [],
    }
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 400
    from agentmon.store.projects import ProjectRepo
    repo = ProjectRepo(store)
    assert repo.list() == []


# ─── update-env ───────────────────────────────────────────────────────────────

def test_update_env_happy(tmp_path):
    project_dir = tmp_path / "upd"
    project_dir.mkdir()
    c, _, store = make_client(tmp_path)
    body = {
        "name": "upd",
        "path": str(project_dir),
        "identifier": "dev",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [],
        "agents": [],
    }
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    pid = r.json()["project"]["id"]
    # сбросим env_version, чтобы убедиться что update его переустановит
    from agentmon.store.projects import ProjectRepo
    ProjectRepo(store).update(pid, env_version="0.0.0")
    r2 = c.post(f"/api/env/projects/{pid}/update-env", json={})
    assert r2.status_code == 200, r2.text
    assert r2.json()["project"]["env_version"] != "0.0.0"


def test_update_env_404(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.post("/api/env/projects/999/update-env", json={})
    assert r.status_code == 404


def test_create_persists_and_exposes_mcp(tmp_path):
    """Создание с mcp_ids сохраняет связи; GET проекта отдаёт mcp_ids."""
    project_dir = tmp_path / "mcpproj"
    project_dir.mkdir()
    c, _, store = make_client(tmp_path)
    from agentmon.store.mcp import McpRepo
    mid = McpRepo(store).add(name="my-mcp", purpose="test")
    body = {
        "name": "mcpproj",
        "path": str(project_dir),
        "identifier": "dev",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [mid],
        "agents": [],
    }
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    pid = r.json()["project"]["id"]
    r2 = c.get(f"/api/env/projects/{pid}")
    assert r2.status_code == 200
    assert mid in r2.json()["project"]["mcp_ids"]


# ─── list/get ─────────────────────────────────────────────────────────────────

def test_list_projects_empty(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.get("/api/env/projects")
    assert r.status_code == 200
    assert r.json()["projects"] == []


def test_get_project_404(tmp_path):
    c, _, _ = make_client(tmp_path)
    r = c.get("/api/env/projects/999")
    assert r.status_code == 404


def test_list_after_create(tmp_path):
    project_dir = tmp_path / "proj2"
    project_dir.mkdir()
    c, _, _ = make_client(tmp_path)
    body = {
        "name": "proj2",
        "path": str(project_dir),
        "identifier": "dev",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [],
        "agents": [],
        "dump_cf": False,
        "dump_cfe": False,
        "install_tools": False,
    }
    r = c.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    pid = r.json()["project"]["id"]

    r2 = c.get("/api/env/projects")
    assert any(p["id"] == pid for p in r2.json()["projects"])

    r3 = c.get(f"/api/env/projects/{pid}")
    assert r3.status_code == 200
    assert r3.json()["project"]["id"] == pid


# ─── no store → 503 ──────────────────────────────────────────────────────────

def test_no_store_503(tmp_path):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=None)
    c = TestClient(app)
    r = c.get("/api/env/projects")
    assert r.status_code == 503


def test_delete_project_removes_db_and_keeps_dir(tmp_path):
    client, registry, store = make_client(tmp_path)
    from agentmon.store.projects import ProjectRepo
    from agentmon.store.tasks import TaskRepo
    from agentmon.store.stacks import StackRepo

    pr, tr, sr = ProjectRepo(store), TaskRepo(store), StackRepo(store)
    proj_dir = tmp_path / "proj"
    proj_dir.mkdir()
    (proj_dir / "keep.txt").write_text("x", encoding="utf-8")

    pid = pr.add(name="p1", path=str(proj_dir))
    t1 = tr.add(project_id=pid, name="t1")
    sid = sr.add(name="s1")
    sr.add_item(sid, t1)

    r = client.delete(f"/api/env/projects/{pid}")
    assert r.status_code == 200 and r.json()["ok"] is True

    assert pr.get(pid) is None                 # проект удалён
    assert tr.list(project_id=pid) == []        # задачи удалены
    assert sr.items(sid) == []                  # задача снята из стека
    assert (proj_dir / "keep.txt").exists()     # каталог и файлы на месте


def test_delete_project_404(tmp_path):
    client, _, _ = make_client(tmp_path)
    assert client.delete("/api/env/projects/9999").status_code == 404


def test_create_stream_streams_steps(tmp_path):
    project_dir = tmp_path / "streamproj"
    project_dir.mkdir()
    client, _, _ = make_client(tmp_path)
    body = {
        "name": "streamproj", "path": str(project_dir),
        "identifier": "dev", "email": "dev@example.com",
        "platform_dir": "/opt/1c", "platform_version": "8.3",
        "db_connection": "", "mcp_ids": [], "agents": [],
        "dump_cf": False, "dump_cfe": False, "install_tools": False,
        "git_init": False,
    }
    r = client.post("/api/env/projects/create/stream", json=body)
    assert r.status_code == 200
    text = r.text
    assert "[layout]" in text and "[content]" in text
    assert "Проект создан" in text


def test_create_stream_validation_400(tmp_path):
    client, _, _ = make_client(tmp_path)
    r = client.post("/api/env/projects/create/stream", json={"name": "x"})
    assert r.status_code == 400


def test_update_env_stream_streams_steps(tmp_path):
    project_dir = tmp_path / "updstream"
    project_dir.mkdir()
    client, _, store = make_client(tmp_path)
    body = {
        "name": "updstream", "path": str(project_dir),
        "identifier": "dev", "email": "dev@example.com",
        "platform_dir": "/opt/1c", "platform_version": "8.3",
        "db_connection": "", "mcp_ids": [], "agents": [],
        "dump_cf": False, "dump_cfe": False, "install_tools": False,
        "git_init": False,
    }
    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    pid = r.json()["project"]["id"]

    from agentmon.store.projects import ProjectRepo
    ProjectRepo(store).update(pid, env_version="0.0.0")

    r2 = client.post(f"/api/env/projects/{pid}/update-env/stream", json={})
    assert r2.status_code == 200
    text = r2.text
    assert "Обновление окружения" in text
    assert "[content]" in text
    assert "Окружение обновлено" in text
    # env_version переустановлен
    assert ProjectRepo(store).get(pid)["env_version"] != "0.0.0"


def test_update_env_stream_404(tmp_path):
    client, _, _ = make_client(tmp_path)
    r = client.post("/api/env/projects/999/update-env/stream", json={})
    assert r.status_code == 404


# ─── docker create ────────────────────────────────────────────────────────────

def _docker_client(tmp_path, *, exists, build_lines=None, build_rc_ok=True,
                   empty_raises=False):
    """TestClient с docker-бэкендом и инъекцией image/build функций.

    Провиженинг docker идёт через RecordingProvisioner (без реального docker).
    empty_raises=True имитирует реальный DockerProvisioner.is_empty_dir, который
    до сборки образа поднимает контейнер и падает (_build → RuntimeError).
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
        def is_empty_dir(self, p):
            if empty_raises:
                raise RuntimeError("образ не найден (контейнер не поднять без образа)")
            return True
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
    d = tmp_path / "proj"; d.mkdir(exist_ok=True)
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


# ─── update-env backend-aware (ssh/docker) ────────────────────────────────────

class _RecordingProvisioner:
    """Минимальный провайдер-рекордер для тестов update-env."""

    def __init__(self):
        self.runs: list[tuple] = []
        self.writes: dict = {}

    def write_text(self, path, content) -> None:
        self.writes[path] = content

    def write_bytes(self, path, data) -> None:
        self.writes[path] = data

    def put_tree(self, local_src, dst, skip=None) -> None:
        from pathlib import Path as _Path
        from agentmon.backends import is_cruft
        src_path = _Path(local_src)
        for item in sorted(src_path.rglob("*")):
            rel = item.relative_to(src_path)
            if is_cruft(rel):
                continue
            if skip is not None and skip(rel):
                continue
            if item.is_dir():
                continue
            target = f"{dst}/{rel.as_posix()}"
            try:
                self.writes[target] = item.read_bytes()
            except OSError:
                pass

    def mkdirs(self, paths) -> None:
        pass

    def exists(self, path) -> bool:
        return path in self.writes

    def is_file(self, path) -> bool:
        return path in self.writes

    def is_empty_dir(self, path) -> bool:
        return True

    def read_text(self, path) -> str:
        val = self.writes.get(path, "")
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="replace")
        return val

    def which(self, tool) -> str | None:
        return f"/usr/bin/{tool}"

    def python_cmd(self) -> list:
        return ["python3"]

    def venv_python(self, project_dir) -> str:
        return f"{project_dir}/.venv/bin/python"

    def tempdir(self) -> str:
        return "/tmp"

    def run(self, cmd, cwd=None, timeout=None) -> RunResult:
        self.runs.append((cmd, cwd))
        return RunResult(0, "", "")


def _make_client_with_monitor(tmp_path, monitor):
    """Создаёт TestClient с заданным monitor (для backend-aware тестов)."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=monitor,
                     store=store)
    return TestClient(app), registry, store


def test_update_env_ssh_uses_recording_provisioner(tmp_path):
    """update-env для ssh-проекта разрешает provisioner из backend (не LocalProvisioner)."""
    rec = _RecordingProvisioner()
    backends = BackendRegistry(
        "claude",
        ssh_factory=lambda conn: SimpleNamespace(provisioner=rec),
    )
    monitor = SimpleNamespace(backends=backends)
    client, registry, store = _make_client_with_monitor(tmp_path, monitor)

    project_path = "/srv/sshupd"

    # Добавляем проект в store напрямую (update-env читает только из store)
    from agentmon.store.projects import ProjectRepo
    pr = ProjectRepo(store)
    pid = pr.add(
        name="sshupd", path=project_path,
        identifier="dev", email="dev@example.com",
        platform_dir="/opt/1c", platform_version="8.3",
        db_kind="file", db_connection="",
        env_version="0.0.0",
    )

    # Регистрируем проект с backend=ssh в registry
    registry.add(name="sshupd", path=project_path, backend="ssh",
                 conn={"host": "h", "user": "u", "port": 22, "key_path": None})

    r = client.post(f"/api/env/projects/{pid}/update-env", json={})
    assert r.status_code == 200, r.text

    # RecordingProvisioner получил вызовы (content-шаги: put_tree/write_text)
    assert rec.writes or rec.runs, \
        "RecordingProvisioner не получил обращений — update-env не использовал ssh prov"

    # env_version обновлён
    assert pr.get(pid)["env_version"] != "0.0.0"


def test_update_env_local_project_uses_local_provisioner(tmp_path):
    """update-env для local-проекта (или отсутствующего в registry) — LocalProvisioner.

    Если путь не найден в registry → backend=local (дефолт) → LocalProvisioner.
    Реальный каталог существует: content-шаги запишут файлы в tmp_path/localupd.
    """
    project_dir = tmp_path / "localupd"
    project_dir.mkdir()

    client, registry, store = make_client(tmp_path)

    from agentmon.store.projects import ProjectRepo
    pr = ProjectRepo(store)
    pid = pr.add(
        name="localupd", path=str(project_dir),
        identifier="dev", email="dev@example.com",
        platform_dir="/opt/1c", platform_version="8.3",
        db_kind="file", db_connection="",
        env_version="0.0.0",
    )
    # НЕ регистрируем в registry → должен использоваться LocalProvisioner

    r = client.post(f"/api/env/projects/{pid}/update-env", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    # content-шаг выполнился (LocalProvisioner пишет в реальный tmp_path)
    assert any(e["step"] == "content" and e["status"] == "ok" for e in data["events"])
    assert pr.get(pid)["env_version"] != "0.0.0"


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


def test_update_env_stream_ssh_uses_recording_provisioner(tmp_path):
    """update-env/stream для ssh-проекта разрешает provisioner из backend."""
    rec = _RecordingProvisioner()
    backends = BackendRegistry(
        "claude",
        ssh_factory=lambda conn: SimpleNamespace(provisioner=rec),
    )
    monitor = SimpleNamespace(backends=backends)
    client, registry, store = _make_client_with_monitor(tmp_path, monitor)

    project_path = "/srv/sshstream"

    from agentmon.store.projects import ProjectRepo
    pr = ProjectRepo(store)
    pid = pr.add(
        name="sshstream", path=project_path,
        identifier="dev", email="dev@example.com",
        platform_dir="/opt/1c", platform_version="8.3",
        db_kind="file", db_connection="",
        env_version="0.0.0",
    )
    registry.add(name="sshstream", path=project_path, backend="ssh",
                 conn={"host": "h", "user": "u", "port": 22, "key_path": None})

    r = client.post(f"/api/env/projects/{pid}/update-env/stream", json={})
    assert r.status_code == 200
    text = r.text
    assert "Обновление окружения" in text
    assert "Окружение обновлено" in text

    # RecordingProvisioner получил вызовы
    assert rec.writes or rec.runs, \
        "RecordingProvisioner не получил обращений — update-env/stream не использовал ssh prov"

    assert pr.get(pid)["env_version"] != "0.0.0"


def test_docker_create_stream_skips_empty_check_before_build(tmp_path):
    """Регресс: для docker is_empty_dir поднял бы контейнер до сборки образа
    (→ _build RuntimeError → 500). Гейт пустоты для docker должен пропускаться,
    создание — доходить до сборки."""
    c, _ = _docker_client(tmp_path, exists=False, empty_raises=True,
                          build_lines=["Step 1/5\n", "Successfully built\n"])
    body = _docker_body(tmp_path, distr_path="/tmp/server64_8_3_27.zip")
    r = c.post("/api/env/projects/create/stream", json=body)
    assert r.status_code == 200
    assert "Step 1/5" in r.text
    assert "✓ Проект создан" in r.text

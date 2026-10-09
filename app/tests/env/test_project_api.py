"""Тесты API мастера/справочника проектов (project_api.py)."""
import subprocess
from pathlib import Path

import pytest
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


def fake_run(cmd, **kwargs):
    """Заглушка subprocess.run: всегда rc=0."""
    class Result:
        returncode = 0
        stdout = "ok"
        stderr = ""
    return Result()


def make_client(tmp_path, run=fake_run):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store, run=run)
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
    assert {"python3", "git", "claude"} <= names
    assert "docker" not in names
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
    app = create_app(registry=registry, queue=queue, monitor=mon, store=None, run=fake_run)
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

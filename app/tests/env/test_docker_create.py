"""Smoke-test: CREATE flow использует resolved provisioner для backend="docker".

Цели:
- RecordingProvisioner внедряется через BackendRegistry(docker_factory=...)
- Probe-Project несёт реальный путь → docker_factory получает правильный path
- Файлы записываются на RecordingProvisioner, а не в реальную ФС
- platform_dir по умолчанию /opt/1cv8/current при пустом значении
- Проект регистрируется с backend="docker"
- cf/cfe dump + tools-install выполняются через RecordingProvisioner (гейт is_local снят)
- git init запускается через RecordingProvisioner.run
"""
import sys
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from agentmon.api import create_app
from agentmon.backends import RunResult
from agentmon.backends.docker import DEFAULT_PLATFORM_DIR
from agentmon.backends.factory import BackendRegistry
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.store.db import connect
from agentmon.store.schema import init_schema

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


class RecordingProvisioner:
    """In-memory provisioner: записывает все обращения без реальной ФС/docker."""

    def __init__(self):
        self.writes: dict[str, str | bytes] = {}
        self.runs: list[tuple] = []

    # ── файловые операции ────────────────────────────────────────────────────

    def write_text(self, path, content) -> None:
        self.writes[path] = content

    def write_bytes(self, path, data) -> None:
        self.writes[path] = data

    def put_tree(self, local_src, dst, skip=None) -> None:
        """Обходит реальный шаблон на мониторе; записывает целевые пути в writes."""
        from agentmon.backends import is_cruft
        src_path = Path(local_src)
        dst_path = dst
        for item in sorted(src_path.rglob("*")):
            rel = item.relative_to(src_path)
            if is_cruft(rel):          # как в проде: cruft по относительному пути
                continue
            if skip is not None and skip(rel):
                continue
            if item.is_dir():
                continue
            target = f"{dst_path}/{rel.as_posix()}"
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
        # Всегда пусто — RecordingProvisioner не знает реальной ФС
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

    # ── запуск команд ────────────────────────────────────────────────────────

    def run(self, cmd, cwd=None, timeout=None) -> RunResult:
        self.runs.append((cmd, cwd))
        return RunResult(0, "", "")


def make_client(tmp_path, monitor):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=monitor,
                     store=store)
    return TestClient(app), registry, store


# ─── Docker create smoke test ────────────────────────────────────────────────

def test_docker_create_uses_recording_provisioner(tmp_path):
    """Полный happy-path для backend=docker; проверяет provisioner, регистрацию,
    probe с реальным путём, записанные файлы, git-init и выполнение cf/cfe+tools через prov."""
    rec = RecordingProvisioner()
    received_projects: list = []

    def docker_factory(project):
        received_projects.append(project)
        return SimpleNamespace(provisioner=rec)

    backends = BackendRegistry(
        "claude",
        docker_factory=docker_factory,
    )
    monitor = SimpleNamespace(backends=backends)

    client, registry, store = make_client(tmp_path, monitor)

    project_path = "/workspace"  # путь внутри контейнера
    body = {
        "name": "dockerproject",
        "path": project_path,
        "identifier": "dev001",
        "email": "dev@example.com",
        # platform_dir намеренно не передаём — должен дефолтиться в /opt/1cv8/current
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "File=/data/base",
        "web_publication": "",
        "mcp_ids": [],
        "agents": [],
        "backend": "docker",
        "conn": {"image": "ai1c-agent:latest"},
        "dump_cf": True,   # должны быть проигнорированы для не-local
        "dump_cfe": True,
        "install_tools": True,
        "git_init": True,
    }

    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    data = r.json()

    # ── probe-Project нёс реальный путь → docker_factory получил верный проект ─
    assert len(received_projects) >= 1, "docker_factory не вызвана — provisioner не создан"
    probe = received_projects[0]
    assert probe.path == project_path, (
        f"probe.path должен быть {project_path!r}, получен {probe.path!r}"
    )

    # ── platform_dir дефолтирован до DEFAULT_PLATFORM_DIR ────────────────────
    project_row = data["project"]
    assert project_row["platform_dir"] == DEFAULT_PLATFORM_DIR, (
        f"platform_dir должен быть {DEFAULT_PLATFORM_DIR!r}, "
        f"получен {project_row['platform_dir']!r}"
    )

    # ── проект зарегистрирован с backend="docker" ─────────────────────────────
    projects = registry.list()
    assert len(projects) == 1
    p = projects[0]
    assert p.backend == "docker"
    assert p.path == project_path

    # ── ключевые файлы записаны через RecordingProvisioner ────────────────────
    written_keys = set(rec.writes.keys())

    # .mcp.json (write_env_files)
    assert any(k.endswith(".mcp.json") for k in written_keys), \
        f".mcp.json не записан; keys={sorted(written_keys)[:20]}"

    # .claude/settings.json (deploy_content)
    assert any(k.endswith(".claude/settings.json") for k in written_keys), \
        f"settings.json не записан; keys={sorted(written_keys)[:20]}"

    # .1c-devbase.json (devbase.write_devbase)
    assert any(k.endswith(".1c-devbase.json") for k in written_keys), \
        f".1c-devbase.json не записан; keys={sorted(written_keys)[:20]}"

    # ── git init запущен через prov.run ──────────────────────────────────────
    all_cmds = [cmd for cmd, _ in rec.runs]
    assert any("git" in " ".join(cmd) and "init" in " ".join(cmd)
               for cmd in all_cmds), \
        f"git init не найден в prov.runs; cmds={all_cmds}"

    # ── cf/cfe dump и tools-install выполнялись через RecordingProvisioner ──────
    # is_local-гейт снят: dump и tools-install идут через разрешённый prov (docker).
    cmds_str = " ".join(" ".join(cmd) for cmd in all_cmds)
    assert "DESIGNER" in cmds_str, \
        f"DESIGNER не найден в prov.runs — dump должен идти через docker prov; cmds={all_cmds}"
    # tools-install: pip install вызван через prov.run
    assert any("pip" in " ".join(cmd) for cmd in all_cmds), \
        f"pip не найден в prov.runs — tools-install должен идти через docker prov; cmds={all_cmds}"


def test_docker_create_platform_dir_not_overridden(tmp_path):
    """Если platform_dir явно задан, дефолт не применяется."""
    rec = RecordingProvisioner()
    backends = BackendRegistry(
        "claude",
        docker_factory=lambda project: SimpleNamespace(provisioner=rec),
    )
    monitor = SimpleNamespace(backends=backends)

    client, registry, store = make_client(tmp_path, monitor)

    custom_platform = "/opt/1c/custom"
    body = {
        "name": "dockerproject2",
        "path": "/workspace",
        "identifier": "dev001",
        "email": "dev@example.com",
        "platform_dir": custom_platform,  # явный путь — не должен замениться
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "",
        "web_publication": "",
        "mcp_ids": [],
        "agents": [],
        "backend": "docker",
        "conn": {},
    }

    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    project_row = r.json()["project"]
    assert project_row["platform_dir"] == custom_platform, (
        f"platform_dir не должен меняться, если задан явно: {project_row['platform_dir']!r}"
    )


def test_docker_create_no_platform_dir_other_backend(tmp_path):
    """Для local-бэкенда platform_dir без дефолта → 400."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=mon,
                     store=store)
    client = TestClient(app)

    project_dir = tmp_path / "localproj"
    project_dir.mkdir()
    body = {
        "name": "localproj",
        "path": str(project_dir),
        "identifier": "dev",
        "email": "dev@example.com",
        # platform_dir отсутствует — local должен вернуть 400
        "platform_version": "8.3",
        "db_kind": "file",
        "db_connection": "",
        "mcp_ids": [],
        "agents": [],
        # backend=local по умолчанию
    }
    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 400, r.text
    assert "platform_dir" in r.json()["detail"]

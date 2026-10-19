"""Smoke-test: CREATE flow использует resolved provisioner для backend="ssh".

Цели:
- RecordingProvisioner внедряется через BackendRegistry(ssh_factory=...)
- Файлы записываются на RecordingProvisioner, а не в реальную ФС
- Проект регистрируется с backend="ssh"
- cf/cfe dump + tools-install выполняются через RecordingProvisioner (гейт is_local снят)
- git init запускается через RecordingProvisioner.run
- license_server → conf/nethasp.ini пишется через RecordingProvisioner
"""
import sys
import os
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

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from test_monitor import FakeBackends  # noqa: E402


class RecordingProvisioner:
    """In-memory provisioner: записывает все обращения без реальной ФС/SSH."""

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


def fake_subprocess_run(cmd, **kwargs):
    """Заглушка subprocess.run: RC=0 (для локальных шагов, которых не должно быть)."""
    class _R:
        returncode = 0
        stdout = ""
        stderr = ""
    return _R()


def make_client(tmp_path, monitor):
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    app = create_app(registry=registry, queue=queue, monitor=monitor,
                     store=store, run=fake_subprocess_run)
    return TestClient(app), registry, store


# ─── SSH create smoke test ───────────────────────────────────────────────────

def test_ssh_create_uses_recording_provisioner(tmp_path):
    """Полный happy-path для backend=ssh; проверяет provisioner, регистрацию,
    записанные файлы, git-init и выполнение cf/cfe+tools через prov."""
    rec = RecordingProvisioner()
    backends = BackendRegistry(
        "claude",
        ssh_factory=lambda conn: SimpleNamespace(provisioner=rec),
    )
    monitor = SimpleNamespace(backends=backends)

    client, registry, store = make_client(tmp_path, monitor)

    project_path = "/srv/sshproject"  # виртуальный путь на удалённом хосте
    body = {
        "name": "sshproject",
        "path": project_path,
        "identifier": "dev001",
        "email": "dev@example.com",
        "platform_dir": "/opt/1c",
        "platform_version": "8.3.25",
        "db_kind": "file",
        "db_connection": "File=/data/base",
        "web_publication": "",
        "mcp_ids": [],
        "agents": [],
        "backend": "ssh",
        "conn": {"host": "h", "user": "u", "port": 22, "key_path": None},
        "license_server": "10.0.0.5",
        "dump_cf": True,
        "dump_cfe": True,
        "install_tools": True,
        "git_init": True,
    }

    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    data = r.json()

    # ── проект зарегистрирован с backend="ssh" ────────────────────────────────
    projects = registry.list()
    assert len(projects) == 1
    p = projects[0]
    assert p.backend == "ssh"
    assert p.conn == {"host": "h", "user": "u", "port": 22, "key_path": None}
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

    # conf/nethasp.ini — license_server выставлен
    assert any(k.endswith("conf/nethasp.ini") for k in written_keys), \
        f"conf/nethasp.ini не записан; keys={sorted(written_keys)[:20]}"

    # ── git init запущен через prov.run ──────────────────────────────────────
    all_cmds = [cmd for cmd, _ in rec.runs]
    assert any("git" in " ".join(cmd) and "init" in " ".join(cmd)
               for cmd in all_cmds), \
        f"git init не найден в prov.runs; cmds={all_cmds}"

    # ── cf/cfe dump и tools-install выполнялись через RecordingProvisioner ──────
    # is_local-гейт снят: dump и tools-install идут через разрешённый prov (ssh/docker).
    cmds_str = " ".join(" ".join(cmd) for cmd in all_cmds)
    assert "DESIGNER" in cmds_str, \
        f"DESIGNER не найден в prov.runs — dump должен идти через ssh prov; cmds={all_cmds}"
    # tools-install: pip install вызван через prov.run
    assert any("pip" in " ".join(cmd) for cmd in all_cmds), \
        f"pip не найден в prov.runs — tools-install должен идти через ssh prov; cmds={all_cmds}"


def test_local_create_unchanged(tmp_path):
    """backend=local CREATE не затронут изменениями — проект создаётся нормально."""
    registry_db = open_db(tmp_path / "reg.sqlite")
    registry = ProjectRegistry(registry_db)
    queue = TaskQueue(registry_db)
    mon = Monitor(registry, FakeBackends(None), generating_window=10.0, now_fn=lambda: 1.0)
    store = connect(str(tmp_path / "store.db"))
    init_schema(store)
    project_dir = tmp_path / "localproj"
    project_dir.mkdir()
    app = create_app(registry=registry, queue=queue, monitor=mon, store=store,
                     run=fake_subprocess_run)
    client = TestClient(app)

    body = {
        "name": "localproj",
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
    r = client.post("/api/env/projects/create", json=body)
    assert r.status_code == 200, r.text
    assert r.json()["project"]["name"] == "localproj"
    # local-проект зарегистрирован с backend=local
    projs = registry.list()
    assert len(projs) == 1
    assert projs[0].backend == "local"

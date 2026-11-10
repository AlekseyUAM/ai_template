"""Monitor запускает ssh/docker-агентов через локальные ssh/docker CLI."""
import tempfile
from types import SimpleNamespace

import pytest

from agentmon import config
from agentmon.backends.docker import DEFAULT_WORKDIR, container_name
from agentmon.models import Project
from agentmon.monitor import Monitor
from test_monitor import FakeBackend, FakeBackends, FakeDetachedRunner


class FakeStore:
    def __init__(self):
        self.runs = []

    def add(self, project_id, pid, *, task_id=None, log_file=None, exit_file=None,
            pid_start=None):
        self.runs.append({"project_id": project_id, "pid": pid,
                          "task_id": task_id, "log_file": log_file,
                          "exit_file": exit_file})
        return len(self.runs)

    def running(self, project_id=None):
        return []


def make_project(backend, path, conn=None):
    return Project(id=1, name="p", path=path, backend=backend,
                   conn=conn or {}, claude_cmd=None, created_at=0.0)


def make_monitor(tmp_path, monkeypatch, project, check_error=None):
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "agentmon-runs")
    backend = FakeBackend(key=f"{project.backend}|x", check_error=check_error)
    backends = FakeBackends(by_path={project.path: backend})
    runner = FakeDetachedRunner()
    store = FakeStore()
    mon = Monitor(SimpleNamespace(list=lambda: []), backends,
                  store=store, runner=runner)
    return mon, runner, store, backend


def test_local_launch_keeps_project_cwd(tmp_path, monkeypatch):
    p = make_project("local", "/srv/p")
    mon, runner, store, _ = make_monitor(tmp_path, monkeypatch, p)
    mon.start(p, "привет", task_id=3)
    _, pid, cmd, cwd = runner.calls[0]
    assert cmd[:2] == ["claude", "--dangerously-skip-permissions"]
    assert cwd == "/srv/p"
    assert store.runs[0]["log_file"].startswith("/srv/p/.agentmon/runs/")


def test_ssh_launch_uses_remote_shell_and_local_logs(tmp_path, monkeypatch):
    p = make_project("ssh", "/srv/my project",
                     {"host": "h", "port": 2222, "user": "dev",
                      "key_path": "~/.ssh/id_ed25519"})
    mon, runner, store, backend = make_monitor(tmp_path, monkeypatch, p)
    mon.start(p, "сделай задачу", task_id=1)

    _, pid, cmd, cwd = runner.calls[0]
    assert cmd[0] == "ssh"
    assert "-tt" in cmd
    assert "BatchMode=yes" in cmd
    assert "StrictHostKeyChecking=yes" in cmd
    assert cmd[cmd.index("-p") + 1] == "2222"
    assert cmd[cmd.index("-i") + 1].endswith(".ssh/id_ed25519")
    assert cmd[-2] == "dev@h"
    remote = cmd[-1]
    assert remote.startswith("cd '/srv/my project' && exec ")
    assert "claude" in remote and "-p" in remote and "сделай" in remote
    assert cwd == tempfile.gettempdir()
    assert store.runs[0]["log_file"].startswith(str(tmp_path / "agentmon-runs"))


def test_docker_launch_uses_exec_and_workdir(tmp_path, monkeypatch):
    p = make_project("docker", "/workspace/proj",
                     {"docker_host": "ssh://dev@docker-host"})
    mon, runner, store, backend = make_monitor(tmp_path, monkeypatch, p)
    mon.start(p, "prompt", task_id=1)

    _, pid, cmd, cwd = runner.calls[0]
    assert cmd[:3] == ["docker", "-H", "ssh://dev@docker-host"]
    assert cmd[3:6] == ["exec", "-t", "-w"]
    assert cmd[6] == DEFAULT_WORKDIR
    assert cmd[7] == container_name("/workspace/proj")
    assert cmd[8:10] == ["claude", "--dangerously-skip-permissions"]
    assert cwd == tempfile.gettempdir()
    assert store.runs[0]["log_file"].startswith(str(tmp_path / "agentmon-runs"))


def test_remote_check_failure_prevents_launch(tmp_path, monkeypatch):
    p = make_project("ssh", "/srv/p", {"host": "h"})
    mon, runner, store, _ = make_monitor(tmp_path, monkeypatch, p,
                                         check_error="нет связи")
    with pytest.raises(RuntimeError, match="нет связи"):
        mon.start(p, "x", task_id=1)
    assert runner.calls == []
    assert store.runs == []


def test_ssh_insecure_opt_out_uses_accept_new(tmp_path, monkeypatch):
    p = make_project("ssh", "/srv/p",
                     {"host": "h", "strict_host_key": False})
    mon, runner, store, backend = make_monitor(tmp_path, monkeypatch, p)
    mon.start(p, "x", task_id=1)
    cmd = runner.calls[0][2]
    assert "StrictHostKeyChecking=accept-new" in cmd

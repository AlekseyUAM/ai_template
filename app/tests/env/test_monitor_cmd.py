"""Тесты monitor.start с опциональным параметром cmd."""
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from test_monitor import FakeDetachedRunner
from agentmon.monitor import Monitor
from agentmon.run_store import RunStore


class _FakeBackends:
    """Минимальный двойник BackendRegistry для Monitor."""

    def key_for(self, project):
        return project.key

    def get(self, project):
        return None

    def close_all(self):
        pass


class _FakeRegistry:
    def list(self):
        return []


def _make(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "db.sqlite"), check_same_thread=False)
    store = RunStore(conn)
    runner = FakeDetachedRunner()
    mon = Monitor(_FakeRegistry(), _FakeBackends(), store=store, runner=runner,
                  now_fn=lambda: 1000.0)
    return mon, runner, store


def _project(tmp_path):
    path = str(tmp_path / "proj")
    Path(path).mkdir(parents=True, exist_ok=True)
    return SimpleNamespace(
        id=1,
        path=path,
        name="p",
        key="local||" + path,
        backend="local",
        claude_cmd=None,
        host=None,
    )


def test_start_with_explicit_cmd_uses_that_cmd(tmp_path):
    mon, runner, store = _make(tmp_path)
    project = _project(tmp_path)
    custom_cmd = ["python", "-c", "pass"]

    mon.start(project, cmd=custom_cmd, task_id=5)

    assert runner.calls, "runner.launch не был вызван"
    call = runner.calls[0]
    assert call[0] == "launch"
    assert call[2] == custom_cmd, f"ожидали {custom_cmd}, получили {call[2]}"


def test_start_with_explicit_cmd_records_run(tmp_path):
    mon, runner, store = _make(tmp_path)
    project = _project(tmp_path)

    mon.start(project, cmd=["python", "-c", "pass"], task_id=5)

    running = store.running(project.id)
    assert running, "прогон не записан в store"


def test_start_default_builds_claude_cmd(tmp_path):
    mon, runner, store = _make(tmp_path)
    project = _project(tmp_path)

    mon.start(project, prompt="сделай тест", task_id=7)

    assert runner.calls, "runner.launch не был вызван"
    launched_cmd = runner.calls[0][2]
    assert "-p" in launched_cmd, f"ожидали '-p' в команде, получили: {launched_cmd}"


def test_cmd_for_handles_paths_with_spaces(tmp_path):
    """shlex.split сохраняет quoted-путь с пробелом как один аргумент
    (наивный .split() бил его на части)."""
    mon, runner, store = _make(tmp_path)
    project = _project(tmp_path)
    project.claude_cmd = '"/opt/My Tools/claude" --flag'

    cmd = mon._cmd_for(project, "hi")

    assert cmd[0] == "/opt/My Tools/claude"
    assert cmd[1] == "--flag"
    assert cmd[-2:] == ["-p", "hi"]

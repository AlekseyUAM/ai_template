"""Тесты репозитория прогонов (RunRepo)."""
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.runs import RunRepo


def _repo(tmp_path):
    """Вспомогательная фабрика: создаёт БД, схему и репозиторий прогонов."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    return RunRepo(db)


def test_run_add_and_running(tmp_path):
    r = _repo(tmp_path)
    rid = r.add(project_id=1, pid=1001, task_id=10, log_file="/tmp/out.log", exit_file="/tmp/exit")
    assert rid is not None
    runs = r.running()
    assert len(runs) == 1
    assert runs[0]["id"] == rid
    assert runs[0]["pid"] == 1001
    assert runs[0]["status"] == "running"


def test_run_running_filter_by_project(tmp_path):
    r = _repo(tmp_path)
    r1 = r.add(project_id=1, pid=1001, task_id=10, log_file=None, exit_file=None)
    r2 = r.add(project_id=2, pid=1002, task_id=20, log_file=None, exit_file=None)
    proj1 = r.running(project_id=1)
    assert len(proj1) == 1
    assert proj1[0]["id"] == r1
    proj2 = r.running(project_id=2)
    assert len(proj2) == 1
    assert proj2[0]["id"] == r2


def test_run_finish(tmp_path):
    r = _repo(tmp_path)
    rid = r.add(project_id=1, pid=999, task_id=5, log_file=None, exit_file=None)
    r.finish(rid, "success", exit_code=0)
    row = r.get(rid)
    assert row["status"] == "success"
    assert row["exit_code"] == 0
    # после завершения не попадает в running
    assert r.running() == []


def test_run_finish_idempotent(tmp_path):
    """Повторный вызов finish не меняет уже завершённый прогон (AND status='running')."""
    r = _repo(tmp_path)
    rid = r.add(project_id=1, pid=777, task_id=5, log_file=None, exit_file=None)
    r.finish(rid, "success", exit_code=0)
    r.finish(rid, "failed", exit_code=1)  # второй вызов — игнорируется
    row = r.get(rid)
    assert row["status"] == "success"
    assert row["exit_code"] == 0


def test_run_get(tmp_path):
    r = _repo(tmp_path)
    rid = r.add(project_id=1, pid=42, task_id=7, log_file="/log", exit_file="/exit")
    row = r.get(rid)
    assert row["project_id"] == 1
    assert row["pid"] == 42
    assert row["task_id"] == 7
    assert row["log_file"] == "/log"
    assert row["exit_file"] == "/exit"
    assert r.get(9999) is None


def test_run_latest_for_task(tmp_path):
    r = _repo(tmp_path)
    r1 = r.add(project_id=1, pid=10, task_id=3, log_file=None, exit_file=None)
    r2 = r.add(project_id=1, pid=11, task_id=3, log_file=None, exit_file=None)
    latest = r.latest_for_task(3)
    assert latest["id"] == r2
    # для несуществующей задачи — None
    assert r.latest_for_task(9999) is None


def test_run_default_clock_records_started_at(tmp_path):
    """С clock=time.time (дефолт) add() записывает ненулевой started_at."""
    db = connect(str(tmp_path / "t.db"))
    init_schema(db)
    r = RunRepo(db)  # используем дефолтный clock=time.time
    rid = r.add(project_id=1, pid=123)
    row = r.get(rid)
    assert row["started_at"] is not None
    assert row["started_at"] > 0

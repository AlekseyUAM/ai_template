from agentmon.registry import open_db
from agentmon.run_store import RunStore


def test_add_running_finish(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    store = RunStore(db, clock=lambda: 100.0)
    rid = store.add(1, 4242, task_id=7, log_file="l", exit_file="e")
    run = store.get(rid)
    assert run["pid"] == 4242 and run["status"] == "running" and run["project_id"] == 1
    assert [r["id"] for r in store.running(1)] == [rid]
    assert store.running(2) == []
    store.finish(rid, "done", exit_code=0)
    assert store.get(rid)["status"] == "done" and store.get(rid)["exit_code"] == 0
    assert store.running() == []


def test_finish_is_idempotent(tmp_path):
    from agentmon.registry import open_db
    from agentmon.run_store import RunStore
    db = open_db(tmp_path / "db.sqlite")
    store = RunStore(db, clock=lambda: 1.0)
    rid = store.add(1, 123, exit_file="e")
    store.finish(rid, "done", exit_code=0)
    store.finish(rid, "failed", exit_code=None)      # second finish must not overwrite
    assert store.get(rid)["status"] == "done" and store.get(rid)["exit_code"] == 0

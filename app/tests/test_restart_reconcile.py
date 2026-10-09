"""F4 — end-to-end test: run finished while monitor was down is settled on restart."""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from agentmon.dispatcher import Dispatcher
from agentmon.monitor import Monitor
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db
from agentmon.run_store import RunStore
from test_monitor import FakeBackends, FakeDetachedRunner  # noqa


def test_finished_while_down_settles_and_advances(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    store = RunStore(db)
    p = reg.add(name="p", path=str(tmp_path), backend="local")

    runner = FakeDetachedRunner()
    mon = Monitor(reg, FakeBackends(None), store=store, runner=runner,
                  now_fn=lambda: 1.0)

    # Task was running; monitor "went down"
    tid = q.enqueue(p.id, "задача-1")
    t = q.next(p.id)
    pid = runner.launch(["x"], cwd=str(tmp_path),
                        log_file=str(tmp_path / "l"),
                        exit_file=str(tmp_path / "e"))
    rid = store.add(p.id, pid, task_id=t.id, exit_file=str(tmp_path / "e"))
    q.mark_running(t.id, session_id=None)

    # While monitor was down the process finished successfully
    runner.kill(pid, 0)   # marks pid dead and writes exit_file with "0"

    # Restart: reconcile settles the run
    mon.reconcile()
    assert store.get(rid)["status"] == "done"

    # Dispatcher tick advances the task queue
    disp = Dispatcher(registry=reg, queue=q, monitor=mon)
    disp.tick()
    assert q.running_for(p.id) is None   # task reached done, not stuck

from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db


def make(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    a = reg.add(name="a", path="/proj/a", backend="local")
    b = reg.add(name="b", path="/proj/b", backend="local")
    return TaskQueue(db), a.id, b.id


def test_enqueue_and_list_by_project(tmp_path):
    q, a, b = make(tmp_path)
    q.enqueue(a, "first")
    q.enqueue(a, "second")
    q.enqueue(b, "other")
    assert [t.text for t in q.list(a)] == ["first", "second"]
    assert [t.text for t in q.list()] == ["first", "second", "other"]


def test_next_returns_oldest_queued(tmp_path):
    q, a, _ = make(tmp_path)
    q.enqueue(a, "first")
    q.enqueue(a, "second")
    assert q.next(a).text == "first"


def test_mark_running_and_running_for(tmp_path):
    q, a, _ = make(tmp_path)
    tid = q.enqueue(a, "first")
    assert q.running_for(a) is None
    q.mark_running(tid, session_id="s1")
    run = q.running_for(a)
    assert (run.text, run.session_id, run.status) == ("first", "s1", "running")
    assert q.next(a) is None


def test_mark_done_and_failed(tmp_path):
    q, a, _ = make(tmp_path)
    t1 = q.enqueue(a, "one")
    t2 = q.enqueue(a, "two")
    q.mark_done(t1)
    q.mark_failed(t2)
    assert [t.status for t in q.list(a)] == ["done", "failed"]
    assert all(t.finished_at is not None for t in q.list(a))


def test_delete(tmp_path):
    q, a, _ = make(tmp_path)
    tid = q.enqueue(a, "one")
    q.delete(tid)
    assert q.list(a) == []


def test_requeue_returns_single_task_to_queue(tmp_path):
    q, a, _ = make(tmp_path)
    tid = q.enqueue(a, "one")
    q.mark_running(tid, "s1")
    q.requeue(tid)
    task = q.list(a)[0]
    assert (task.status, task.started_at, task.session_id) == ("queued", None, None)
    assert q.next(a).id == tid


def test_requeue_running_returns_tasks_to_queue(tmp_path):
    q, a, b = make(tmp_path)
    t1 = q.enqueue(a, "one")
    t2 = q.enqueue(b, "two")
    q.enqueue(a, "three")
    q.mark_running(t1, "s1")
    q.mark_running(t2, "s2")
    assert q.requeue_running() == 2
    assert [t.status for t in q.list()] == ["queued", "queued", "queued"]
    assert q.list(a)[0].started_at is None
    assert q.list(a)[0].session_id is None

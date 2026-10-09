import logging
import threading

from agentmon.dispatcher import Dispatcher
from agentmon.queue import TaskQueue
from agentmon.registry import ProjectRegistry, open_db


class FakeMonitor:
    """Двойник монитора под detached-модель.

    start(project, text, task_id) фиксирует запуск и возвращает id прогона;
    task_status(task_id) отдаёт заранее выставленный статус прогона. Завершение
    авторитетно по статусу прогона, а не по эвристике тишины.
    """

    def __init__(self, fail_on_start=None):
        self.started = []            # [(project.path, text, task_id)]
        self.refreshed = 0
        self.fail_on_start = fail_on_start
        self._status = {}            # task_id -> "running"|"done"|"failed"|None
        self._next_run = 100

    def refresh(self):
        self.refreshed += 1

    def start(self, project, text, task_id=None):
        if self.fail_on_start:
            raise RuntimeError(self.fail_on_start)
        self.started.append((project.path, text, task_id))
        self._status[task_id] = "running"
        run_id = self._next_run
        self._next_run += 1
        return str(run_id)

    def task_status(self, task_id):
        return self._status.get(task_id)

    def set_status(self, task_id, value):
        self._status[task_id] = value


def make(tmp_path, monitor, max_requeues=3):
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    q = TaskQueue(db)
    disp = Dispatcher(registry=reg, queue=q, monitor=monitor,
                      max_requeues=max_requeues)
    return reg, q, disp


def test_starts_next_task_and_marks_it_running(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/proj/a", backend="local")
    tid = q.enqueue(p.id, "do first")
    disp.tick()
    assert mon.started == [("/proj/a", "do first", tid)]
    assert q.running_for(p.id).text == "do first"


def test_only_one_task_runs_per_project(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/proj/a", backend="local")
    q.enqueue(p.id, "first")
    q.enqueue(p.id, "second")
    disp.tick()
    disp.tick()                      # первая всё ещё running → вторую не стартуем
    assert len(mon.started) == 1
    assert mon.started[0][1] == "first"


def test_done_task_marks_done_and_next_starts(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/proj/a", backend="local")
    t1 = q.enqueue(p.id, "first")
    q.enqueue(p.id, "second")
    disp.tick()                      # стартует first
    mon.set_status(t1, "done")
    disp.tick()                      # first done → mark_done (на этом тике return)
    assert q.list(p.id)[0].status == "done"
    disp.tick()                      # следующий тик стартует second
    assert mon.started[-1][1] == "second"


def test_failed_task_is_requeued_then_failed_after_max(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon, max_requeues=2)
    p = reg.add(name="a", path="/srv/a", backend="local")
    tid = q.enqueue(p.id, "first")

    # 1-й провал → requeue
    disp.tick()
    mon.set_status(tid, "failed")
    disp.tick()
    assert q.running_for(p.id) is None
    assert q.next(p.id).text == "first"

    # 2-й провал → requeue
    disp.tick()                      # снова стартует (status сбросился в running)
    mon.set_status(tid, "failed")
    disp.tick()
    assert q.next(p.id).text == "first"

    # 3-й провал → failed
    disp.tick()
    mon.set_status(tid, "failed")
    disp.tick()
    assert q.running_for(p.id) is None
    assert q.list(p.id)[0].status == "failed"
    assert q.next(p.id) is None


def test_requeue_counter_cleared_on_done(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/srv/a", backend="local")
    tid = q.enqueue(p.id, "first")

    disp.tick()
    mon.set_status(tid, "failed")
    disp.tick()                      # requeue, счётчик=1
    assert disp._requeues.get(tid) == 1

    disp.tick()                      # снова стартует
    mon.set_status(tid, "done")
    disp.tick()                      # done → счётчик снят
    assert tid not in disp._requeues


def test_running_status_waits(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/proj/a", backend="local")
    q.enqueue(p.id, "first")
    q.enqueue(p.id, "second")
    disp.tick()
    disp.tick()                      # status running → ждём
    assert q.running_for(p.id).text == "first"
    assert len(mon.started) == 1


def test_none_status_waits_without_completing(tmp_path):
    """task_status None (прогон только создан) не завершает задачу."""
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/proj/a", backend="local")
    tid = q.enqueue(p.id, "first")
    q.enqueue(p.id, "second")
    disp.tick()
    mon.set_status(tid, None)
    disp.tick()
    assert q.running_for(p.id).text == "first"
    assert len(mon.started) == 1


def test_project_without_tasks_does_not_start(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    reg.add(name="a", path="/proj/a", backend="local")
    disp.tick()
    assert mon.started == []


def test_each_project_is_dispatched_independently(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    a = reg.add(name="a", path="/proj/a", backend="local")
    b = reg.add(name="b", path="/proj/b", backend="local")
    q.enqueue(a.id, "ta")
    q.enqueue(b.id, "tb")
    disp.tick()
    assert sorted(text for _, text, _ in mon.started) == ["ta", "tb"]


def test_start_failure_leaves_task_queued(tmp_path):
    mon = FakeMonitor(fail_on_start="хост недоступен")
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/srv/a", backend="local")
    q.enqueue(p.id, "do it")
    disp.tick()                      # не должно бросать
    assert q.next(p.id).text == "do it"
    assert q.running_for(p.id) is None


def test_failure_on_one_project_does_not_block_another(tmp_path):
    class Picky(FakeMonitor):
        def start(self, project, text, task_id=None):
            if project.path == "/bad":
                raise RuntimeError("недоступен")
            return super().start(project, text, task_id)

    mon = Picky()
    reg, q, disp = make(tmp_path, mon)
    bad = reg.add(name="bad", path="/bad", backend="local")
    good = reg.add(name="good", path="/good", backend="local")
    q.enqueue(bad.id, "x")
    q.enqueue(good.id, "y")
    disp.tick()
    assert [text for _, text, _ in mon.started] == ["y"]


def test_tick_refreshes_once(tmp_path):
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    reg.add(name="a", path="/proj/a", backend="local")
    disp.tick()
    assert mon.refreshed == 1


# --- Ограничение повторов запуска (Finding 6) ---


def test_start_failure_marks_task_failed_after_bound(tmp_path, caplog):
    """Сломанный старт не должен повторяться вечно."""
    mon = FakeMonitor(fail_on_start="нет такого каталога")
    reg, q, disp = make(tmp_path, mon)
    disp.max_start_failures = 3
    p = reg.add(name="a", path="/srv/a", backend="local")
    q.enqueue(p.id, "first")

    disp.tick()
    assert q.next(p.id).text == "first"
    disp.tick()
    assert q.next(p.id).text == "first"
    with caplog.at_level(logging.ERROR, logger="agentmon.dispatcher"):
        disp.tick()
    assert q.next(p.id) is None
    assert q.list(p.id)[0].status == "failed"
    assert any(rec.levelno >= logging.ERROR and "/srv/a" in rec.getMessage()
               for rec in caplog.records)
    disp.tick()
    assert disp._start_failures == {}


def test_start_failure_counter_is_cleared_on_success(tmp_path):
    mon = FakeMonitor(fail_on_start="связь моргнула")
    reg, q, disp = make(tmp_path, mon)
    disp.max_start_failures = 3
    p = reg.add(name="a", path="/srv/a", backend="local")
    tid = q.enqueue(p.id, "first")

    disp.tick()
    disp.tick()
    assert disp._start_failures[tid] == 2

    mon.fail_on_start = None
    disp.tick()
    assert disp._start_failures == {}
    assert q.running_for(p.id).id == tid


def test_start_failures_are_counted_per_task(tmp_path):
    mon = FakeMonitor(fail_on_start="нет связи")
    reg, q, disp = make(tmp_path, mon)
    disp.max_start_failures = 2
    a = reg.add(name="a", path="/srv/a", backend="local")
    b = reg.add(name="b", path="/srv/b", backend="local")
    q.enqueue(a.id, "for a")
    q.enqueue(b.id, "for b")

    disp.tick()
    disp.tick()
    assert [t.status for t in q.list(a.id)] == ["failed"]
    assert [t.status for t in q.list(b.id)] == ["failed"]


def test_programming_error_is_logged_apart_from_outage(tmp_path, caplog):
    """TypeError в диспетчере не должен выглядеть как обрыв связи."""
    class Exploding(FakeMonitor):
        def task_status(self, task_id):
            raise TypeError("неверный тип аргумента")

    mon = Exploding()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/srv/a", backend="local")
    tid = q.enqueue(p.id, "first")
    q.mark_running(tid, "s1")

    with caplog.at_level(logging.WARNING, logger="agentmon.dispatcher"):
        disp.tick()
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors and errors[0].exc_info is not None


def test_tick_is_callable_from_a_worker_thread(tmp_path):
    """dispatch_loop уводит tick в пул потоков — он не должен зависеть от петли."""
    mon = FakeMonitor()
    reg, q, disp = make(tmp_path, mon)
    p = reg.add(name="a", path="/srv/a", backend="local")
    q.enqueue(p.id, "first")

    error = []
    thread = threading.Thread(target=lambda: _run(disp, error))
    thread.start()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert error == []
    assert q.running_for(p.id).text == "first"


def _run(disp, error):
    try:
        disp.tick()
    except Exception as exc:              # pragma: no cover — диагностика
        error.append(exc)

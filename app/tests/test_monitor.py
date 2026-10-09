import threading
import time
from pathlib import Path

import pytest

from agentmon.models import FileRef
from agentmon.monitor import Monitor
from agentmon.registry import ProjectRegistry, open_db
from agentmon.run_store import RunStore


class FakeDetachedRunner:
    """Двойник detached-раннера монитора: управляемая жизнь PID.

    launch(...) выдаёт растущий PID и помечает его живым. is_running читает
    множество живых PID. terminate убивает PID. kill(pid, code) гасит процесс
    и пишет код выхода в его exit_file — так тест воспроизводит естественную
    смерть агента, которую потом подхватит reconcile().
    """

    def __init__(self, fail_on_launch=None):
        self.alive: set[int] = set()
        self.calls = []
        self.fail_on_launch = fail_on_launch
        self._exit_files: dict[int, str] = {}
        self._next_pid = 1000

    def launch(self, cmd, cwd, log_file, exit_file):
        if self.fail_on_launch:
            raise RuntimeError(self.fail_on_launch)
        pid = self._next_pid
        self._next_pid += 1
        self.alive.add(pid)
        self._exit_files[pid] = exit_file
        self.calls.append(("launch", pid, cmd, cwd))
        return pid

    def is_running(self, pid):
        return pid in self.alive

    def terminate(self, pid):
        self.calls.append(("terminate", pid))
        self.alive.discard(pid)

    def kill(self, pid, code=0):
        """Снаружи: процесс завершился сам, записав код выхода."""
        self.alive.discard(pid)
        exit_file = self._exit_files.get(pid)
        if exit_file:
            Path(exit_file).parent.mkdir(parents=True, exist_ok=True)
            Path(exit_file).write_text(str(code), encoding="utf-8")


class FakeRunner:
    def __init__(self, fail_on_start=None):
        self.alive: set[str] = set()
        self.calls = []
        self.fail_on_start = fail_on_start

    def start(self, project):
        if self.fail_on_start:
            raise RuntimeError(self.fail_on_start)
        self.alive.add(project.key)
        self.calls.append(("start", project.key))
        return project.key

    def send_input(self, agent_id, text):
        self.calls.append(("send", agent_id, text))

    def stop(self, agent_id, mode):
        # Как в настоящих раннерах: незапущенный агент — это KeyError.
        if agent_id not in self.alive:
            raise KeyError(f"агент не запущен: {agent_id}")
        self.calls.append(("stop", agent_id, mode))
        if mode == "kill":
            self.alive.discard(agent_id)

    def is_alive(self, agent_id):
        return agent_id in self.alive

    def tail_output(self, agent_id, limit=65536):
        return "ВЫВОД"

    def shutdown_all(self):
        self.alive.clear()
        self.calls.append(("shutdown",))


class FakeFiles:
    def __init__(self):
        self.data = {}
        self.meta = {}
        self.list_files_calls = 0

    def add(self, path, dir_name, sid, mtime, body):
        self.data[path] = body.encode()
        self.meta[path] = (dir_name, sid, mtime)

    def home_projects_dir(self):
        return "/home/u/.claude/projects"

    def list_files(self, projects_dir):
        self.list_files_calls += 1
        return [FileRef(path=p, dir_name=d, session_id=s,
                        size=len(self.data[p]), mtime=m)
                for p, (d, s, m) in self.meta.items()]

    def read_from(self, path, offset):
        blob = self.data[path][offset:]
        return blob, offset + len(blob)


class FakeBackend:
    def __init__(self, key="local", runner=None, files=None, check_error=None,
                 broken=False):
        self.key = key
        self.runner = runner or FakeRunner()
        self.files = files or FakeFiles()
        self.check_error = check_error
        self.closed = False
        self.is_broken = broken

    def check(self):
        if self.check_error:
            raise RuntimeError(self.check_error)

    def close(self):
        # Как настоящий Backend.close: закрытие машины гасит всех её агентов.
        self.closed = True
        self.runner.shutdown_all()


class FakeBackends:
    def __init__(self, backend=None, by_path=None):
        self.backend = backend or FakeBackend()
        # by_path: project.path -> FakeBackend, для проектов на других бэкендах.
        # Проект, для которого пути нет в словаре, получает self.backend —
        # это сохраняет поведение по умолчанию для однобэкендовых тестов.
        self.by_path = by_path or {}
        self.invalidated = []

    def _for(self, project):
        return self.by_path.get(project.path, self.backend)

    def key_for(self, project):
        return self._for(project).key

    def get(self, project):
        return self._for(project)

    def invalidate(self, key):
        self.invalidated.append(key)

    def items(self):
        seen = {self.backend.key: self.backend}
        for backend in self.by_path.values():
            seen[backend.key] = backend
        return list(seen.items())

    def close_all(self):
        self.backend.close()
        for backend in self.by_path.values():
            backend.close()


def assistant(cwd, inp, out, text):
    return ('{"type":"assistant","cwd":"%s","message":{"model":"claude-opus-4-8",'
            '"usage":{"input_tokens":%d,"output_tokens":%d,'
            '"cache_read_input_tokens":0,"cache_creation_input_tokens":0},'
            '"content":[{"type":"text","text":"%s"}]}}\n' % (cwd, inp, out, text))


def make(tmp_path, backend=None, now=1000.0, store=True, runner=None):
    """Монитор для тестов. store=True → реальный RunStore на tmp sqlite и
    управляемый FakeDetachedRunner (управление агентами включено). store=None →
    управление агентами выключено (как в env-тестах с одними HTTP-ручками)."""
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    backends = FakeBackends(backend)
    run_store = RunStore(db) if store is True else store
    if store is True and runner is None:
        runner = FakeDetachedRunner()
    mon = Monitor(reg, backends, store=run_store, runner=runner,
                  generating_window=10.0, now_fn=lambda: now)
    mon.test_runner = runner           # удобный доступ в тестах
    return reg, backends, mon


def test_start_records_a_run_and_returns_its_id(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    run_id = mon.start(p, "сделай", task_id=7)
    assert run_id == str(mon.store.get(int(run_id))["id"])
    run = mon.store.latest_for_task(7)
    assert run["project_id"] == p.id and run["status"] == "running"
    assert mon.test_runner.calls[0][0] == "launch"


def test_start_disabled_without_store(tmp_path):
    reg, backends, mon = make(tmp_path, store=None)
    p = reg.add(name="a", path="/srv/a", backend="local")
    with pytest.raises(RuntimeError):
        mon.start(p, "сделай")


def test_is_alive_reflects_runner_pid_liveness(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path=str(tmp_path / "proj"), backend="local")
    assert mon.is_alive(p) is False
    mon.start(p, "go", task_id=1)
    assert mon.is_alive(p) is True
    # PID умер — агент больше не жив.
    for pid in list(mon.test_runner.alive):
        mon.test_runner.kill(pid, 0)
    assert mon.is_alive(p) is False


def test_reconcile_finishes_dead_run_done_on_zero_exit(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path=str(tmp_path / "proj"), backend="local")
    run_id = int(mon.start(p, "go", task_id=1))
    (pid,) = tuple(mon.test_runner.alive)
    mon.test_runner.kill(pid, 0)
    mon.reconcile()
    run = mon.store.get(run_id)
    assert run["status"] == "done" and run["exit_code"] == 0
    assert mon.task_status(1) == "done"


def test_reconcile_finishes_dead_run_failed_on_nonzero_exit(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path=str(tmp_path / "proj"), backend="local")
    run_id = int(mon.start(p, "go", task_id=2))
    (pid,) = tuple(mon.test_runner.alive)
    mon.test_runner.kill(pid, 3)
    mon.reconcile()
    assert mon.store.get(run_id)["status"] == "failed"
    assert mon.task_status(2) == "failed"


def test_task_status_running_then_none_for_unknown(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=5)
    assert mon.task_status(5) == "running"
    assert mon.task_status(999) is None


def test_task_status_none_without_store(tmp_path):
    reg, backends, mon = make(tmp_path, store=None)
    assert mon.task_status(1) is None


def test_stop_terminates_pid_and_finishes_run(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    run_id = int(mon.start(p, "go", task_id=1))
    (pid,) = tuple(mon.test_runner.alive)
    mon.stop(p, "kill")
    assert ("terminate", pid) in mon.test_runner.calls
    assert mon.store.get(run_id)["status"] == "failed"
    assert mon.is_alive(p) is False


def test_sessions_hide_projects_without_live_agent(tmp_path):
    files = FakeFiles()
    files.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, assistant("/srv/a", 10, 5, "hi"))
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path, backend)
    reg.add(name="a", path="/srv/a", backend="local")
    assert mon.sessions() == []


def test_sessions_show_live_agent_with_snapshot(tmp_path):
    files = FakeFiles()
    files.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, assistant("/srv/a", 10, 5, "hi"))
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=1)
    sessions = mon.sessions()
    assert len(sessions) == 1
    s = sessions[0]
    assert (s["project_id"], s["project_path"], s["name"]) == (p.id, "/srv/a", "a")
    assert (s["input_tokens"], s["state"], s["session_id"]) == (10, "generating", "s1")


def test_live_agent_without_log_still_listed(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=1)
    s = mon.sessions()[0]
    assert s["session_id"] is None
    assert (s["state"], s["input_tokens"], s["cost_usd"]) == ("idle", 0, 0.0)


def test_dead_log_of_deleted_project_never_appears(tmp_path):
    files = FakeFiles()
    files.add("/p/-x/s1.jsonl", "-x", "s1", 995.0, assistant("/other/proj", 1, 1, "hi"))
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=1)
    assert [s["project_path"] for s in mon.sessions()] == ["/srv/a"]


def test_state_and_transcript_use_observer(tmp_path):
    files = FakeFiles()
    body = ('{"type":"user","cwd":"/srv/a","message":{"content":'
            '[{"type":"text","text":"вопрос"}]}}\n')
    files.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, body)
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.refresh()
    assert mon.state(p) == "generating"
    assert mon.transcript(p) == [{"role": "user", "text": "вопрос"}]


def test_capture_returns_run_log(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path=str(tmp_path / "srv_a"), backend="local")
    mon.start(p, "go", task_id=1)
    run = mon.store.running(p.id)[-1]
    log = Path(run["log_file"])
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("ВЫВОД", encoding="utf-8")
    assert mon.capture(p) == "ВЫВОД"


def test_start_failure_is_recorded_and_reraised(tmp_path):
    runner = FakeDetachedRunner(fail_on_launch="нет связи")
    reg, backends, mon = make(tmp_path, runner=runner)
    p = reg.add(name="a", path="/srv/a", backend="local")
    with pytest.raises(RuntimeError):
        mon.start(p, "go")
    assert "нет связи" in mon.last_error(p)


def test_successful_call_clears_previous_error(tmp_path):
    runner = FakeDetachedRunner(fail_on_launch="нет связи")
    reg, backends, mon = make(tmp_path, runner=runner)
    p = reg.add(name="a", path="/srv/a", backend="local")
    with pytest.raises(RuntimeError):
        mon.start(p, "go")
    runner.fail_on_launch = None
    mon.start(p, "go", task_id=1)
    assert mon.last_error(p) is None


def test_check_reports_backend_failure(tmp_path):
    backend = FakeBackend(check_error="хост недоступен")
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="ssh", conn={"host": "srv"})
    with pytest.raises(RuntimeError):
        mon.check(p)
    assert "хост недоступен" in mon.last_error(p)


def test_refresh_survives_broken_backend(tmp_path):
    class Exploding(FakeFiles):
        def list_files(self, projects_dir):
            raise RuntimeError("связь оборвана")

    backend = FakeBackend(files=Exploding())
    reg, backends, mon = make(tmp_path, backend)
    reg.add(name="a", path="/srv/a", backend="local")
    mon.refresh()                     # не должно бросать
    assert mon.sessions() == []


def test_shutdown_closes_backends(tmp_path):
    reg, backends, mon = make(tmp_path)
    mon.shutdown()
    assert backends.backend.closed is True


def test_two_projects_on_same_backend_share_one_observer(tmp_path):
    reg, backends, mon = make(tmp_path)
    p1 = reg.add(name="a", path="/srv/a", backend="local")
    p2 = reg.add(name="b", path="/srv/b", backend="local")
    assert mon._observer(p1) is mon._observer(p2)


def test_refresh_touches_shared_backend_once_for_two_projects(tmp_path):
    files = FakeFiles()
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path, backend)
    reg.add(name="a", path="/srv/a", backend="local")
    reg.add(name="b", path="/srv/b", backend="local")
    mon.refresh()
    assert files.list_files_calls == 1


def test_projects_on_different_backends_get_different_observers(tmp_path):
    backend_a = FakeBackend(key="local|host-a")
    backend_b = FakeBackend(key="local|host-b")
    reg, backends, mon = make(tmp_path, backend_a)
    backends.by_path["/srv/b"] = backend_b
    p1 = reg.add(name="a", path="/srv/a", backend="local")
    p2 = reg.add(name="b", path="/srv/b", backend="local")
    assert mon._observer(p1) is not mon._observer(p2)


def test_observer_cache_self_heals_after_backend_replaced(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    obs1 = mon._observer(p)
    replacement = FakeBackend(key=backends.backend.key)
    backends.backend = replacement
    obs2 = mon._observer(p)
    assert obs2 is not obs1
    assert obs2.files is replacement.files


# --- Недоступный бэкенд виден пользователю (Finding 8) ---


def test_broken_backend_becomes_a_visible_error(tmp_path):
    """SSH глушит отказы внутри — монитор обязан спросить бэкенд прямо."""
    backend = FakeBackend(key="ssh|root@srv:22", broken=True)
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="ssh", conn={"host": "srv"})
    assert mon.last_error(p) is None
    mon.refresh()
    assert "srv" in mon.last_error(p)


def test_backend_error_clears_when_the_host_comes_back(tmp_path):
    backend = FakeBackend(key="ssh|root@srv:22", broken=True)
    reg, backends, mon = make(tmp_path, backend)
    p = reg.add(name="a", path="/srv/a", backend="ssh", conn={"host": "srv"})
    mon.refresh()
    assert mon.last_error(p)
    backend.is_broken = False
    mon.refresh()
    assert mon.last_error(p) is None


def test_broken_backend_error_reaches_every_project_of_that_host(tmp_path):
    backend = FakeBackend(key="ssh|root@srv:22", broken=True)
    reg, backends, mon = make(tmp_path, backend)
    a = reg.add(name="a", path="/srv/a", backend="ssh", conn={"host": "srv"})
    b = reg.add(name="b", path="/srv/b", backend="ssh", conn={"host": "srv"})
    mon.refresh()
    assert mon.last_error(a) and mon.last_error(b)


def test_operation_error_wins_over_backend_error(tmp_path):
    backend = FakeBackend(key="ssh|root@srv:22", broken=True)
    runner = FakeDetachedRunner(fail_on_launch="каталога нет")
    reg, backends, mon = make(tmp_path, backend, runner=runner)
    p = reg.add(name="a", path="/srv/a", backend="ssh", conn={"host": "srv"})
    mon.refresh()
    with pytest.raises(RuntimeError):
        mon.start(p, "go")
    assert "каталога нет" in mon.last_error(p)


# --- Ошибка не переживает проект (Finding 11) ---


def test_forget_drops_the_error_of_a_project(tmp_path):
    runner = FakeDetachedRunner(fail_on_launch="нет связи")
    reg, backends, mon = make(tmp_path, runner=runner)
    p = reg.add(name="a", path="/srv/a", backend="local")
    with pytest.raises(RuntimeError):
        mon.start(p, "go")
    assert mon.last_error(p)
    mon.forget(p)
    assert mon.last_error(p) is None


def test_invalidate_backend_drops_connection_and_observer(tmp_path):
    reg, backends, mon = make(tmp_path)
    p = reg.add(name="a", path="/srv/a", backend="local")
    obs = mon._observer(p)
    mon.invalidate_backend(p)
    assert backends.invalidated == ["local"]
    assert mon._observer(p) is not obs


# --- Одновременное наблюдение не должно удваивать учёт (Finding 7) ---


class SlowFiles(FakeFiles):
    """read_from намеренно медленный: так два потока успевают войти вместе."""

    def read_from(self, path, offset):
        time.sleep(0.05)
        return super().read_from(path, offset)


def _single_threaded_tokens(tmp_path, files):
    backend = FakeBackend(files=files)
    (tmp_path / "one").mkdir(exist_ok=True)
    reg, backends, mon = make(tmp_path / "one", backend)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=1)
    mon.sessions()
    mon.sessions()
    return mon.sessions()[0]["input_tokens"]


def test_concurrent_observation_does_not_double_count_tokens(tmp_path):
    (tmp_path / "one").mkdir()
    (tmp_path / "many").mkdir()
    body = assistant("/srv/a", 10, 5, "hi")

    files_one = SlowFiles()
    files_one.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, body)
    expected = _single_threaded_tokens(tmp_path, files_one)

    files = SlowFiles()
    files.add("/p/-a/s1.jsonl", "-a", "s1", 995.0, body)
    backend = FakeBackend(files=files)
    reg, backends, mon = make(tmp_path / "many", backend)
    p = reg.add(name="a", path="/srv/a", backend="local")
    mon.start(p, "go", task_id=1)

    errors = []

    def worker(fn):
        try:
            fn()
        except Exception as exc:               # pragma: no cover — диагностика
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(mon.sessions,)),
        threading.Thread(target=worker, args=(mon.refresh,)),
        threading.Thread(target=worker, args=(lambda: mon.transcript(p),)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not any(t.is_alive() for t in threads)
    assert errors == []
    assert mon.sessions()[0]["input_tokens"] == expected == 10
    assert mon.transcript(p) == [{"role": "assistant", "text": "hi"}]


def test_enforce_timeout_kills_overrunning_run(tmp_path):
    """enforce_timeout: прогон дольше лимита снимается (terminate) и → failed;
    в пределах лимита — не трогается."""
    db = open_db(tmp_path / "db.sqlite")
    reg = ProjectRegistry(db)
    backends = FakeBackends(None)
    clock = {"t": 1000.0}
    run_store = RunStore(db, clock=lambda: clock["t"])
    runner = FakeDetachedRunner()
    mon = Monitor(reg, backends, store=run_store, runner=runner,
                  generating_window=10.0, now_fn=lambda: clock["t"])

    p = reg.add(name="a", path=str(tmp_path / "a"), backend="local")
    run_id = mon.start(p, "go", task_id=7)          # started_at = 1000.0
    pid = run_store.get(int(run_id))["pid"]

    # 59 минут < лимита 60 → не таймаут
    clock["t"] = 1000.0 + 59 * 60
    assert mon.enforce_timeout(7, 60) is False
    assert mon.task_status(7) == "running"
    assert ("terminate", pid) not in runner.calls

    # 61 минута > лимита 60 → таймаут: процесс снят, прогон failed
    clock["t"] = 1000.0 + 61 * 60
    assert mon.enforce_timeout(7, 60) is True
    assert mon.task_status(7) == "failed"
    assert ("terminate", pid) in runner.calls

    # повторный вызов идемпотентен — прогон уже не running
    assert mon.enforce_timeout(7, 60) is False


def test_enforce_timeout_noop_without_store(tmp_path):
    """Без store enforce_timeout просто возвращает False."""
    reg, backends, mon = make(tmp_path, store=None)
    assert mon.enforce_timeout(1, 60) is False

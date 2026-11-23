import json
import os
import signal
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentmon.env import code_index_bench as B
from agentmon.env import code_index_release as R


def test_clean_removes_dirs_and_legacy_container(tmp_path):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 0, "serve": 0}')
    catalog = tmp_path / "catalog"; (catalog / ".code-index").mkdir(parents=True)
    calls = []
    B.clean_code_index(ci, catalog, run=lambda cmd, **k: calls.append(cmd),
                       log=lambda _m: None)
    assert not ci.exists()
    assert not (catalog / ".code-index").exists()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


def test_start_writes_pid_and_toml(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    def fake_download(dest, *, log=None):
        Path(dest).mkdir(parents=True, exist_ok=True)
        bin_path.write_text("bin", encoding="utf-8")
        return bin_path
    pids = iter([111, 222])
    class Proc:
        def __init__(self):
            self.pid = next(pids)
    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    index = B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=fake_download, popen=lambda *a, **k: Proc(),
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""))
    assert index.daemon_pid == 111 and index.serve_pid == 222
    assert (ci / "benchmark-pids.json").is_file()
    text = (ci / "daemon.toml").read_text(encoding="utf-8")
    assert 'alias = "a"' in text and str(catalog.resolve()) in text


def test_stop_kills_own_pids(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    killed, calls = [], []
    checks = {"n": 0}

    def ours(pid, run):
        checks["n"] += 1
        return checks["n"] <= 2          # живы только до SIGTERM

    monkeypatch.setattr(B, "_is_our_process", ours)
    B.stop_code_index(ci, run=lambda cmd, **k: calls.append(cmd),
                      kill=lambda pid, sig: killed.append(pid),
                      sleep=lambda _s: None, clock=lambda: 0.0,
                      log=lambda _m: None)
    assert killed == [10, 11]
    assert not (ci / "benchmark-pids.json").exists()


# --- дополнительные кейсы ---

def test_stop_skips_foreign_pids_and_missing_dir(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    killed = []
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: False)
    for target in (ci, tmp_path / "missing"):
        B.stop_code_index(target, run=lambda cmd, **k: None,
                          kill=lambda pid, sig: killed.append(pid),
                          sleep=lambda _s: None, clock=lambda: 0.0,
                          log=lambda _m: None)
    assert killed == []
    assert not (ci / "benchmark-pids.json").exists()


def test_clean_tolerates_missing_code_index_dir(tmp_path):
    catalog = tmp_path / "catalog"; (catalog / ".code-index").mkdir(parents=True)
    calls = []
    B.clean_code_index(tmp_path / "missing", catalog,
                       run=lambda cmd, **k: calls.append(cmd),
                       log=lambda _m: None)
    assert not (catalog / ".code-index").exists()
    assert any(cmd[:3] == ["docker", "rm", "-f"] for cmd in calls)


def test_start_cleans_first_and_spawns_detached(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / B.BENCHMARK_MARKER).write_text("benchmark\n", encoding="utf-8")
    (ci / "old.txt").write_text("old", encoding="utf-8")
    catalog = tmp_path / "catalog"; catalog.mkdir()
    spawned = []
    pids = iter([1, 2])

    def fake_download(dest, *, log=None):
        path = Path(dest) / "bsl-indexer"
        path.write_text("bin", encoding="utf-8")
        return path

    def fake_popen(args, **kwargs):
        spawned.append((args, kwargs))
        return SimpleNamespace(pid=next(pids))

    monkeypatch.setattr(B, "_spawn_kwargs",
                        lambda: {"start_new_session": True})
    index = B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=fake_download, popen=fake_popen,
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""),
        log=lambda _m: None)
    assert not (ci / "old.txt").exists()
    assert spawned[0][0][1:] == ["daemon", "run"]
    assert spawned[1][0][1:3] == ["serve", "--transport"]
    assert all(kw.get("start_new_session") is True for _a, kw in spawned)
    pids_file = json.loads((ci / "benchmark-pids.json").read_text("utf-8"))
    assert pids_file == {"daemon": 1, "serve": 2}
    assert index == B.NativeIndex(ci, ci / "bsl-indexer", 1, 2)


def _ready_run(status, calls):
    """Фейковый ``run``: JSON статуса — только на ``daemon status --json``.

    Остальные команды (tasklist/docker/...) получают пустой успешный вывод,
    как настоящий ``tasklist`` о чужом PID: иначе ``_is_our_process`` счёл бы
    любой PID "нашим".
    """
    def run(*args, **kwargs):
        cmd = list(args[0])
        calls.append(cmd)
        out = status if cmd[-2:] == ["status", "--json"] else ""
        return SimpleNamespace(returncode=0, stdout=out, stderr="")
    return run


def _counting_clock():
    calls = {"n": 0}

    def clock():
        calls["n"] += 1
        return float(calls["n"])       # 1.0, 2.0, … — растущее время

    return clock


def test_wait_ready_returns_when_index_ready(monkeypatch):
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/p", "status": "ready"}]})
    calls = []
    B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                            run=_ready_run(status, calls),
                            sleep=lambda _s: None, clock=_counting_clock(),
                            tcp_ok=lambda _u: True,
                            log=lambda _m: None)
    assert calls == [[str(index.binary), "daemon", "status", "--json"]]


def test_wait_ready_raises_on_dead_process(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: False)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    with pytest.raises(SetupError):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run("", []), sleep=lambda _s: None,
                                clock=_counting_clock(), tcp_ok=lambda _u: True,
                                log=lambda _m: None)


def test_wait_ready_raises_on_timeout(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/p", "status": "indexing"}]})
    with pytest.raises(SetupError):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run(status, []),
                                sleep=lambda _s: None, clock=_counting_clock(),
                                tcp_ok=lambda _u: True,
                                log=lambda _m: None)


def test_module_does_not_import_bench_setup_at_import_time():
    import subprocess
    import sys
    src = str(Path(__file__).resolve().parents[3] / "src")
    code = ("import agentmon.env.code_index_bench, sys; "
            "sys.exit(int('bench_setup' in sys.modules))")
    result = subprocess.run([sys.executable, "-c", code],
                            capture_output=True, text=True, timeout=30,
                            env={**os.environ, "PYTHONPATH": src})
    assert result.returncode == 0, result.stderr


def test_existing_binary_finds_downloaded(tmp_path):
    assert R.existing_binary(tmp_path) is None
    nested = tmp_path / "v1" / "bin"
    nested.mkdir(parents=True)
    binary = nested / "bsl-indexer"
    binary.write_text("bin", encoding="utf-8")
    assert R.existing_binary(tmp_path) == binary


# --- fix-ревью: дедлайн stop, error-статус, потерянный PID демона ---

class _Clock:
    """Сценарий времени: значения по одному, дальше — за пределом срока."""

    def __init__(self, values, past=11.0):
        self.values = list(values)
        self.past = past

    def __call__(self):
        return self.values.pop(0) if self.values else self.past


def test_stop_gives_up_waiting_after_deadline(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    waits, signals = [], []
    alive = {10, 11}

    def wait(pids, **kw):
        waits.append((sorted(pids), kw["timeout"]))
        return B._wait_exit(pids, **kw)

    def kill(pid, sig):
        signals.append((pid, sig))
        if sig == signal.SIGKILL:
            alive.discard(pid)          # SIGKILL добил процесс

    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: pid in alive)
    monkeypatch.setattr(B, "STOP_TIMEOUT_SEC", 10.0)
    B.stop_code_index(ci, run=lambda cmd, **k: None, kill=kill,
                      clock=_Clock([0.0, 0.0, 10.0, 10.0]), wait=wait,
                      log=lambda _m: None)
    assert waits == [([10, 11], 10.0)]
    assert signals == [(10, signal.SIGTERM), (11, signal.SIGTERM),
                       (10, signal.SIGKILL), (11, signal.SIGKILL)]


def test_stop_no_sigkill_when_wait_witnessed_exit(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "benchmark-pids.json").write_text('{"daemon": 10, "serve": 11}')
    signals = []

    def wait(pids, **kw):
        return []                       # оба PID вышли до дедлайна

    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    B.stop_code_index(ci, run=lambda cmd, **k: None,
                      kill=lambda pid, sig: signals.append((pid, sig)),
                      clock=_Clock([0.0, 0.0]), wait=wait,
                      log=lambda _m: None)
    assert signals == [(10, signal.SIGTERM), (11, signal.SIGTERM)]


def test_stop_check_overrunning_deadline_ends_wait():
    checked = []
    def check(pid):
        checked.append(pid)
        return True
    alive = B._wait_exit([10], check=check,
                         clock=_Clock([0.0, 0.0, 10.0]), sleep=lambda _s: None,
                         timeout=10.0)
    assert checked == [10]
    assert alive == [10]


def test_wait_ready_fails_fast_on_error_status(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/x", "status": "error",
                                    "message": "boom"}]})
    calls = []
    with pytest.raises(SetupError, match="boom"):
        B.wait_code_index_ready(index, wait_minutes=360, host="h", port=1,
                                run=_ready_run(status, calls),
                                sleep=lambda _s: None,
                                clock=lambda: 0.0, tcp_ok=lambda _u: True,
                                log=lambda _m: None)
    assert len(calls) == 1          # без ожидания таймаута


def test_wait_ready_error_uses_error_field_and_fallback(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/x", "status": "error",
                                    "error": "bad xml"}]})
    with pytest.raises(SetupError, match="bad xml"):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run(status, []),
                                sleep=lambda _s: None, clock=lambda: 0.0,
                                tcp_ok=lambda _u: True, log=lambda _m: None)
    status = json.dumps({"paths": [{"path": "/x", "status": "error"}]})
    with pytest.raises(SetupError, match="ошибка индексации"):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run(status, []),
                                sleep=lambda _s: None, clock=lambda: 0.0,
                                tcp_ok=lambda _u: True, log=lambda _m: None)


def test_start_stops_daemon_when_serve_spawn_fails(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("bin", encoding="utf-8")
    (ci / B.BENCHMARK_MARKER).write_text("benchmark\n", encoding="utf-8")
    calls = []

    def fake_popen(args, **kwargs):
        calls.append(list(args))
        if len(calls) == 2:
            raise OSError("spawn serve failed")
        return SimpleNamespace(pid=111)

    stopped = []
    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: True)
    real_stop = B.stop_code_index

    def spy_stop(d, **k):
        stopped.append(Path(d))
        return real_stop(d, kill=lambda pid, sig: None,
                         wait=lambda pids, **kw: [], **k)

    monkeypatch.setattr(B, "stop_code_index", spy_stop)
    with pytest.raises(OSError, match="spawn serve failed"):
        B.start_code_index(
            code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
            download=lambda dest, *, log=None: bin_path,
            popen=fake_popen,
            run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                                stderr=""),
            log=lambda _m: None)
    # Реальная очистка: демон остановлен, stale serve-записи нет.
    assert stopped[-1] == ci
    assert not (ci / "benchmark-pids.json").exists()


def test_start_writes_daemon_pid_before_serve_spawn(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("bin", encoding="utf-8")
    (ci / B.BENCHMARK_MARKER).write_text("benchmark\n", encoding="utf-8")
    seen, pids = [], iter([111, 222])

    def fake_popen(args, **kwargs):
        path = ci / "benchmark-pids.json"
        seen.append(json.loads(path.read_text("utf-8"))
                    if path.exists() else None)
        return SimpleNamespace(pid=next(pids))

    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=lambda dest, *, log=None: bin_path, popen=fake_popen,
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""),
        log=lambda _m: None)
    assert seen[0] is None                # до spawn демона pid-файла нет
    assert seen[1] == {"daemon": 111, "serve": None}
    assert json.loads((ci / "benchmark-pids.json").read_text("utf-8")) == {
        "daemon": 111, "serve": 222}


# --- benchmark-маркер: не стирать чужой каталог ---

def _start_with(ci, tmp_path, monkeypatch, **extra):
    catalog = tmp_path / "catalog"; catalog.mkdir(exist_ok=True)
    bin_path = ci / "bsl-indexer"
    pids = iter([111, 222])
    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    return B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        download=lambda dest, *, log=None: bin_path,
        popen=lambda *a, **k: SimpleNamespace(pid=next(pids)),
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""),
        log=lambda _m: None, **extra)


def test_start_refuses_unmarked_non_empty_dir(tmp_path, monkeypatch):
    from agentmon.env.bench_setup import SetupError
    ci = tmp_path / "shared"; ci.mkdir()
    (ci / "service.db").write_text("foreign", encoding="utf-8")
    with pytest.raises(SetupError, match="не помечен"):
        _start_with(ci, tmp_path, monkeypatch)
    assert (ci / "service.db").is_file()          # чужой каталог цел


def test_start_accepts_marked_dir(tmp_path, monkeypatch):
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / B.BENCHMARK_MARKER).write_text("benchmark\n", encoding="utf-8")
    (ci / "old.txt").write_text("old", encoding="utf-8")
    index = _start_with(ci, tmp_path, monkeypatch)
    assert index.daemon_pid == 111 and index.serve_pid == 222
    assert not (ci / "old.txt").exists()
    assert (ci / B.BENCHMARK_MARKER).is_file()


# --- порт занят / чужой слушатель не считается готовностью ---

def test_wait_ready_foreign_listener_is_not_ready(monkeypatch):
    from agentmon.env.bench_setup import SetupError
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: pid == 1)
    index = B.NativeIndex(Path("/ci"), Path("/ci/bsl-indexer"), 1, 2)
    status = json.dumps({"paths": [{"path": "/p", "status": "ready"}]})
    with pytest.raises(SetupError, match="завершился"):
        B.wait_code_index_ready(index, wait_minutes=1, host="h", port=1,
                                run=_ready_run(status, []),
                                sleep=lambda _s: None, clock=_counting_clock(),
                                tcp_ok=lambda _u: True, log=lambda _m: None)


def test_start_refuses_busy_port_before_spawn(tmp_path, monkeypatch):
    from agentmon.env.bench_setup import SetupError
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    bin_path = ci / "bsl-indexer"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("bin", encoding="utf-8")
    (ci / B.BENCHMARK_MARKER).write_text("benchmark\n", encoding="utf-8")
    probed, spawned = [], []

    def fake_popen(args, **kwargs):
        spawned.append(list(args))
        return SimpleNamespace(pid=111)

    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    with pytest.raises(SetupError, match="8005"):
        B.start_code_index(
            code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
            download=lambda dest, *, log=None: bin_path, popen=fake_popen,
            run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                                stderr=""),
            tcp_ok=lambda url: probed.append(url) or True,
            log=lambda _m: None)
    assert probed == ["http://127.0.0.1:8005"]
    assert spawned == []
    assert not (ci / "benchmark-pids.json").exists()


# --- bind host: serve принимает только socket-адрес, не hostname ---

def test_start_maps_localhost_to_loopback_for_serve(tmp_path, monkeypatch):
    ci = tmp_path / "ci"
    catalog = tmp_path / "catalog"; catalog.mkdir()
    spawned = []
    pids = iter([1, 2])

    def fake_download(dest, *, log=None):
        path = Path(dest) / "bsl-indexer"
        path.write_text("bin", encoding="utf-8")
        return path

    def fake_popen(args, **kwargs):
        spawned.append((list(args), kwargs))
        return SimpleNamespace(pid=next(pids))

    monkeypatch.setattr(B, "_spawn_kwargs", lambda: {})
    B.start_code_index(
        code_index_dir=ci, catalog_dir=catalog, alias="a", port=8005,
        host="localhost", download=fake_download, popen=fake_popen,
        run=lambda *a, **k: SimpleNamespace(returncode=0, stdout="",
                                            stderr=""),
        tcp_ok=lambda _u: False, log=lambda _m: None)
    serve_args, serve_kwargs = spawned[1]
    assert serve_args[serve_args.index("--host") + 1] == "127.0.0.1"
    assert serve_kwargs["env"]["MCP_HTTP_HOST"] == "127.0.0.1"


def test_wait_dead_process_includes_log_tail(tmp_path, monkeypatch):
    from agentmon.env.bench_setup import SetupError
    ci = tmp_path / "ci"; ci.mkdir()
    (ci / "serve.log").write_text(
        "Error: Некорректный host:port 'localhost:8005'\n", encoding="utf-8")
    (ci / "daemon.log").write_text("daemon started\n", encoding="utf-8")
    index = B.NativeIndex(ci, ci / "bsl-indexer", 1, 2)
    monkeypatch.setattr(B, "_daemon_status", lambda index, run: None)
    monkeypatch.setattr(B, "_is_our_process", lambda pid, run: False)
    with pytest.raises(SetupError, match="Некорректный host:port"):
        B.wait_code_index_ready(index, wait_minutes=1, host="localhost",
                                port=8005, run=lambda *a, **k: None,
                                sleep=lambda _s: None, clock=lambda: 0.0,
                                tcp_ok=lambda _u: False, log=lambda _m: None)

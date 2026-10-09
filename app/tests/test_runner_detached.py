import sys, time
from pathlib import Path
from agentmon import runner_detached as rd


def _wait_gone(pid, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if not rd.is_running(pid):
            return True
        time.sleep(0.05)
    return False


def test_launch_runs_and_records_exit(tmp_path):
    pid = rd.launch([sys.executable, "-c", "import sys; sys.exit(0)"],
                    cwd=str(tmp_path), log_file=str(tmp_path / "l"),
                    exit_file=str(tmp_path / "e"))
    assert pid > 0
    assert _wait_gone(pid)
    assert (tmp_path / "e").read_text().strip() == "0"


def test_is_running_false_for_bogus():
    assert rd.is_running(0) is False
    assert rd.is_running(2_000_000_000) is False


def test_is_running_survives_proc_read_race(monkeypatch):
    """TOCTOU: процесс исчезает между открытием и чтением /proc/<pid>/stat —
    is_running не должен бросать, а должен отработать на os.kill-проверке."""
    if rd.IS_WIN:
        return
    class _P:
        def read_text(self, *a, **k):
            raise FileNotFoundError("gone")
    monkeypatch.setattr(rd, "Path", lambda *_a, **_k: _P())
    # os.kill(bogus) → ProcessLookupError → False, без исключения наружу
    assert rd.is_running(2_000_000_000) is False


def test_reap_is_safe_without_children():
    # Без детей waitpid бросает ChildProcessError — reap его гасит.
    rd.reap()           # не должно бросать


def test_launch_leaves_no_zombie(tmp_path):
    """После завершения ребёнка reap() (через is_running) снимает зомби."""
    if rd.IS_WIN:
        return
    pid = rd.launch([sys.executable, "-c", "import sys; sys.exit(0)"],
                    cwd=str(tmp_path), log_file=str(tmp_path / "l"),
                    exit_file=str(tmp_path / "e"))
    assert _wait_gone(pid)              # is_running → False, попутно reap()
    # Зомби не осталось: его состояние в /proc уже не 'Z' (он снят).
    state = Path(f"/proc/{pid}/stat")
    if state.exists():
        txt = state.read_text()
        assert txt[txt.rfind(")") + 2] != "Z"


def test_terminate_kills(tmp_path):
    pid = rd.launch([sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=str(tmp_path), log_file=str(tmp_path / "l"),
                    exit_file=str(tmp_path / "e"))
    assert rd.is_running(pid)
    rd.terminate(pid)
    assert _wait_gone(pid)


def test_terminate_kills_process_group(tmp_path):
    import time
    child_pidfile = tmp_path / "child.pid"
    # run_wrapper (the launched pid) runs this inner command as its child;
    # the inner process records its own pid then sleeps.
    inner = (f"import os,time; open(r'{child_pidfile}','w').write(str(os.getpid())); "
             f"time.sleep(30)")
    pid = rd.launch([sys.executable, "-c", inner], cwd=str(tmp_path),
                    log_file=str(tmp_path / "l"), exit_file=str(tmp_path / "e"))
    # wait for the inner process to write its pid
    end = time.time() + 5
    while time.time() < end and not child_pidfile.exists():
        time.sleep(0.05)
    child_pid = int(child_pidfile.read_text())
    assert rd.is_running(child_pid)
    rd.terminate(pid)
    assert _wait_gone(pid) and _wait_gone(child_pid)   # both wrapper and grandchild are dead


def test_terminate_escalates_to_sigkill(tmp_path):
    """Процесс, игнорирующий SIGTERM, всё равно должен быть убит (SIGKILL)."""
    if rd.IS_WIN:
        return
    # Инертный к SIGTERM процесс: ставит обработчик и уходит в долгий сон.
    inner = ("import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
             "time.sleep(60)")
    pid = rd.launch([sys.executable, "-c", inner], cwd=str(tmp_path),
                    log_file=str(tmp_path / "l"), exit_file=str(tmp_path / "e"))
    assert rd.is_running(pid)
    rd.terminate(pid)                  # SIGTERM игнорируется → эскалация до SIGKILL
    assert _wait_gone(pid)

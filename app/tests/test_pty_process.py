import os
import sys
import time

import pytest

from agentmon.pty_process import spawn

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX-ветка PTY; ветка Windows проверяется вручную на Windows",
)


def read_until(proc, needle, timeout=5.0):
    buf = ""
    deadline = time.time() + timeout
    while time.time() < deadline:
        buf += proc.read_available()
        if needle in buf:
            return buf
        time.sleep(0.05)
    return buf


def test_echoes_written_text():
    p = spawn("cat", cwd=os.getcwd())
    try:
        p.write("hello\n")
        assert "hello" in read_until(p, "hello")
    finally:
        p.kill()


def test_alive_then_dead_after_kill():
    p = spawn("cat", cwd=os.getcwd())
    try:
        assert p.alive is True
        p.kill()
        deadline = time.time() + 5.0
        while p.alive and time.time() < deadline:
            time.sleep(0.05)
        assert p.alive is False
    finally:
        p.kill()


def test_runs_in_requested_cwd(tmp_path):
    p = spawn("sh", cwd=str(tmp_path))
    try:
        p.write("pwd\n")
        out = read_until(p, tmp_path.name)
        assert tmp_path.name in out
    finally:
        p.kill()


def test_read_available_is_empty_when_nothing_written():
    p = spawn("cat", cwd=os.getcwd())
    try:
        assert p.read_available() == ""
    finally:
        p.kill()


def test_process_that_exits_becomes_not_alive():
    p = spawn("sh -c 'exit 0'", cwd=os.getcwd())
    deadline = time.time() + 5.0
    while p.alive and time.time() < deadline:
        time.sleep(0.05)
    assert p.alive is False


def test_interrupt_does_not_break_the_session():
    # Проверяем только живучесть: терминал с ECHOCTL печатает ESC как "^[",
    # поэтому дословного \x1b в эхе может не быть.
    p = spawn("cat", cwd=os.getcwd())
    try:
        p.interrupt()
        time.sleep(0.2)
        assert p.alive is True
    finally:
        p.kill()


def test_missing_cwd_raises():
    with pytest.raises(FileNotFoundError):
        spawn("cat", cwd="/no/such/directory/at/all")


def test_kill_reaps_child_leaves_no_zombie():
    # os.waitpid(pid, os.WNOHANG) на уже забранном ребёнке бросает
    # ChildProcessError («No child processes») — это прямое доказательство
    # того, что kill() сам реапнул процесс, а не оставил зомби висеть до
    # случайного обращения к alive.
    p = spawn("cat", cwd=os.getcwd())
    pid = p._proc.pid
    p.kill()
    with pytest.raises(ChildProcessError):
        os.waitpid(pid, os.WNOHANG)


def test_kill_closes_master_fd_idempotently():
    p = spawn("cat", cwd=os.getcwd())
    p.kill()
    p.kill()  # повторный kill() не должен бросать
    # Дескриптор закрыт — запись в него обязана упасть OSError, а не молча
    # потеряться и не уронить процесс необработанным исключением другого рода.
    with pytest.raises(OSError):
        p.write("data\n")


def test_natural_exit_closes_master_fd():
    p = spawn("sh -c 'exit 0'", cwd=os.getcwd())
    try:
        deadline = time.time() + 5.0
        while p.alive and time.time() < deadline:
            time.sleep(0.05)
        assert p.alive is False
        with pytest.raises(OSError):
            os.fstat(p._master)
    finally:
        p.kill()


def test_terminate_reaps_child():
    p = spawn("cat", cwd=os.getcwd())
    try:
        pid = p._proc.pid
        p.terminate()
        deadline = time.time() + 5.0
        while p.alive and time.time() < deadline:
            time.sleep(0.05)
        assert p.alive is False
        with pytest.raises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)
    finally:
        p.kill()


def _open_fd_count():
    return len(os.listdir("/proc/self/fd"))


@pytest.mark.skipif(not os.path.isdir("/proc/self/fd"),
                    reason="нужен /proc для подсчёта дескрипторов")
def test_failed_spawn_does_not_leak_master_fd():
    # pty.openpty() выполняется до Popen: если Popen упал, объекта,
    # который закрыл бы master, не появится вовсе. Диспетчер повторяет
    # неудачный старт, поэтому утечка копится до исчерпания таблицы.
    before = _open_fd_count()
    for _ in range(5):
        with pytest.raises(FileNotFoundError):
            spawn("nosuchbinary-agentmon-test", cwd=os.getcwd())
    assert _open_fd_count() == before

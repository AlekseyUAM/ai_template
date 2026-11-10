"""PID после рестарта монитора может принадлежать чужому процессу."""
import os
import signal
import subprocess
import sys
import time

import pytest

from agentmon import runner_detached


def _spawn_sleep():
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                            start_new_session=True)


def _wait_start(pid):
    for _ in range(100):
        start = runner_detached.process_start_time(pid)
        if start is not None:
            return start
        time.sleep(0.01)
    return None


@pytest.mark.skipif(os.name == "nt", reason="нет /proc")
def test_start_time_mismatch_is_not_ours():
    proc = _spawn_sleep()
    try:
        start = _wait_start(proc.pid)
        assert start is not None
        assert runner_detached.is_running(proc.pid, start) is True
        assert runner_detached.is_running(proc.pid, start + 1) is False
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(os.name == "nt", reason="нет /proc")
def test_terminate_does_not_kill_foreign_start_time():
    proc = _spawn_sleep()
    try:
        start = _wait_start(proc.pid)
        runner_detached.terminate(proc.pid, start + 1)   # чужой start-time
        time.sleep(0.2)
        assert proc.poll() is None, "чужой процесс не должен быть убит"
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.skipif(os.name == "nt", reason="нет /proc")
def test_terminate_kills_own_process_group():
    proc = _spawn_sleep()
    start = _wait_start(proc.pid)
    runner_detached.terminate(proc.pid, start)
    try:
        proc.wait(timeout=3)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()

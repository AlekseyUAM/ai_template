import sys
from pathlib import Path
from agentmon import run_wrapper


def test_run_writes_exit_code(tmp_path):
    ef = tmp_path / "e"
    rc = run_wrapper.run(str(ef), [sys.executable, "-c", "import sys; sys.exit(3)"])
    assert rc == 3 and ef.read_text().strip() == "3"


def test_main_parses_separator(tmp_path):
    ef = tmp_path / "e"
    try:
        run_wrapper.main([str(ef), "--", sys.executable, "-c", "import sys; sys.exit(0)"])
    except SystemExit as e:
        assert e.code == 0
    assert ef.read_text().strip() == "0"


import os
import signal
import subprocess
import time

import pytest


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="PDEATHSIG только Linux")
def test_wrapper_death_kills_child(tmp_path):
    """SIGKILL wrapper'а не оставляет claude сиротой."""
    pid_file = tmp_path / "child.pid"
    exit_file = tmp_path / "exit"
    inner = (
        "import pathlib, time; "
        f"pathlib.Path({str(pid_file)!r}).write_text(str(__import__('os').getpid())); "
        "time.sleep(60)"
    )
    wrapper = subprocess.Popen([
        sys.executable, "-c",
        "import sys; sys.path.insert(0, 'src'); "
        "from agentmon.run_wrapper import run; "
        f"run({str(exit_file)!r}, [sys.executable, '-c', {inner!r}])",
    ], cwd=str(Path(__file__).resolve().parents[1]))
    try:
        for _ in range(100):
            if pid_file.exists():
                break
            time.sleep(0.02)
        child_pid = int(pid_file.read_text())
        wrapper.kill()
        wrapper.wait(timeout=3)
        deadline = time.time() + 3
        while time.time() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            os.kill(child_pid, signal.SIGKILL)
            pytest.fail("дочерний процесс пережил SIGKILL wrapper'а")
    finally:
        if wrapper.poll() is None:
            wrapper.kill()

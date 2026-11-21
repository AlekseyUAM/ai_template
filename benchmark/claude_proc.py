"""Запуск `claude -p` с промптом через stdin.

Windows-обёртка `.bat` через cmd.exe искажает argv, если промпт многострочный:
CLI теряет флаги. Поэтому промпт пишем в stdin, а в argv оставляем только флаги.
"""
from __future__ import annotations

import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    duration_sec: float


def _group_exists(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _wait_exit(proc: subprocess.Popen, timeout: float) -> bool:
    try:
        proc.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        return False


def _kill_group(proc: subprocess.Popen, pgid: int) -> None:
    """Мягко остановить лидера, затем гарантированно зачистить process group.

    Windows не умеет process group: дерево снимается `taskkill /F /T`.
    """
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                check=False, timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
            _wait_exit(proc, 5)
        return

    def send(sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            pass

    if proc.poll() is None:
        send(signal.SIGINT)
        _wait_exit(proc, 10)
    if proc.poll() is None:
        send(signal.SIGTERM)
        _wait_exit(proc, 5)
    if _group_exists(pgid):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
        _wait_exit(proc, 5)


def run_claude_process(*, cmd: str, prompt: str, cwd: Path,
                       timeout_sec: float, stdout_path: Path,
                       stderr_path: Path,
                       extra_args: tuple[str, ...] = (),
                       env: dict[str, str] | None = None) -> ProcessResult:
    """Запустить `claude -p` с промптом в stdin; таймаут убивает группу."""
    argv = [cmd, "-p", "--output-format", "stream-json",
            "--verbose", *extra_args]
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        proc = subprocess.Popen(
            argv, cwd=cwd, stdin=subprocess.PIPE, stdout=out, stderr=err,
            env=env, start_new_session=True)
        try:
            assert proc.stdin is not None
            proc.stdin.write(prompt.encode("utf-8"))
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            # Ребёнок завершился раньше, чем прочитал stdin.
            pass
        try:
            exit_code = proc.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_group(proc, proc.pid)
            try:
                exit_code = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                exit_code = proc.poll()
        except BaseException:
            _kill_group(proc, proc.pid)
            raise
    return ProcessResult(exit_code, timed_out,
                         time.monotonic() - started)

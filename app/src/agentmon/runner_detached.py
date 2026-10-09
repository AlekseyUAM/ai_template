"""Запуск агентов отдельными detached-процессами; слежение по PID. Кросс-платформа."""
import os
import subprocess
import sys
import threading
from pathlib import Path

IS_WIN = os.name == "nt"
_DETACHED_PROCESS = 0x00000008

# PID детей, которых породил именно launch(). Снимаем (reap) ТОЛЬКО их —
# waitpid(-1) воровал бы коды завершения у subprocess.run() из других потоков
# (1cv8/git/pip/docker) и ломал те вызовы ChildProcessError-ом.
_OUR_CHILDREN: set[int] = set()
_CHILDREN_LOCK = threading.Lock()


def reap() -> None:
    """Невозбуждающе дожать наших завершившихся детей (POSIX), чтобы не копить
    зомби. launch() порождает run_wrapper и забывает про Popen, поэтому
    завершившиеся дети иначе становятся <defunct> на всё время жизни монитора.
    Снимаем строго свои PID (см. _OUR_CHILDREN), не трогая чужих детей процесса.
    На Windows no-op."""
    if IS_WIN:
        return
    with _CHILDREN_LOCK:
        pids = list(_OUR_CHILDREN)
    for pid in pids:
        try:
            done, _ = os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            done = pid          # уже снят (напр. subprocess._cleanup) — забываем
        except OSError:
            continue
        if done:
            with _CHILDREN_LOCK:
                _OUR_CHILDREN.discard(pid)


def launch(cmd: list, cwd: str, log_file: str, exit_file: str) -> int:
    """Запустить cmd detached через run_wrapper; вернуть PID. stdin закрыт,
    stdout/stderr → log_file, код выхода → exit_file."""
    wrapped = [sys.executable, "-m", "agentmon.run_wrapper", exit_file, "--", *cmd]
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    log = open(log_file, "ab")
    kwargs = {"cwd": cwd, "stdin": subprocess.DEVNULL, "stdout": log, "stderr": log}
    if IS_WIN:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | _DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    try:
        pid = subprocess.Popen(wrapped, **kwargs).pid
        if not IS_WIN:
            with _CHILDREN_LOCK:
                _OUR_CHILDREN.add(pid)
        return pid
    finally:
        log.close()


def is_running(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    if IS_WIN:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        ok = k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        if not ok:
            return True                         # call failed — assume alive conservatively
        return code.value == 259                # STILL_ACTIVE
    # Снимаем завершившихся детей на каждом тике — is_running зовётся из
    # reconcile/is_alive/sessions, это естественная периодическая точка.
    reap()
    # On Linux, check /proc/<pid>/stat to detect if process is truly running (not zombie).
    # Процесс может завершиться между exists() и read_text() — читаем через
    # try/except, при FileNotFoundError/OSError падаем на проверку os.kill.
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        stat_text = None
    if stat_text is not None:
        # Parse state from /proc/<pid>/stat: field is 3rd item (index 2)
        # Fields: pid (cmd) state ppid pgrp session tty_nr ...
        # Find the end of the command name (it's in parentheses)
        close_paren = stat_text.rfind(")")
        if close_paren != -1 and close_paren + 2 < len(stat_text):
            state_char = stat_text[close_paren + 2]  # State is right after the closing paren
            # 'Z' is zombie, 'R' is running, 'S' is sleeping, etc. Any but 'Z' is alive
            if state_char == 'Z':
                return False
            return True
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ChildProcessError):
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def terminate(pid: int) -> None:
    if not is_running(pid):
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        return
    import signal
    import time
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (ProcessLookupError, OSError):
        pass
    # Ждём завершения ограниченное время, затем эскалируем до SIGKILL.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _alive_posix(pid):
            break
        time.sleep(0.05)
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            pass
    # Снимаем зомби нашего прямого ребёнка (если это он).
    try:
        os.waitpid(pid, os.WNOHANG)
    except (ChildProcessError, OSError):
        pass
    with _CHILDREN_LOCK:
        _OUR_CHILDREN.discard(pid)
    reap()


def _alive_posix(pid: int) -> bool:
    """Жив ли pid (не зомби) на POSIX — без reap(), для цикла ожидания."""
    try:
        stat_text = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        stat_text = None
    if stat_text is not None:
        close_paren = stat_text.rfind(")")
        if close_paren != -1 and close_paren + 2 < len(stat_text):
            return stat_text[close_paren + 2] != "Z"
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, ChildProcessError, OSError):
        return False
    except PermissionError:
        return True
    return True

# Detached-мониторинг — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Checkbox steps.

**Goal:** Перевести запуск/слежение агентов на detached-процессы + PID + JSONL + код выхода (headless `claude -p`), устойчиво к перезапуску монитора.

**Tech Stack:** Python 3.10+ (stdlib: subprocess, os, ctypes на Windows, sqlite3), pytest.

## Global Constraints
- Кросс-платформа Linux+Windows; stdin агенту не нужен (чат убран).
- Запуск задачи = `claude -p "<prompt>"` detached; завершение = PID мёртв + код выхода.
- Реестр прогонов в SQLite (`runs`) переживает перезапуск монитора.
- Формат `/api/sessions` и `/ws/sessions` сохранить (фронт «Агенты» не трогаем).
- ssh-бэкенд в detached — вне скоупа (local-only; ssh позже).
- Observer/jsonl — остаются (токены/фаза).

---

# ФУНДАМЕНТ (безопасно, самодостаточно)

## Task 1: run_wrapper.py (захват кода выхода)

**Files:** Create `app/src/agentmon/run_wrapper.py`; Test `app/tests/test_run_wrapper.py`.
**Interfaces:** `run(exit_file, cmd) -> int` (запускает cmd, пишет код в exit_file); `main(argv)` формат `<exit_file> -- <cmd...>`.

- [ ] **Step 1: failing test**
```python
# app/tests/test_run_wrapper.py
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
```
- [ ] **Step 2: run (fails).** `cd app && PYTHONPATH=src python -m pytest tests/test_run_wrapper.py -q`
- [ ] **Step 3: implement**
```python
# app/src/agentmon/run_wrapper.py
"""Запуск дочернего процесса с записью его кода выхода в файл (для detached-прогонов)."""
import subprocess
import sys
from pathlib import Path


def run(exit_file: str, cmd: list) -> int:
    code = subprocess.call(cmd)
    Path(exit_file).write_text(str(code), encoding="utf-8")
    return code


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 3 or argv[1] != "--":
        raise SystemExit("использование: run_wrapper <exit_file> -- <cmd...>")
    raise SystemExit(run(argv[0], argv[2:]))


if __name__ == "__main__":
    main()
```
- [ ] **Step 4: run (pass).**
- [ ] **Step 5: commit** `git commit -m "feat(run): run_wrapper — захват кода выхода detached-процесса"`

---

## Task 2: runner_detached.py (запуск/PID/стоп)

**Files:** Create `app/src/agentmon/runner_detached.py`; Test `app/tests/test_runner_detached.py`.
**Interfaces:** `launch(cmd, cwd, log_file, exit_file) -> int` (PID); `is_running(pid) -> bool`; `terminate(pid) -> None`. Кросс-платформа.

- [ ] **Step 1: failing test**
```python
# app/tests/test_runner_detached.py
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


def test_terminate_kills(tmp_path):
    pid = rd.launch([sys.executable, "-c", "import time; time.sleep(30)"],
                    cwd=str(tmp_path), log_file=str(tmp_path / "l"),
                    exit_file=str(tmp_path / "e"))
    assert rd.is_running(pid)
    rd.terminate(pid)
    assert _wait_gone(pid)
```
- [ ] **Step 2: run (fails).**
- [ ] **Step 3: implement**
```python
# app/src/agentmon/runner_detached.py
"""Запуск агентов отдельными detached-процессами; слежение по PID. Кросс-платформа."""
import os
import subprocess
import sys
from pathlib import Path

IS_WIN = os.name == "nt"
_DETACHED_PROCESS = 0x00000008


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
        return subprocess.Popen(wrapped, **kwargs).pid
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
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                # STILL_ACTIVE
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def terminate(pid: int) -> None:
    if not is_running(pid):
        return
    if IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        try:
            os.kill(pid, 15)
        except ProcessLookupError:
            pass
```
- [ ] **Step 4: run (pass).** (Детач-процесс наследует PYTHONPATH=src, поэтому `agentmon.run_wrapper` импортируется.)
- [ ] **Step 5: commit** `git commit -m "feat(run): runner_detached — запуск/PID/стоп кросс-платформенно"`

---

## Task 3: run_store.py (реестр прогонов)

**Files:** Create `app/src/agentmon/run_store.py`; Test `app/tests/test_run_store.py`.
**Interfaces:** `RunStore(conn, clock=time.time)` создаёт таблицу `runs`; `add(project_id, pid, *, task_id, log_file, exit_file) -> run_id`; `running(project_id=None) -> list[dict]`; `finish(run_id, status, exit_code=None)`; `get(run_id) -> dict|None`.

- [ ] **Step 1: failing test**
```python
# app/tests/test_run_store.py
from agentmon.registry import open_db
from agentmon.run_store import RunStore


def test_add_running_finish(tmp_path):
    db = open_db(tmp_path / "db.sqlite")
    store = RunStore(db, clock=lambda: 100.0)
    rid = store.add(1, 4242, task_id=7, log_file="l", exit_file="e")
    run = store.get(rid)
    assert run["pid"] == 4242 and run["status"] == "running" and run["project_id"] == 1
    assert [r["id"] for r in store.running(1)] == [rid]
    assert store.running(2) == []
    store.finish(rid, "done", exit_code=0)
    assert store.get(rid)["status"] == "done" and store.get(rid)["exit_code"] == 0
    assert store.running() == []
```
- [ ] **Step 2: run (fails).**
- [ ] **Step 3: implement**
```python
# app/src/agentmon/run_store.py
"""Реестр detached-прогонов (таблица runs). Переживает перезапуск монитора."""
import time

_SCHEMA = """CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    task_id INTEGER,
    pid INTEGER NOT NULL,
    log_file TEXT,
    exit_file TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    started_at REAL NOT NULL,
    finished_at REAL,
    exit_code INTEGER
)"""


class RunStore:
    def __init__(self, conn, clock=time.time):
        self.conn = conn
        self.clock = clock
        conn.execute(_SCHEMA)
        conn.commit()

    def add(self, project_id, pid, *, task_id=None, log_file=None, exit_file=None):
        cur = self.conn.execute(
            "INSERT INTO runs (project_id, task_id, pid, log_file, exit_file, "
            "status, started_at) VALUES (?,?,?,?,?,'running',?)",
            (project_id, task_id, pid, log_file, exit_file, self.clock()))
        self.conn.commit()
        return cur.lastrowid

    def running(self, project_id=None):
        if project_id is None:
            rows = self.conn.execute("SELECT * FROM runs WHERE status='running'").fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM runs WHERE status='running' AND project_id=?",
                (project_id,)).fetchall()
        return [dict(r) for r in rows]

    def finish(self, run_id, status, exit_code=None):
        self.conn.execute(
            "UPDATE runs SET status=?, exit_code=?, finished_at=? WHERE id=?",
            (status, exit_code, self.clock(), run_id))
        self.conn.commit()

    def get(self, run_id):
        r = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return dict(r) if r else None
```
- [ ] **Step 4: run (pass).** (open_db ставит row_factory=Row → dict(r) работает.)
- [ ] **Step 5: commit** `git commit -m "feat(run): run_store — реестр прогонов (SQLite runs)"`

---

# ИНТЕГРАЦИЯ (рискованно; детализируется перед исполнением, отдельный чекпойнт)

## Task 4: Detached Monitor
Переписать `monitor.py` на: `start(project, prompt)` → `runner_detached.launch(claude_cmd -p prompt)` + `run_store.add`; `is_alive(project)` → есть ли running-прогон с живым PID; `stop` → `terminate`; `reconcile()` → мёртвые PID → finish(done/failed по exit_file); `sessions()` → running-прогоны + observer-JSONL (формат API сохранить). Инъекция `runner`/`store` + `FakeRunner` для тестов. Ретайр PTY-веток монитора (`send/transcript/capture` — чат уже удалён).

## Task 5: Detached Dispatcher
`tick()` → для queued задачи `monitor.start(project, orchestration_text)`, `mark_running`; по завершении прогона (reconcile) → `mark_done`/`mark_failed` по коду выхода. Убрать idle-эвристику и requeue-по-PTY.

## Task 6: Проводка и UI
`__main__.build` — собрать RunStore на том же DB, Monitor(registry, store, runner), Dispatcher. `api.py` start/stop — передать prompt (для ручного старта — дефолтный/пустой или последняя задача). Форма проекта — временно только `local` (ssh скрыть). Миграция тестов `test_monitor.py`/`test_dispatcher.py`/`test_api.py` под FakeRunner/runs-модель; observer-тесты оставить. Полный набор зелёный.

---

## Self-Review (фундамент)
- run_wrapper/runner_detached/run_store — самодостаточны, кросс-платформенны, TDD на реальных коротких процессах.
- Интеграция (T4-T6) не ломает формат `/api/sessions`; детализируется с кодом перед исполнением.
- Риск сосредоточен в T4-T6 (миграция ~300 тестов) — отдельный чекпойнт.

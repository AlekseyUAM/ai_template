#!/usr/bin/env python
"""Update the task stage status in task.json. Self-contained script (without agentmon).

Also enforces gates: a stage cannot be moved to `running` while the
previous enabled stage with `gate: true` is not confirmed (`approved: true`).
Confirmation is set by a command with status `approve`.

When `develop`/`tests` return to `pending`, it archives the verdicts of the previous
iteration (`TESTING.md` -> `TESTING.<n>.md`, `REVIEW.md` -> `REVIEW.<n>.md`).

Statuses: `pending -> running -> done | failed`. `done` is allowed only from
`running` - a stage without a completed infobase load and an open run is not
closed. Re-running a stage (including already `running` or `done`) is the
`restart` command: closes all open records, increments `iteration` and
opens a new run. Repeated `running` while already `running` is an error.

Each stage run is recorded in `stage["runs"]`
(`{"iteration", "started_at", "finished_at"}`) - history for metrics; the record
number matches the stage `iteration` at the time of the run.
"""
import argparse
import contextlib
from datetime import datetime, timezone
import json
import os
import re
import time
from pathlib import Path

VALID = ("pending", "running", "done", "failed", "skipped", "approve",
         "restart")

LOCK_TIMEOUT = 5.0
STALE_LOCK_SECONDS = 30.0


@contextlib.contextmanager
def _locked(path: Path):
    """Interprocess lock next to task.json.

    The file is written by both the orchestrator and the application (approve from UI/Telegram).
    Without a lock, two read-modify-write operations lose each other's edits.
    """
    lock = path.with_name(path.name + ".lock")
    deadline = time.monotonic() + LOCK_TIMEOUT
    fd = None
    while fd is None:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > STALE_LOCK_SECONDS:
                    lock.unlink()
                    continue
            except OSError:
                continue
            if time.monotonic() >= deadline:
                raise SystemExit(f"task.json занят другим процессом: {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            lock.unlink()
        except OSError:
            pass


def _atomic_write_json(path: Path, data: dict) -> None:
    """temp in the same directory + os.replace: a reader sees the old or the new file."""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        # Windows: os.replace fails while a reader has the target open.
        # Retry briefly; the reader's window is short and it re-reads anyway.
        for attempt in range(100):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if attempt == 99:
                    raise
                time.sleep(0.01)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

TRUTHY = {"1", "true", "yes", "да", "истина", "on"}


def _now_iso() -> str:
    """Current time in ISO 8601 with the OS local offset."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _normalize_times(data: dict) -> None:
    """Numeric dates in task.json -> ISO strings (old files, no migration)."""
    def _convert(container: dict) -> None:
        for key in ("created_at", "started_at", "finished_at"):
            value = container.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                container[key] = (
                    # tz=utc avoids the Windows CRT localtime limit for
                    # pre-1970/small epoch values; astimezone() still gives
                    # the OS local offset.
                    datetime.fromtimestamp(value, tz=timezone.utc)
                    .astimezone()
                    .isoformat(timespec="seconds"))

    _convert(data)
    for stage in data.get("stages", []):
        if isinstance(stage, dict):
            _convert(stage)
            # runs[] - run history for metrics: the same numeric timestamps
            for run in stage.get("runs") or []:
                if isinstance(run, dict):
                    _convert(run)
    db_update = data.get("db_update")
    if isinstance(db_update, dict):
        _convert(db_update)


def _truthy(value) -> bool:
    """Tolerant truth parsing: bool / number / string (1/true/да/yes...)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY
    return False


def _gate_block(data: dict, target_stage: str):
    """Error message if target_stage cannot start due to an unconfirmed
    gate on one of the previous enabled stages. None - if it can.

    The only criterion is the `gate` field: a stage with `gate: true` must be confirmed
    (`approved: true`) before the next stage starts."""
    for s in data.get("stages", []):
        if s["name"] == target_stage:
            return None
        if not _truthy(s.get("enabled")):
            continue
        # The gate guards the transition AFTER a completed stage. While the stage is pending or
        # running, there is nothing to approve - otherwise no following stage would start.
        if (s.get("status") == "done" and _truthy(s.get("gate"))
                and not _truthy(s.get("approved"))):
            return (
                f"гейт не пройден: этап '{s['name']}' требует подтверждения перед "
                f"запуском '{target_stage}'. Подтвердите командой:\n"
                f"  python .claude/tools/task_status.py <task_dir> {s['name']} approve")
    return None


def _db_update_block(data: dict, stage: str, status: str):
    """Error message if develop cannot be closed without a successful infobase load.

    With `update_db: true` the configuration load is part of completing the `develop`
    stage. If it is not confirmed (`db_update.finished_at` is empty), the stage
    cannot be moved to `done`: otherwise a load failure is masked by the status
    "done" (in task.json and in the monitor). None - if it can be closed."""
    if stage != "develop" or status != "done":
        return None
    if not _truthy(data.get("update_db")):
        return None
    db_update = data.get("db_update") or {}
    if db_update.get("finished_at") is None:
        return (
            "этап 'develop' нельзя перевести в 'done': включён update_db, но "
            "загрузка в ИБ не подтверждена. Выполните загрузку (правило "
            "optimized-config-loading) и отметьте её завершение:\n"
            "  python .claude/tools/task_status.py <task_dir> db-update done\n"
            "При ошибке загрузки этап не закрывайте — верните develop в pending.")
    return None


# Stages whose return to pending archives the iteration verdicts (TESTING.md,
# REVIEW.md). DEVELOP.md/TESTS.md are archived by the stage executor itself.
AUTO_ARCHIVE_STAGES = ("develop", "tests")


def _archive_verdicts(task_dir: Path, data: dict) -> None:
    """Archive the iteration verdicts before returning the stage to pending.

    TESTING.md -> TESTING.<iteration testing>.md if testing is done;
    REVIEW.md -> REVIEW.<iteration review>.md if review is done. No stage,
    stage not done or no file - no-op. All conflicts are checked first
    (the target file already exists) and only then the rename is performed, so
    an error does not leave half an archive (called before the status change)."""
    plan = []
    for verdict_stage, artifact in (("testing", "TESTING.md"),
                                    ("review", "REVIEW.md")):
        stage = next((s for s in data.get("stages", [])
                      if s.get("name") == verdict_stage), None)
        if stage is None or stage.get("status") != "done":
            continue
        src = task_dir / artifact
        if not src.exists():
            continue
        dst = task_dir / f"{src.stem}.{stage.get('iteration', 1)}.md"
        if dst.exists():
            raise SystemExit(
                f"ОШИБКА (архив): целевой файл уже существует: {dst}. "
                f"Не перезаписываю — вердикт {artifact} разберите вручную "
                f"(уберите или переименуйте {dst.name}), затем повторите "
                f"команду. Статус этапа и файлы не изменены.")
        plan.append((src, dst))
    for src, dst in plan:
        os.replace(src, dst)


def _overall_status(stages) -> str:
    """Overall task status by stage statuses. Mirror of task_model.overall_status
    (priority: failed -> awaiting_user -> done -> running -> planned), but with
    tolerant boolean field parsing (`enabled`/`gate`/`approved`)."""
    enabled = [s for s in stages if _truthy(s.get("enabled"))]
    if not enabled:
        return "done"
    if any(s.get("status") == "failed" for s in enabled):
        return "failed"
    for i, s in enumerate(enabled):
        if _truthy(s.get("gate")) and s.get("status") == "done" \
                and not _truthy(s.get("approved")):
            if any(later.get("status") == "pending" for later in enabled[i + 1:]):
                return "awaiting_user"
    if all(s.get("status") == "done" for s in enabled):
        return "done"
    if any(s.get("status") == "running" for s in enabled):
        return "running"
    return "planned"


def set_db_update(task_dir: str, phase: str) -> None:
    """Writes infobase update timings to task.json: phase ∈ {start, done}."""
    if phase not in ("start", "done"):
        raise SystemExit(f"db-update: ожидается start|done, получено {phase!r}")
    path = Path(task_dir) / "task.json"
    with _locked(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        now = _now_iso()
        du = data.get("db_update") or {}
        if phase == "start":
            du = {"started_at": now, "finished_at": None}
        else:
            du.setdefault("started_at", now)
            du["finished_at"] = now
        data["db_update"] = du
        _normalize_times(data)
        _atomic_write_json(path, data)


def _close_open_runs(stage: dict, now: str) -> None:
    for run in stage.get("runs") or []:
        if isinstance(run, dict) and run.get("finished_at") is None:
            run["finished_at"] = now


_REVIEW_VERDICT_RE = re.compile(
    r"\|\s*Вердикт\s*\|\s*([^|\n]+?)\s*\|", re.IGNORECASE)


def _review_verdict(task_dir) -> str | None:
    """Verdict from `REVIEW.md` (cell row `| Вердикт | ... |`), if present."""
    path = Path(task_dir) / "REVIEW.md"
    if not path.is_file():
        return None
    try:
        match = _REVIEW_VERDICT_RE.search(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1).strip() if match else None


def _restart_block(stage: str, task_dir) -> str | None:
    """Forbid review restart if the current verdict is "на доработку".

    Such a return must go through `pending`: it archives REVIEW.md and
    increments the iteration; `restart` would leave the old verdict current.
    """
    if stage != "review":
        return None
    verdict = (_review_verdict(task_dir) or "").upper()
    if "НА ДОРАБОТКУ" in verdict or "НЕ ПРОЙДЕНО" in verdict:
        return (
            f"текущий REVIEW.md содержит вердикт «{verdict}». "
            f"Для возврата на доработку используйте pending "
            f"(он архивирует REVIEW.md), затем running; restart запрещён.")
    return None


def _restart_stage(stage: dict, data: dict) -> None:
    """Start a new stage run, closing all open runs[]."""
    now = _now_iso()
    runs = stage.get("runs") or []
    _close_open_runs(stage, now)
    stage["iteration"] = (
        int(stage.get("iteration", 1)) + 1 if runs else 1)
    stage["status"] = "running"
    stage["started_at"] = now
    stage["finished_at"] = None
    stage.setdefault("runs", []).append(
        {"iteration": stage["iteration"], "started_at": now,
         "finished_at": None})
    if stage.get("name") == "develop" and _truthy(data.get("update_db")):
        data["db_update"] = {"started_at": None, "finished_at": None}


def _refresh_overall(data: dict) -> None:
    overall = _overall_status(data.get("stages", []))
    data["status"] = overall
    now = _now_iso()
    if overall == "running" and not data.get("started_at"):
        data["started_at"] = now
    if overall in ("done", "failed"):
        data["finished_at"] = now
    elif data.get("finished_at"):
        data["finished_at"] = None


def _apply_update(data: dict, stage: str, status: str, files, task_dir) -> None:
    for s in data.get("stages", []):
        if s["name"] == stage:
            if status == "approve":
                s["approved"] = True
            elif status == "restart":
                msg = _restart_block(stage, task_dir)
                if msg:
                    raise SystemExit("ОШИБКА (restart): " + msg)
                _restart_stage(s, data)
                data["stage"] = stage
                _refresh_overall(data)
                return
            else:
                if status == "running":
                    if s.get("status") == "running":
                        raise SystemExit(
                            f"ОШИБКА (running): этап '{stage}' уже running. "
                            f"Для нового прогона используйте restart.")
                    msg = _gate_block(data, stage)
                    if msg:
                        raise SystemExit("ОШИБКА (гейт): " + msg)
                    _close_open_runs(s, _now_iso())
                if status == "done":
                    if s.get("status") != "running":
                        raise SystemExit(
                            f"ОШИБКА (done): этап '{stage}' не в running "
                            f"(текущий статус: {s.get('status')}). "
                            f"Сначала переведите этап в running.")
                    msg = _db_update_block(data, stage, status)
                    if msg:
                        raise SystemExit("ОШИБКА (БД): " + msg)
                    if not any(run.get("finished_at") is None
                               for run in (s.get("runs") or [])):
                        raise SystemExit(
                            f"ОШИБКА (done): у этапа '{stage}' нет открытого "
                            f"прогона. Запустите этап через running или restart.")
                # Archive verdicts of the previous iteration - BEFORE changing the status: on
                # a file conflict the stage and files stay as they were.
                if status == "pending" and stage in AUTO_ARCHIVE_STAGES:
                    _archive_verdicts(Path(task_dir), data)
                s["status"] = status
                data["stage"] = stage
                changed = s.setdefault("changed_files", [])
                for f in (files or []):
                    if f not in changed:
                        changed.append(f)
                # New develop run with update_db: the previous load does not
                # close it - done will again require db-update done.
                if stage == "develop" and status in ("pending", "running") \
                        and _truthy(data.get("update_db")):
                    data["db_update"] = {"started_at": None, "finished_at": None}
                # Stage timings and iteration number
                now_stage = _now_iso()
                if status == "running":
                    # Any repeated run (after done/failed or a return to
                    # pending) is a new iteration; the first run is iteration 1.
                    has_history = (bool(s.get("runs"))
                                   or s.get("finished_at") is not None)
                    if has_history:
                        s["iteration"] = int(s.get("iteration", 1)) + 1
                    else:
                        s.setdefault("iteration", 1)
                    s["started_at"] = now_stage
                    s["finished_at"] = None
                    # Run history for metrics: iteration as is, each
                    # transition to running is a separate record.
                    s.setdefault("runs", []).append(
                        {"iteration": s.get("iteration", 1),
                         "started_at": now_stage, "finished_at": None})
                elif status in ("done", "failed"):
                    s["finished_at"] = now_stage
                    for run in reversed(s.get("runs") or []):
                        if run.get("finished_at") is None:
                            run["finished_at"] = now_stage
                            break
                elif status == "pending":
                    # The run is interrupted (return for rework, load failed):
                    # close the open record, otherwise it would hang and
                    # the duration of the next run would be attributed to it.
                    for run in reversed(s.get("runs") or []):
                        if run.get("finished_at") is None:
                            run["finished_at"] = now_stage
                            break
            # Recalculate the top-level task status by stages (as on the DB path
            # in task_api2.update_stage), otherwise it would stick at the initial value
            # (_refresh_overall).
            # Timestamps - ISO 8601 in the OS local timezone. In the DB they are
            # converted back to epoch by task_sync; the fallback for unmarked
            # stages remains numeric. started_at is set on the first
            # transition of the task to running, finished_at - on a terminal
            # status; on a return to a non-terminal status we drop
            # the stale finished_at.
            _refresh_overall(data)
            return
    raise SystemExit(f"неизвестный этап: {stage}")


def update(task_dir: str, stage: str, status: str, files=None) -> None:
    path = Path(task_dir) / "task.json"
    with _locked(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        _apply_update(data, stage, status, files, task_dir)
        _normalize_times(data)
        _atomic_write_json(path, data)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Обновить статус этапа задачи")
    ap.add_argument("task_dir")
    ap.add_argument("stage")
    ap.add_argument("status",
                    help="pending|running|done|failed|skipped|approve, "
                         "restart (новый прогон этапа), "
                         "или start|done для псевдоэтапа db-update. "
                         "done — только из running; повторный running "
                         "без restart — ошибка")
    ap.add_argument("--files", nargs="*", default=[])
    args = ap.parse_args(argv)
    if args.stage == "db-update":
        set_db_update(args.task_dir, args.status)
    else:
        if args.status not in VALID:
            raise SystemExit(f"неизвестный статус: {args.status}")
        update(args.task_dir, args.stage, args.status, args.files)


if __name__ == "__main__":
    main()

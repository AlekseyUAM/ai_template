#!/usr/bin/env python
"""Обновить статус этапа задачи в task.json. Самодостаточный скрипт (без agentmon).

Дополнительно обеспечивает гейты: нельзя перевести этап в `running`, пока
предыдущий включённый этап с `gate: true` не подтверждён (`approved: true`).
Подтверждение ставится командой со статусом `approve`.
"""
import argparse
import contextlib
import json
import os
import time
from pathlib import Path

VALID = ("pending", "running", "done", "failed", "skipped", "approve")

LOCK_TIMEOUT = 5.0
STALE_LOCK_SECONDS = 30.0


@contextlib.contextmanager
def _locked(path: Path):
    """Межпроцессный lock рядом с task.json.

    Файл пишут и оркестратор, и приложение (approve из UI/Telegram). Без lock'а
    два read-modify-write теряют правки друг друга.
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
    """temp в том же каталоге + os.replace: читатель видит старый или новый файл."""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, path)
    finally:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass

TRUTHY = {"1", "true", "yes", "да", "истина", "on"}


def _truthy(value) -> bool:
    """Толерантный разбор истинности: bool / число / строка (1/true/да/yes…)."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in TRUTHY
    return False


def _gate_block(data: dict, target_stage: str):
    """Сообщение-ошибка, если нельзя стартовать target_stage из-за неподтверждённого
    гейта на одном из предыдущих включённых этапов. None — если можно.

    Единственный критерий — поле `gate`: этап с `gate: true` обязан быть подтверждён
    (`approved: true`) до запуска следующего этапа."""
    for s in data.get("stages", []):
        if s["name"] == target_stage:
            return None
        if not _truthy(s.get("enabled")):
            continue
        # Гейт стережёт переход ПОСЛЕ выполненного этапа. Пока этап pending или
        # running, одобрять нечего — иначе не стартует ни один следующий этап.
        if (s.get("status") == "done" and _truthy(s.get("gate"))
                and not _truthy(s.get("approved"))):
            return (
                f"гейт не пройден: этап '{s['name']}' требует подтверждения перед "
                f"запуском '{target_stage}'. Подтвердите командой:\n"
                f"  python .claude/tools/task_status.py <task_dir> {s['name']} approve")
    return None


def _db_update_block(data: dict, stage: str, status: str):
    """Сообщение-ошибка, если нельзя закрыть develop без успешной загрузки в ИБ.

    При `update_db: true` загрузка конфигурации — часть завершения этапа
    `develop`. Если она не подтверждена (`db_update.finished_at` пуст), этап
    нельзя переводить в `done`: иначе падение загрузки маскируется статусом
    «готово» (в task.json и в мониторе). None — если закрывать можно."""
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


def _overall_status(stages) -> str:
    """Общий статус задачи по статусам этапов. Зеркало task_model.overall_status
    (приоритет: failed → awaiting_user → done → running → planned), но с
    толерантным разбором булевых полей (`enabled`/`gate`/`approved`)."""
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
    """Пишет тайминги обновления ИБ в task.json: phase ∈ {start, done}."""
    if phase not in ("start", "done"):
        raise SystemExit(f"db-update: ожидается start|done, получено {phase!r}")
    path = Path(task_dir) / "task.json"
    with _locked(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        now = time.time()
        du = data.get("db_update") or {}
        if phase == "start":
            du = {"started_at": now, "finished_at": None}
        else:
            du.setdefault("started_at", now)
            du["finished_at"] = now
        data["db_update"] = du
        _atomic_write_json(path, data)


def _apply_update(data: dict, stage: str, status: str, files) -> None:
    for s in data.get("stages", []):
        if s["name"] == stage:
            if status == "approve":
                s["approved"] = True
            else:
                if status == "running":
                    msg = _gate_block(data, stage)
                    if msg:
                        raise SystemExit("ОШИБКА (гейт): " + msg)
                if status == "done":
                    msg = _db_update_block(data, stage, status)
                    if msg:
                        raise SystemExit("ОШИБКА (БД): " + msg)
                s["status"] = status
                data["stage"] = stage
                changed = s.setdefault("changed_files", [])
                for f in (files or []):
                    if f not in changed:
                        changed.append(f)
                # Новый прогон develop при update_db: прежняя загрузка его не
                # закрывает — для done снова потребуется db-update done.
                if stage == "develop" and status in ("pending", "running") \
                        and _truthy(data.get("update_db")):
                    data["db_update"] = {"started_at": None, "finished_at": None}
                # Тайминги этапа и номер итерации
                now_stage = time.time()
                if status == "running":
                    if s.get("finished_at") is not None:
                        # повторный прогон этапа в цикле develop↔testing/review
                        s["iteration"] = int(s.get("iteration", 1)) + 1
                        s["finished_at"] = None
                    else:
                        s.setdefault("iteration", 1)
                    s["started_at"] = now_stage
                elif status in ("done", "failed"):
                    s["finished_at"] = now_stage
            # Пересчитать верхнеуровневый статус задачи по этапам (как на DB-пути
            # в task_api2.update_stage), иначе он застрянет на начальном значении.
            overall = _overall_status(data.get("stages", []))
            data["status"] = overall
            # Отметки времени — epoch-секунды, как в БД (queue.py): started_at при
            # первом переходе задачи в running (ставим один раз), finished_at при
            # достижении терминального статуса (done/failed). При возврате в
            # нетерминальный статус (например, цикл review→develop) снимаем
            # устаревший finished_at.
            now = time.time()
            if overall == "running" and not data.get("started_at"):
                data["started_at"] = now
            if overall in ("done", "failed"):
                data["finished_at"] = now
            elif data.get("finished_at"):
                data["finished_at"] = None
            return
    raise SystemExit(f"неизвестный этап: {stage}")


def update(task_dir: str, stage: str, status: str, files=None) -> None:
    path = Path(task_dir) / "task.json"
    with _locked(path):
        data = json.loads(path.read_text(encoding="utf-8"))
        _apply_update(data, stage, status, files)
        _atomic_write_json(path, data)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Обновить статус этапа задачи")
    ap.add_argument("task_dir")
    ap.add_argument("stage")
    ap.add_argument("status",
                    help="pending|running|done|failed|skipped|approve, "
                         "или start|done для псевдоэтапа db-update")
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

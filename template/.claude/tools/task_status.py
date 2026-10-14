#!/usr/bin/env python
"""Обновить статус этапа задачи в task.json. Самодостаточный скрипт (без agentmon).

Дополнительно обеспечивает гейты: нельзя перевести этап в `running`, пока
предыдущий включённый этап с `gate: true` не подтверждён (`approved: true`).
Подтверждение ставится командой со статусом `approve`.
"""
import argparse
import json
import time
from pathlib import Path

VALID = ("pending", "running", "done", "failed", "skipped", "approve")

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
        if _truthy(s.get("gate")) and not _truthy(s.get("approved")):
            return (
                f"гейт не пройден: этап '{s['name']}' требует подтверждения перед "
                f"запуском '{target_stage}'. Подтвердите командой:\n"
                f"  python .claude/tools/task_status.py <task_dir> {s['name']} approve")
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


def update(task_dir: str, stage: str, status: str, files) -> None:
    path = Path(task_dir) / "task.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for s in data.get("stages", []):
        if s["name"] == stage:
            if status == "approve":
                s["approved"] = True
            else:
                if status == "running":
                    msg = _gate_block(data, stage)
                    if msg:
                        raise SystemExit("ОШИБКА (гейт): " + msg)
                s["status"] = status
                data["stage"] = stage
                changed = s.setdefault("changed_files", [])
                for f in (files or []):
                    if f not in changed:
                        changed.append(f)
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
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            return
    raise SystemExit(f"неизвестный этап: {stage}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Обновить статус этапа задачи")
    ap.add_argument("task_dir")
    ap.add_argument("stage")
    ap.add_argument("status", choices=VALID,
                    help="pending|running|done|failed|skipped|approve "
                         "(approve — подтвердить гейт этапа, не меняя статус)")
    ap.add_argument("--files", nargs="*", default=[])
    args = ap.parse_args(argv)
    update(args.task_dir, args.stage, args.status, args.files)


if __name__ == "__main__":
    main()

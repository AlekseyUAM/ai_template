#!/usr/bin/env python3
"""Обновить статус этапа задачи в task.json. Самодостаточный скрипт (без agentmon).

Дополнительно обеспечивает гейты: нельзя перевести этап в `running`, пока
предыдущий включённый этап с `gate: true` не подтверждён (`approved: true`).
Подтверждение ставится командой со статусом `approve`.
"""
import argparse
import json
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
                f"  python3 .claude/tools/task_status.py <task_dir> {s['name']} approve")
    return None


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
                changed = s.setdefault("changed_files", [])
                for f in (files or []):
                    if f not in changed:
                        changed.append(f)
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

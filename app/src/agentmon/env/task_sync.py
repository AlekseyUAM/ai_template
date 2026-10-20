"""Перенос task.json → БД (этапы/статус/отметки времени) для одной задачи.

Источник истины по прогрессу задачи — её task.json, который правит оркестратор
на хосте проекта; дерево монитора и Telegram-нотификатор читают БД. Эти функции
закрывают разрыв «файл ↔ БД» и используются в двух местах:
- фоновым стек-раннером при завершении прогона (чтобы гейт/этапы доезжали до БД
  без участия UI);
- эндпоинтом POST /api/env/projects/{pid}/refresh.
"""
import json
import time
from pathlib import Path

from agentmon.store.tasks import TaskRepo
from agentmon.env.task_schema import task_folder_name
from agentmon.env.task_model import overall_status

# Статусами queued/stopped владеет стек/очередь — в task.json их нет, поэтому
# status из файла для них не перезаписываем (иначе выбьем задачу из очереди).
PROTECTED_STATUSES = {"queued", "stopped"}


def _apply_stage_timings(file_stages, prev_by_name, now) -> list:
    """Дошт­амповывает недостающие started_at/finished_at этапов.

    task_status.py (инструмент оркестратора) должен ставить started_at при
    переходе этапа в running и finished_at при done/failed. Если агент пометил
    этап минуя инструмент, тайминги остаются null — восполняем их как фолбэк.

    Защита от дрейфа: если в файле timestamp нет, берём прежнее значение из БД
    (prev_by_name); только когда нет нигде — ставим now. Иначе каждый синк
    переписывал бы время заново.
    """
    for s in file_stages:
        prev = prev_by_name.get(s.get("name"), {})
        status = s.get("status")
        if s.get("started_at") is None:
            if prev.get("started_at") is not None:
                s["started_at"] = prev["started_at"]
            elif status in ("running", "done", "failed"):
                s["started_at"] = now
        if status in ("done", "failed") and s.get("finished_at") is None:
            if prev.get("finished_at") is not None:
                s["finished_at"] = prev["finished_at"]
            else:
                s["finished_at"] = now
    return file_stages


def sync_task_from_file(store, project_path, task, now_fn=time.time) -> dict | None:
    """Читает task.json задачи и переносит актуальные поля в БД.

    Возвращает словарь применённых полей; None — если файла нет или он битый
    (в этом случае БД не трогается).
    """
    folder = task_folder_name(task["id"], task.get("identifier"))
    tj = Path(project_path) / "tasks" / folder / "task.json"
    if not tj.exists():
        return None
    try:
        data = json.loads(tj.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None

    fields = {}
    for key in ("stage", "started_at", "finished_at"):
        if key in data:
            fields[key] = data.get(key)
    file_status = data.get("status")
    if file_status and task.get("status") not in PROTECTED_STATUSES:
        fields["status"] = file_status
    if "stages" in data:
        prev_by_name = {}
        try:
            for s in json.loads(task.get("stages_json") or "[]"):
                prev_by_name[s.get("name")] = s
        except (ValueError, TypeError):
            pass
        stages = _apply_stage_timings(data["stages"], prev_by_name, now_fn())
        fields["stages_json"] = json.dumps(stages, ensure_ascii=False)
    if "db_update" in data:
        fields["db_update_json"] = json.dumps(data["db_update"], ensure_ascii=False)
    if fields:
        TaskRepo(store).update(task["id"], **fields)
    return fields


def write_stage_approval(project_path, task, stage_name) -> bool:
    """Ставит approved=true указанному этапу в task.json и пересчитывает status.

    Approve из UI/Telegram меняет только БД, а источник истины для оркестратора —
    task.json: его гейт стережёт task_status.py (`_gate_block`), который не пустит
    следующий этап в running, пока в файле approved=false. Без этой записи после
    одобрения задача не возобновляется. Возвращает True, если файл обновлён.
    """
    folder = task_folder_name(task["id"], task.get("identifier"))
    tj = Path(project_path) / "tasks" / folder / "task.json"
    if not tj.exists():
        return False
    try:
        data = json.loads(tj.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    found = False
    for s in data.get("stages", []):
        if s.get("name") == stage_name:
            s["approved"] = True
            found = True
            break
    if not found:
        return False
    data["status"] = overall_status(data.get("stages", []))
    tj.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                  encoding="utf-8")
    return True

"""Перенос task.json → БД (этапы/статус/отметки времени) для одной задачи.

Источник истины по прогрессу задачи — её task.json, который правит оркестратор
на хосте проекта; дерево монитора и Telegram-нотификатор читают БД. Эта функция
закрывает разрыв «файл → БД» и используется в двух местах:
- фоновым стек-раннером при завершении прогона (чтобы гейт/этапы доезжали до БД
  без участия UI);
- эндпоинтом POST /api/env/projects/{pid}/refresh.
"""
import json
from pathlib import Path

from agentmon.store.tasks import TaskRepo
from agentmon.env.task_schema import task_folder_name

# Статусами queued/stopped владеет стек/очередь — в task.json их нет, поэтому
# status из файла для них не перезаписываем (иначе выбьем задачу из очереди).
PROTECTED_STATUSES = {"queued", "stopped"}


def sync_task_from_file(store, project_path, task) -> dict | None:
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
        fields["stages_json"] = json.dumps(data["stages"], ensure_ascii=False)
    if "db_update" in data:
        fields["db_update_json"] = json.dumps(data["db_update"], ensure_ascii=False)
    if fields:
        TaskRepo(store).update(task["id"], **fields)
    return fields

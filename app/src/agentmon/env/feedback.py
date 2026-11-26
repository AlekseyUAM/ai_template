"""Приём пользовательских замечаний: БД + зеркало в USER_FEEDBACK.md."""
from pathlib import Path

from agentmon.env.task_json import atomic_write_text_prov
from agentmon.env.task_schema import task_folder_name
from agentmon.store.telegram_store import FeedbackRepo

HEADER = "# Замечания пользователя\n\n"


def save_feedback(db, project_path: str, task: dict, chat_id: str, text: str,
                  now=None, prov=None) -> None:
    FeedbackRepo(db).add(task_id=task["id"], chat_id=chat_id, text=text, now=now)

    folder = task_folder_name(task["id"], task.get("identifier"))
    stamp = f"- (chat {chat_id}, t={now}) {text}\n"
    if prov is not None:
        path = f"{str(project_path).rstrip('/')}/tasks/{folder}/USER_FEEDBACK.md"
        existing = prov.read_text(path) if prov.exists(path) else HEADER
        atomic_write_text_prov(prov, path, existing + stamp)
        return
    path = Path(project_path) / "tasks" / folder / "USER_FEEDBACK.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else HEADER
    path.write_text(existing + stamp, encoding="utf-8")

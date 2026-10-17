"""Приём пользовательских замечаний: БД + зеркало в USER_FEEDBACK.md."""
from pathlib import Path

from agentmon.env.task_schema import task_folder_name
from agentmon.store.telegram_store import FeedbackRepo

HEADER = "# Замечания пользователя\n\n"


def save_feedback(db, project_path: str, task: dict, chat_id: str, text: str, now=None) -> None:
    FeedbackRepo(db).add(task_id=task["id"], chat_id=chat_id, text=text, now=now)

    folder = task_folder_name(task["id"], task.get("identifier"))
    path = Path(project_path) / "tasks" / folder / "USER_FEEDBACK.md"
    existing = path.read_text(encoding="utf-8") if path.exists() else HEADER
    stamp = f"- (chat {chat_id}, t={now}) {text}\n"
    path.write_text(existing + stamp, encoding="utf-8")

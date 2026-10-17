from pathlib import Path
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.telegram_store import FeedbackRepo
from agentmon.telegram.feedback import save_feedback


def test_save_feedback_writes_db_and_file(tmp_path):
    db = connect(":memory:")
    init_schema(db)
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    task = {"id": 1, "identifier": "001"}
    save_feedback(db, str(tmp_path), task, chat_id="111", text="почини отбор", now=1.0)

    rows = FeedbackRepo(db).list_for_task(1)
    assert rows[0]["text"] == "почини отбор"

    md = (tmp_path / "tasks" / "task#001" / "USER_FEEDBACK.md").read_text(encoding="utf-8")
    assert "почини отбор" in md


def test_save_feedback_appends(tmp_path):
    db = connect(":memory:")
    init_schema(db)
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    task = {"id": 1, "identifier": "001"}
    save_feedback(db, str(tmp_path), task, "111", "первое", now=1.0)
    save_feedback(db, str(tmp_path), task, "111", "второе", now=2.0)
    md = (tmp_path / "tasks" / "task#001" / "USER_FEEDBACK.md").read_text(encoding="utf-8")
    assert "первое" in md and "второе" in md

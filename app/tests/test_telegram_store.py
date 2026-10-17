from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.telegram_store import NotifyStateRepo, FeedbackRepo


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


def test_notify_state_upsert():
    repo = NotifyStateRepo(_db())
    assert repo.get("task", 1) is None
    repo.set("task", 1, "running")
    assert repo.get("task", 1) == "running"
    repo.set("task", 1, "done")              # второй set — update, не дубль
    assert repo.get("task", 1) == "done"


def test_feedback_add_and_list():
    repo = FeedbackRepo(_db())
    fid = repo.add(task_id=5, chat_id="111", text="почини X", now=1.0)
    assert isinstance(fid, int)
    rows = repo.list_for_task(5)
    assert len(rows) == 1
    assert rows[0]["text"] == "почини X"
    assert rows[0]["chat_id"] == "111"

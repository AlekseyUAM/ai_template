import pytest
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.tasks import TaskRepo
from agentmon.telegram.notifier import TelegramNotifier


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


class _Sender:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text):
        self.sent.append((chat_id, text))


def _add_project(db):
    return db.returning_id("projects", ["name", "path"], ["p", "/tmp/p"])


@pytest.mark.asyncio
async def test_baseline_silent_then_transition():
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])

    await n.tick()                       # baseline — молчим
    assert s.sent == []

    tr.set_status(tid, "done")
    await n.tick()                       # переход running→done — уведомляем
    assert len(s.sent) == 1
    assert s.sent[0][0] == "111"
    assert "done" in s.sent[0][1].lower() or "заверш" in s.sent[0][1].lower()


@pytest.mark.asyncio
async def test_no_duplicate_on_same_status():
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline
    await n.tick()                       # статус не менялся
    assert s.sent == []

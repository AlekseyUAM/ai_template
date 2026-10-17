import pytest
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.stacks import StackRepo
from agentmon.telegram.handlers import Handlers


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


class _Caps:
    def __init__(self):
        self.sent, self.answered, self.posted = [], [], []

    async def send(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))

    async def answer(self, cq_id, text=None):
        self.answered.append((cq_id, text))

    async def api_post(self, path, json=None):
        self.posted.append(path)
        return {"ok": True}


def _handlers(db, caps, chat_ids=("111",)):
    return Handlers(db, caps.send, caps.answer, caps.api_post, list(chat_ids),
                    base_path_of=lambda pid: "/tmp/p")


@pytest.mark.asyncio
async def test_unauthorized_ignored():
    db = _db()
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"message": {"chat": {"id": 999}, "text": "/stacks"}})
    assert caps.sent == []                 # чужой чат — молчим


@pytest.mark.asyncio
async def test_stacks_command_lists():
    db = _db()
    StackRepo(db).add(name="001")
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"message": {"chat": {"id": 111}, "text": "/stacks"}})
    assert caps.sent and "001" in caps.sent[0][1]


@pytest.mark.asyncio
async def test_stack_stop_calls_rest():
    db = _db()
    sid = StackRepo(db).add(name="001")
    caps = _Caps()
    h = _handlers(db, caps)
    await h.handle_update({"callback_query": {
        "id": "cq1", "message": {"chat": {"id": 111}},
        "data": f"stk:stop:{sid}"}})
    assert f"/api/env/stacks/{sid}/stop" in caps.posted
    assert caps.answered                   # ответили на callback


@pytest.mark.asyncio
async def test_gate_note_flow_saves_and_approves(tmp_path):
    db = _db()
    pid = db.returning_id("projects", ["name", "path"], ["p", str(tmp_path)])
    from agentmon.store.tasks import TaskRepo
    import json
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.update(tid, identifier="001",
              stages_json=json.dumps([{"name": "analyze", "artifact": "ANALYZE.md",
                                       "enabled": True, "gate": True}]))
    (tmp_path / "tasks" / "task#001").mkdir(parents=True)
    caps = _Caps()
    h = Handlers(db, caps.send, caps.answer, caps.api_post, ["111"],
                 base_path_of=lambda p: str(tmp_path))

    # нажали «Замечание» — бот ждёт текст
    await h.handle_update({"callback_query": {
        "id": "cq2", "message": {"chat": {"id": 111}}, "data": f"gate:note:{tid}:analyze"}})
    # прислали текст замечания
    await h.handle_update({"message": {"chat": {"id": 111}, "text": "учти Y"}})

    from agentmon.store.telegram_store import FeedbackRepo
    assert FeedbackRepo(db).list_for_task(tid)[0]["text"] == "учти Y"
    assert f"/api/env/tasks/{tid}/approve" in " ".join(caps.posted)

import json
from pathlib import Path

import pytest
from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.tasks import TaskRepo
from agentmon.store.stacks import StackRepo
from agentmon.env.task_model import build_stages
from agentmon.telegram.notifier import TelegramNotifier


def _db():
    db = connect(":memory:")
    init_schema(db)
    return db


class _Sender:
    def __init__(self):
        self.sent = []

    async def send(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))


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


# --- новые тесты для FIX 1 ---

@pytest.mark.asyncio
async def test_stack_stop_notifies():
    """Ручная остановка (stopped) должна порождать уведомление «остановлен»."""
    db = _db()
    sr = StackRepo(db)
    sid = sr.add(name="mystack")
    # baseline: stack только что создан, статус по умолчанию idle
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    sr.set_status(sid, "running")
    await n.tick()                       # baseline — молчим
    assert s.sent == []

    sr.set_status(sid, "stopped")
    await n.tick()
    assert len(s.sent) == 1
    assert "остановлен" in s.sent[0][1]


@pytest.mark.asyncio
async def test_stack_idle_notifies_as_завершён():
    """Естественное завершение (idle, не все done) → «завершён», НЕ «остановлен»."""
    db = _db()
    sr = StackRepo(db)
    sid = sr.add(name="mystack")
    sr.set_status(sid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline

    sr.set_status(sid, "idle")
    await n.tick()
    assert len(s.sent) == 1
    assert "завершён" in s.sent[0][1]
    assert "остановлен" not in s.sent[0][1]


@pytest.mark.asyncio
async def test_stack_all_done_notifies_as_выполнен():
    """Стек со всеми задачами done → _stack_status='completed' → «выполнен»."""
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    sr = StackRepo(db)
    sid = sr.add(name="mystack")
    sr.set_status(sid, "running")
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    sr.add_item(sid, tid)

    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline (running, item not done)

    tr.set_status(tid, "done")
    await n.tick()
    # task transition (done) + stack transition (completed) both fire
    texts = [text for _, text, _ in s.sent]
    assert any("выполнен" in t for t in texts)


@pytest.mark.asyncio
async def test_notifier_failure_does_not_advance_state():
    """Если sender бросает исключение, last_status не продвигается;
    следующий тик с рабочим sender должен повторно отправить то же уведомление."""
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")

    # sender, который всегда бросает
    class _FailSender:
        async def send(self, chat_id, text, reply_markup=None):
            raise RuntimeError("network down")

    fail_s = _FailSender()
    n_fail = TelegramNotifier(db, fail_s.send, ["111"])
    await n_fail.tick()                  # baseline (using fail sender, sets state silently)

    tr.set_status(tid, "done")
    await n_fail.tick()                  # попытка отправить — падает, state НЕ продвигается

    # теперь рабочий sender — должен снова получить уведомление
    ok_s = _Sender()
    n_ok = TelegramNotifier(db, ok_s.send, ["111"])
    await n_ok.tick()                    # state не продвинулся → повторная попытка
    assert len(ok_s.sent) == 1
    assert "заверш" in ok_s.sent[0][1].lower() or "done" in ok_s.sent[0][1].lower()


# --- кнопки гейта на уведомлении awaiting_user ---

def _gate_task(db, pid):
    """Задача с гейтом на analyze (done, не approved) и pending-этапом plan после."""
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    stages = build_stages(["analyze", "plan"], gated_names=["analyze"])
    for st in stages:
        if st["name"] == "analyze":
            st["status"] = "done"
    tr.update(tid, stages_json=json.dumps(stages, ensure_ascii=False))
    return tid


def _callbacks(markup):
    return [btn["callback_data"]
            for row in markup["inline_keyboard"] for btn in row]


@pytest.mark.asyncio
async def test_awaiting_user_notification_carries_gate_buttons():
    db = _db()
    pid = _add_project(db)
    tid = _gate_task(db, pid)
    tr = TaskRepo(db)
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline — молчим
    assert s.sent == []

    tr.set_status(tid, "awaiting_user")
    await n.tick()                       # переход → уведомление с кнопками
    assert len(s.sent) == 1
    _chat, text, markup = s.sent[0]
    assert "гейт" in text
    assert markup is not None
    cbs = _callbacks(markup)
    assert f"gate:ok:{tid}:analyze" in cbs
    assert f"gate:note:{tid}:analyze" in cbs


@pytest.mark.asyncio
async def test_awaiting_user_includes_stage_report(tmp_path):
    """На гейте приходит содержимое артефакта этапа, а кнопки — на последнем
    (prompt) сообщении."""
    db = _db()
    pid = db.returning_id("projects", ["name", "path"], ["p", str(tmp_path)])
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    stages = build_stages(["analyze", "develop"], gated_names=["analyze"])
    for st in stages:
        if st["name"] == "analyze":
            st["status"] = "done"
    tr.update(tid, stages_json=json.dumps(stages, ensure_ascii=False))
    # артефакт этапа analyze на диске
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "ANALYZE.md").write_text("СОДЕРЖИМОЕ ОТЧЁТА ABC", encoding="utf-8")

    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline
    tr.set_status(tid, "awaiting_user")
    await n.tick()

    texts = [t for _, t, _ in s.sent]
    assert any("СОДЕРЖИМОЕ ОТЧЁТА ABC" in t for t in texts), \
        "содержимое артефакта этапа должно прийти в чат"
    # кнопки — на последнем сообщении (prompt)
    _chat, _text, last_markup = s.sent[-1]
    assert last_markup is not None
    cbs = _callbacks(last_markup)
    assert f"gate:ok:{tid}:analyze" in cbs
    assert f"gate:note:{tid}:analyze" in cbs


@pytest.mark.asyncio
async def test_non_gate_notification_has_no_buttons():
    """Обычные переходы (running/done/...) идут без inline-клавиатуры."""
    db = _db()
    pid = _add_project(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t", goal="g", plan="", constraints="", tests="")
    tr.set_status(tid, "running")
    s = _Sender()
    n = TelegramNotifier(db, s.send, ["111"])
    await n.tick()                       # baseline
    tr.set_status(tid, "done")
    await n.tick()
    assert len(s.sent) == 1
    assert s.sent[0][2] is None

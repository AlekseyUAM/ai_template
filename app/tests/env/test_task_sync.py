"""Тесты task_sync: дошт­амп таймингов этапов и запись approval в task.json."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone

from agentmon.store.db import connect
from agentmon.store.schema import init_schema
from agentmon.store.projects import ProjectRepo
from agentmon.store.tasks import TaskRepo
from agentmon.env.task_sync import sync_task_from_file, write_stage_approval
from agentmon.env.task_model import build_stages


def _setup(tmp_path):
    db = connect(":memory:")
    init_schema(db)
    pid = ProjectRepo(db).add(name="p", path=str(tmp_path))
    tr = TaskRepo(db)
    tid = tr.add(project_id=pid, name="t")
    return db, tr, tid


def _write_task_json(tmp_path, tid, stages, status="running"):
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "task.json").write_text(
        json.dumps({"status": status, "stages": stages}, ensure_ascii=False),
        encoding="utf-8")


def _done_analyze():
    stages = build_stages(["analyze", "develop"], gated_names=["analyze"])
    for s in stages:
        if s["name"] == "analyze":
            s["status"] = "done"
    return stages


# ─── баг #2: дошт­амп таймингов этапов ────────────────────────────────────────

def test_sync_stamps_missing_stage_timings(tmp_path):
    """Этап done с null-таймингами в файле → монитор ставит started_at/finished_at."""
    db, tr, tid = _setup(tmp_path)
    _write_task_json(tmp_path, tid, _done_analyze(), status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 1000.0
    assert analyze["finished_at"] == 1000.0


def test_sync_does_not_drift_existing_timings(tmp_path):
    """Повторный синк с другим now не должен сдвигать уже проставленное время."""
    db, tr, tid = _setup(tmp_path)
    _write_task_json(tmp_path, tid, _done_analyze(), status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)
    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 2000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 1000.0, "время не должно дрейфовать между синками"
    assert analyze["finished_at"] == 1000.0


def test_sync_preserves_file_timings(tmp_path):
    """Если тайминги есть в файле — берём их, не перетираем now."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"], s["finished_at"] = 5.0, 9.0
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 5.0
    assert analyze["finished_at"] == 9.0


# ─── баг #1: approve пишет approved в task.json ───────────────────────────────

def test_write_stage_approval_sets_flag_and_recomputes_status(tmp_path):
    db, tr, tid = _setup(tmp_path)
    _write_task_json(tmp_path, tid, _done_analyze(), status="awaiting_user")

    ok = write_stage_approval(str(tmp_path), tr.get(tid), "analyze")
    assert ok is True

    data = json.loads((Path(tmp_path) / "tasks" / f"task#{tid}" / "task.json")
                       .read_text(encoding="utf-8"))
    analyze = next(s for s in data["stages"] if s["name"] == "analyze")
    assert analyze["approved"] is True
    # analyze done+approved, develop pending → overall planned (гейт снят)
    assert data["status"] == "planned"


def test_write_stage_approval_no_file_is_noop(tmp_path):
    db, tr, tid = _setup(tmp_path)
    assert write_stage_approval(str(tmp_path), tr.get(tid), "analyze") is False


def test_unknown_file_status_ignored(tmp_path):
    """Опечатка в task.json не должна попадать в БД."""
    import json
    from agentmon.store.db import connect
    from agentmon.store.schema import init_schema
    from agentmon.store.tasks import TaskRepo
    from agentmon.env import task_sync

    db = connect(str(tmp_path / "db.sqlite"))
    init_schema(db)
    tr = TaskRepo(db)
    tid = tr.add(project_id=1, name="t", identifier="001", status="planned")
    folder = tmp_path / "proj" / "tasks" / "task#001"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({"status": "awaiting_userr"}),
                                      encoding="utf-8")

    task = tr.get(tid)
    task_sync.sync_task_from_file(db, str(tmp_path / "proj"), task)
    assert tr.get(tid)["status"] == "planned"


# ─── ISO-даты task.json → epoch в БД ─────────────────────────────────────────

_MSK = timezone(timedelta(hours=3))


def _epoch_11_msk():
    return datetime(2026, 11, 13, 11, 0, tzinfo=_MSK).timestamp()


def _epoch_0830_utc():
    return datetime(2026, 11, 13, 8, 30, tzinfo=timezone.utc).timestamp()


def test_sync_converts_iso_stage_timings(tmp_path):
    """ISO-даты этапов из файла → epoch-числа в БД."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = "2026-11-13T11:00:00+03:00"
            s["finished_at"] = "2026-11-13T08:30:00Z"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == _epoch_11_msk()
    assert analyze["finished_at"] == _epoch_0830_utc()


def test_sync_mixed_epoch_and_iso_timings(tmp_path):
    """Старое число и новая ISO-строка в одном файле — оба в БД числами."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = 5.0
            s["finished_at"] = "2026-11-13T08:30:00Z"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 5.0
    assert analyze["finished_at"] == _epoch_0830_utc()


def test_sync_converts_task_level_iso_timings(tmp_path):
    """Task-level started_at/finished_at из файла → числа в колонках БД."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "started_at": "2026-11-13T11:00:00+03:00",
        "finished_at": None,
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    assert tr.get(tid)["started_at"] == _epoch_11_msk()
    assert tr.get(tid)["finished_at"] is None


def test_sync_converts_db_update_iso_timings(tmp_path):
    """db_update: ISO внутри словаря → числа в JSON-строке БД, прочее сохраняется."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "db_update": {
            "started_at": "2026-11-13T11:00:00+03:00",
            "finished_at": "2026-11-13T08:30:00Z",
            "note": "keep",
        },
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    db_update = json.loads(tr.get(tid)["db_update_json"])
    assert db_update["started_at"] == _epoch_11_msk()
    assert db_update["finished_at"] == _epoch_0830_utc()
    assert db_update["note"] == "keep"


def test_sync_invalid_iso_falls_back_to_now(tmp_path):
    """Мусор вместо даты не роняет синк: этап done получает фолбэк now."""
    db, tr, tid = _setup(tmp_path)
    stages = _done_analyze()
    for s in stages:
        if s["name"] == "analyze":
            s["started_at"] = "не дата"
    _write_task_json(tmp_path, tid, stages, status="awaiting_user")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    analyze = next(s for s in json.loads(tr.get(tid)["stages_json"])
                   if s["name"] == "analyze")
    assert analyze["started_at"] == 1000.0
    assert analyze["finished_at"] == 1000.0


def test_sync_invalid_task_level_iso_becomes_none(tmp_path):
    """Невалидная task-level дата — как отсутствующая (None), без исключения."""
    db, tr, tid = _setup(tmp_path)
    folder = Path(tmp_path) / "tasks" / f"task#{tid}"
    folder.mkdir(parents=True)
    (folder / "task.json").write_text(json.dumps({
        "status": "running",
        "started_at": "не дата",
        "stages": [],
    }, ensure_ascii=False), encoding="utf-8")

    sync_task_from_file(db, str(tmp_path), tr.get(tid), now_fn=lambda: 1000.0)

    assert tr.get(tid)["started_at"] is None

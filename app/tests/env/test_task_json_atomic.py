"""task.json: атомарная запись и межпроцессный lock."""
import importlib.util
import json
import threading
from pathlib import Path

from agentmon.env import task_schema as ts
from agentmon.env import task_sync
from agentmon.env.task_json import update_json

CLI = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools" / "task_status.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("task_status_atomic", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_update_json_serializes_read_modify_write(tmp_path):
    path = tmp_path / "task.json"
    path.write_text(json.dumps({"counter": 0}), encoding="utf-8")
    threads_n, per_thread = 8, 25

    def worker():
        for _ in range(per_thread):
            update_json(path, lambda data: data.__setitem__(
                "counter", data["counter"] + 1))

    threads = [threading.Thread(target=worker) for _ in range(threads_n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert json.loads(path.read_text(encoding="utf-8"))["counter"] == threads_n * per_thread


def test_reader_never_sees_torn_json(tmp_path):
    mod = _load_cli()
    d = tmp_path / "task#001"
    d.mkdir()
    stages = [{"name": f"s{i}", "enabled": True, "status": "pending",
               "gate": False, "approved": False, "changed_files": []}
              for i in range(1500)]
    path = d / "task.json"
    path.write_text(json.dumps({"stages": stages, "status": "planned"}),
                    encoding="utf-8")

    stop = threading.Event()
    errors = []

    def writer():
        for _ in range(150):
            mod.update(str(d), "s0", "done")
        stop.set()

    def reader():
        while not stop.is_set():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except ValueError as exc:
                errors.append(exc)
                return

    w = threading.Thread(target=writer)
    r = threading.Thread(target=reader)
    r.start(); w.start(); w.join(); r.join()
    assert errors == [], f"читатель увидел обрезанный JSON: {errors[:1]}"


def test_approve_and_stage_update_do_not_lose_each_other(tmp_path):
    """approve из UI и update оркестратора не затирают правки друг друга."""
    mod = _load_cli()
    for attempt in range(20):
        s = ts.create_task(tmp_path, title="t", goal="", plan="", constraints="",
                           enabled_stages=ts.STAGE_NAMES)
        d = ts.task_dir(tmp_path, s.id)
        # approve идёт в analyze, update — в tests: разные поля одного файла.
        task = {"id": int(s.id), "identifier": s.id}
        barrier = threading.Barrier(2)
        errors = []

        def do_approve():
            barrier.wait()
            try:
                task_sync.write_stage_approval(str(tmp_path), task, "analyze")
            except Exception as exc:              # noqa: BLE001
                errors.append(exc)

        def do_update():
            barrier.wait()
            try:
                mod.update(str(d), "tests", "done")
            except Exception as exc:              # noqa: BLE001
                errors.append(exc)

        t1 = threading.Thread(target=do_approve)
        t2 = threading.Thread(target=do_update)
        t1.start(); t2.start(); t1.join(); t2.join()
        assert errors == []
        data = json.loads((d / "task.json").read_text(encoding="utf-8"))
        by = {st["name"]: st for st in data["stages"]}
        assert by["analyze"]["approved"] is True, f"потерян approve (попытка {attempt})"
        assert by["tests"]["status"] == "done", f"потерян статус этапа (попытка {attempt})"

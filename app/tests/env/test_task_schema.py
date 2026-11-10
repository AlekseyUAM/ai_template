from agentmon.env import task_schema as ts


def test_orchestration_prompt_mentions_task_and_skill():
    p = ts.orchestration_prompt("100007")
    assert "tasks/task#100007" in p and "task-orchestration" in p


def test_orchestration_prompt_uses_identifier_when_present():
    """v2-задача с идентификатором → каталог task#{identifier} (префикс task# обязателен
    для распознавания хуком route_to_orchestrator)."""
    p = ts.orchestration_prompt(123, "FEAT-7")
    assert "tasks/task#FEAT-7" in p


def test_next_id_empty_is_base(tmp_path):
    assert ts.next_task_id(tmp_path) == "100001"


def test_create_task_writes_files(tmp_path):
    spec = ts.create_task(tmp_path, title="T", goal="цель", plan="план",
                          constraints="огр", enabled_stages=ts.STAGE_NAMES)
    d = ts.task_dir(tmp_path, spec.id)
    assert (d / "task.json").exists()
    assert "цель" in (d / "TASK.md").read_text(encoding="utf-8")
    assert len(spec.stages) == 7
    assert all(s.status == "pending" for s in spec.stages)


def test_next_id_increments(tmp_path):
    first = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                           enabled_stages=ts.STAGE_NAMES)
    assert first.id == "100001"
    assert ts.next_task_id(tmp_path) == "100002"


def test_disabled_stage_is_skipped(tmp_path):
    spec = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                          enabled_stages=["analyze", "plan"])
    by = {s.name: s for s in spec.stages}
    assert by["analyze"].status == "pending"
    assert by["docs"].status == "skipped" and by["docs"].enabled is False


def test_roundtrip_and_list(tmp_path):
    ts.create_task(tmp_path, title="a", goal="g", plan="p", constraints="c",
                   enabled_stages=ts.STAGE_NAMES)
    tasks = ts.list_tasks(tmp_path)
    assert len(tasks) == 1
    d = ts.task_dir(tmp_path, tasks[0].id)
    assert ts.load_task(d).title == "a"


def test_loads_v2_stage_with_gates_and_extra_fields(tmp_path):
    import json
    d = tmp_path / "task#001"
    d.mkdir()
    (d / "task.json").write_text(json.dumps({
        "id": "001", "name": "Задача", "title": "Задача",
        "goal": "g", "plan": "p", "constraints": "c", "status": "awaiting_user",
        "identifier": "001", "project_id": 5, "update_db": True,
        "unknown_from_future": 1,
        "stages": [
            {"name": "analyze", "enabled": True, "subagent": "analyst",
             "artifact": "ANALYZE.md", "status": "done", "changed_files": [],
             "gate": True, "approved": False, "started_at": 1.0,
             "finished_at": 2.0, "iteration": 1, "new_field": "x"},
            {"name": "testing", "enabled": True, "subagent": "",
             "artifact": "TESTING.md", "status": "pending",
             "changed_files": [], "gate": False, "approved": False},
        ],
    }, ensure_ascii=False), encoding="utf-8")

    spec = ts.load_task(d)
    assert spec.title == "Задача"
    assert spec.status == "awaiting_user"
    assert spec.stages[0].gate is True and spec.stages[0].approved is False
    assert spec.stages[1].subagent == ""

    ts.save_task(d, spec)
    saved = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert saved["status"] == "awaiting_user"
    assert saved["stages"][0]["gate"] is True
    assert saved["stages"][1]["name"] == "testing"

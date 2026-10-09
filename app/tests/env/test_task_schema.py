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

import importlib.util
import json
from pathlib import Path
import pytest
from agentmon.env import task_schema as ts

CLI = Path(__file__).resolve().parents[3] / "template" / ".claude" / "tools" / "task_status.py"


def _load():
    spec = importlib.util.spec_from_file_location("task_status", CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _task(tmp_path):
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=ts.STAGE_NAMES)
    return ts.task_dir(tmp_path, s.id)


def test_cli_sets_status_and_files(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    mod.main([str(d), "develop", "done", "--files", "Module.bsl", "Form.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    dev = next(s for s in data["stages"] if s["name"] == "develop")
    assert dev["status"] == "done"
    assert dev["changed_files"] == ["Module.bsl", "Form.bsl"]


def test_cli_unknown_stage_errors(tmp_path):
    mod = _load()
    d = _task(tmp_path)
    with pytest.raises(SystemExit):
        mod.main([str(d), "nope", "done"])


def _one_stage_task(tmp_path):
    """Задача с единственным включённым этапом develop и верхнеуровневым status."""
    s = ts.create_task(tmp_path, title="a", goal="", plan="", constraints="",
                       enabled_stages=["develop"])
    d = ts.task_dir(tmp_path, s.id)
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    data["status"] = "planned"
    (d / "task.json").write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    return d


def test_cli_rolls_up_overall_status_to_done(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done", "--files", "Module.bsl"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "done"


def test_cli_rolls_up_overall_status_running(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "running"


def test_cli_rolls_up_overall_status_failed(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "failed"])
    data = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert data["status"] == "failed"


def test_cli_sets_started_and_finished_at(tmp_path):
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    running = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert isinstance(running["started_at"], (int, float))
    assert running.get("finished_at") is None

    mod.main([str(d), "develop", "done"])
    done = json.loads((d / "task.json").read_text(encoding="utf-8"))
    # started_at не перезаписывается, finished_at проставляется и не раньше старта
    assert done["started_at"] == running["started_at"]
    assert isinstance(done["finished_at"], (int, float))
    assert done["finished_at"] >= done["started_at"]


def test_cli_clears_finished_at_when_reopened(tmp_path):
    """Цикл review→develop: задача снова не терминальна — finished_at снимается."""
    mod = _load()
    d = _one_stage_task(tmp_path)
    mod.main([str(d), "develop", "running"])
    mod.main([str(d), "develop", "done"])
    assert json.loads((d / "task.json").read_text(encoding="utf-8"))["finished_at"]
    mod.main([str(d), "develop", "pending"])
    reopened = json.loads((d / "task.json").read_text(encoding="utf-8"))
    assert reopened["status"] == "planned"
    assert reopened["finished_at"] is None

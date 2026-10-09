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

import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[3] / "template" / ".claude" / "hooks" / "route_to_orchestrator.py"


def _load():
    spec = importlib.util.spec_from_file_location("r2o", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_task_prompt_routes_to_orchestrator():
    m = _load()
    out = m.build_output({"prompt": "Выполни задачу tasks/task#100001 ..."})
    assert "task-orchestration" in out["hookSpecificOutput"]["additionalContext"]


def test_windows_task_prompt_routes_to_orchestrator():
    """Windows-путь с обратными слэшами — тот же каталог задачи."""
    m = _load()
    out = m.build_output(
        {"prompt": r"Выполни задачу C:\work\proj\tasks\task#100001 по task.json"})
    assert "task-orchestration" in out["hookSpecificOutput"]["additionalContext"]


def test_other_prompt_silent():
    m = _load()
    assert m.build_output({"prompt": "просто вопрос"}) == {}

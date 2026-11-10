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


def test_non_string_prompt_does_not_crash(monkeypatch):
    import io
    m = _load()
    monkeypatch.setattr(m.sys, "stdin", io.StringIO('{"prompt": 123}'))
    monkeypatch.setattr(m.sys, "stdout", io.StringIO())
    m.main()                                  # не должно бросить
    assert m.sys.stdout.getvalue() == ""


def test_invalid_event_shape_does_not_crash(monkeypatch):
    import io
    m = _load()
    monkeypatch.setattr(m.sys, "stdin", io.StringIO('["not", "a", "dict"]'))
    monkeypatch.setattr(m.sys, "stdout", io.StringIO())
    m.main()
    assert m.sys.stdout.getvalue() == ""

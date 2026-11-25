import importlib.util
import json
from pathlib import Path

HOOK = (Path(__file__).resolve().parents[3] / "template" / ".claude"
        / "hooks" / "route_to_checklists.py")


def _load():
    spec = importlib.util.spec_from_file_location("r2c", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _project(tmp_path):
    task = tmp_path / "tasks" / "task#100001"
    task.mkdir(parents=True)
    (task / "task.json").write_text(json.dumps({
        "stages": [
            {"name": "analyze", "enabled": True, "subagent": "analyst",
             "artifact": "ANALYZE.md"},
            {"name": "develop", "enabled": True, "subagent": "developer",
             "artifact": "DEVELOP.md"},
            {"name": "docs", "enabled": False, "subagent": "technical-writer",
             "artifact": "DOCS.md"},
        ],
    }), encoding="utf-8")
    return tmp_path


def test_task_prompt_routes_to_checklists(tmp_path):
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "Single-agent" in context
    assert ".claude/checklists/analyst.md" in context
    assert ".claude/checklists/developer.md" in context
    assert "technical-writer" not in context      # disabled stage
    assert "ANALYZE.md" in context and "DEVELOP.md" in context


def test_first_action_is_mcp_usage(tmp_path):
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "First action" in context
    assert "mcp-usage" in context


def test_first_action_is_the_first_line(tmp_path):
    """The first-action line starts the injected context, before any checklist."""
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    first = context.splitlines()[0]
    assert "First action" in first and "mcp-usage" in first
    assert context.index("mcp-usage") < context.index("Checklists:")


def test_stage_scoped_first_action_is_mcp_usage(tmp_path, monkeypatch):
    m = _load()
    root = _project(tmp_path)
    monkeypatch.setenv("TASK_STAGE", "develop")
    out = m.build_output({"prompt": "tasks/task#100001", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "First action" in context
    assert "mcp-usage" in context


def _set_first_stage_gate(root):
    path = root / "tasks" / "task#100001" / "task.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["stages"][0]["gate"] = True
    path.write_text(json.dumps(data), encoding="utf-8")


def test_gate_reminder_only_when_task_has_gates(tmp_path):
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    assert "Gates:" not in out["hookSpecificOutput"]["additionalContext"]

    _set_first_stage_gate(root)
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task#100001 ...", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "Gates:" in context
    assert "STOP the run" in context
    assert "never call approve" in context


def test_double_hash_task_folder(tmp_path):
    """identifier="#001" → task##001: чеклисты и напоминание о гейте доходят."""
    m = _load()
    task = tmp_path / "tasks" / "task##001"
    task.mkdir(parents=True)
    (task / "task.json").write_text(json.dumps({"stages": [
        {"name": "analyze", "enabled": True, "subagent": "analyst",
         "artifact": "ANALYZE.md", "gate": True},
    ]}), encoding="utf-8")
    out = m.build_output(
        {"prompt": "Выполни задачу tasks/task##001 по этапам из её task.json.",
         "cwd": str(tmp_path)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert ".claude/checklists/analyst.md" in context
    assert "Gates:" in context


def test_windows_task_prompt_routes_to_checklists(tmp_path):
    """Windows-путь с обратными слэшами — тот же каталог задачи."""
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(
        {"prompt": r"Выполни задачу C:\work\proj\tasks\task#100001 по task.json",
         "cwd": str(root)})
    assert ".claude/checklists/analyst.md" in (
        out["hookSpecificOutput"]["additionalContext"])


def test_stage_scoped_mentions_only_current_stage(tmp_path, monkeypatch):
    m = _load()
    root = _project(tmp_path)
    monkeypatch.setenv("TASK_STAGE", "develop")
    out = m.build_output(
        {"prompt": "tasks/task#100001", "cwd": str(root)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "Stage-scoped" in context
    assert ".claude/checklists/developer.md" in context
    assert ".claude/checklists/analyst.md" not in context


def test_missing_task_json_falls_back(tmp_path):
    m = _load()
    out = m.build_output({"prompt": "tasks/task#100001", "cwd": str(tmp_path)})
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "Failed to read task.json" in context


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

import importlib.util
import io
import json
from pathlib import Path

HOOK = (Path(__file__).resolve().parents[3] / "template" / ".claude"
        / "hooks" / "stage_checklist.py")

STAGES = [
    {"name": "tests", "enabled": True, "subagent": "developer-tests",
     "artifact": "TESTS.md"},
    {"name": "develop", "enabled": True, "subagent": "developer",
     "artifact": "DEVELOP.md"},
    {"name": "testing", "enabled": True, "subagent": "",
     "artifact": "TESTING.md"},
]


def _load():
    spec = importlib.util.spec_from_file_location("stage_checklist", HOOK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _project(tmp_path, *, with_task=True, with_developer=True):
    task = tmp_path / "tasks" / "task#100001"
    task.mkdir(parents=True)
    if with_task:
        (task / "task.json").write_text(json.dumps({
            "max_minutes": 20,
            "stages": STAGES,
        }), encoding="utf-8")
    checklists = tmp_path / ".claude" / "checklists"
    checklists.mkdir(parents=True)
    if with_developer:
        (checklists / "developer.md").write_text(
            "# Developer\nREGISTER-RULE: use СрезПоследних\n", encoding="utf-8")
    (checklists / "developer-tests.md").write_text(
        "# Test developer\nSMOKE-RULE\n", encoding="utf-8")
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "single-agent-workflow.md").write_text(
        "# Single agent\nRULE\n", encoding="utf-8")
    return tmp_path


def _event(root, command, tool_name="Bash"):
    return {"tool_name": tool_name, "tool_input": {"command": command},
            "cwd": str(root)}


def _context(out):
    return out["hookSpecificOutput"]["additionalContext"]


def test_injects_checklist_on_stage_running(tmp_path):
    m = _load()
    root = _project(tmp_path)
    out = m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running"))
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    text = _context(out)
    assert 'Stage "develop" started' in text
    assert "deliberate re-read" in text
    assert "REGISTER-RULE" in text
    assert ".claude/checklists/developer.md" in text
    assert "DEVELOP.md" in text


def test_ignores_done(tmp_path):
    m = _load()
    root = _project(tmp_path)
    assert m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop done --files x.bsl")) == {}


def test_ignores_status(tmp_path):
    m = _load()
    root = _project(tmp_path)
    assert m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 status")) == {}


def test_ignores_unrelated_bash(tmp_path):
    m = _load()
    root = _project(tmp_path)
    assert m.build_output(_event(root, "echo hello")) == {}


def test_empty_subagent_uses_single_agent_workflow(tmp_path):
    m = _load()
    root = _project(tmp_path)
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "testing running")))
    assert ".claude/rules/single-agent-workflow.md" in text
    assert "RULE" in text
    assert "TESTING.md" in text


def test_missing_checklist_warns_with_path(tmp_path):
    m = _load()
    root = _project(tmp_path, with_developer=False)
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running")))
    assert "not found" in text
    assert ".claude/checklists/developer.md" in text


def test_missing_task_json_warns(tmp_path):
    m = _load()
    root = _project(tmp_path, with_task=False)
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running")))
    assert "task.json" in text
    assert "not found" in text


def test_stage_not_found_warns(tmp_path):
    m = _load()
    root = _project(tmp_path)
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "review running")))
    assert "review" in text
    assert "not found" in text


def test_stage_scoped_mode_is_silent(tmp_path, monkeypatch):
    m = _load()
    root = _project(tmp_path)
    monkeypatch.setenv("TASK_STAGE", "develop")
    assert m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running")) == {}


def test_compound_command_uses_last_running_stage(tmp_path):
    m = _load()
    root = _project(tmp_path)
    command = ("python .claude/tools/task_status.py tasks/task#100001 "
               "tests done --files x.bsl && "
               "python .claude/tools/task_status.py tasks/task#100001 "
               "develop running")
    text = _context(m.build_output(_event(root, command)))
    assert "REGISTER-RULE" in text
    assert "SMOKE-RULE" not in text
    assert ".claude/checklists/developer.md" in text


def test_windows_paths_in_command(tmp_path):
    m = _load()
    root = _project(tmp_path)
    command = ("python .claude\\tools\\task_status.py "
               "tasks\\task#100001 develop running")
    text = _context(m.build_output(_event(root, command)))
    assert "REGISTER-RULE" in text


def test_truncates_huge_checklist(tmp_path):
    m = _load()
    root = _project(tmp_path)
    (root / ".claude" / "checklists" / "developer.md").write_text(
        "X" * (m.MAX_CHARS + 5000), encoding="utf-8")
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running")))
    assert "truncated" in text
    assert len(text) <= m.MAX_CHARS + 1000


def test_cyrillic_content_preserved(tmp_path):
    m = _load()
    root = _project(tmp_path)
    (root / ".claude" / "checklists" / "developer.md").write_text(
        "ПРАВИЛО: СрезПоследних\n", encoding="utf-8")
    text = _context(m.build_output(_event(
        root, "python .claude/tools/task_status.py tasks/task#100001 "
              "develop running")))
    assert "ПРАВИЛО: СрезПоследних" in text


def test_non_bash_is_silent(tmp_path):
    m = _load()
    root = _project(tmp_path)
    assert m.build_output({
        "tool_name": "Edit",
        "tool_input": {"file_path": str(root / "x.bsl")},
        "cwd": str(root),
    }) == {}


def test_invalid_event_shape_does_not_crash(monkeypatch):
    m = _load()
    monkeypatch.setattr(m.sys, "stdin", io.StringIO('["not", "a", "dict"]'))
    monkeypatch.setattr(m.sys, "stdout", io.StringIO())
    m.main()
    assert m.sys.stdout.getvalue() == ""


def test_broken_json_does_not_crash(monkeypatch):
    m = _load()
    monkeypatch.setattr(m.sys, "stdin", io.StringIO("{not json"))
    monkeypatch.setattr(m.sys, "stdout", io.StringIO())
    m.main()
    assert m.sys.stdout.getvalue() == ""

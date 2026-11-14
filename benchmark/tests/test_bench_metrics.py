import json
from pathlib import Path

from bench_metrics import (aggregate_environment, classify_bash,
                           parse_tool_events, summarize_events,
                           summarize_transcripts)
from bench_metrics import SessionFiles
from bench_metrics import (collect_task_state, cycle_metrics,
                           run_static_analyzers, stage_table,
                           write_json_atomic)
from bench_run import TaskInfo


def write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False)
                              for row in rows) + "\n", encoding="utf-8")
    return path


def tool_use(ts: str, tool_id: str, name: str, tool_input: dict) -> dict:
    return {"type": "assistant", "timestamp": ts, "message": {
        "content": [{"type": "tool_use", "id": tool_id, "name": name,
                     "input": tool_input}]}}


def tool_result(ts: str, tool_id: str, content: str = "ok",
                is_error: bool = False) -> dict:
    return {"type": "user", "timestamp": ts, "message": {
        "content": [{"type": "tool_result", "tool_use_id": tool_id,
                     "content": content, "is_error": is_error}]}}


def test_parse_tool_events_pairs_duration(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "python .claude/tools/run-tests.py cfg.json"}),
        tool_result("2026-01-01T00:01:30+00:00", "t1"),
        tool_use("2026-01-01T00:02:00+00:00", "t2", "Edit",
                 {"file_path": "/p/src/cfe/ЮнитТесты/Module.bsl"}),
        tool_result("2026-01-01T00:02:01+00:00", "t2", "boom", True),
    ])
    events = parse_tool_events(path)
    assert events[0].duration_sec == 90.0
    assert events[1].is_error is True
    assert events[1].name == "Edit"


def test_classify_bash():
    assert classify_bash("python .claude/tools/run-tests.py x") == "test-run"
    assert classify_bash("python .claude/tools/run-tests.py --test A > smoke.log") == "test-run"
    assert classify_bash("python x load-extension src/cfe/ЮнитТесты") == "extension-load"
    assert classify_bash("python .claude/tools/load-config-optimized.py") == "config-load"
    assert classify_bash("python analyze_code.py x.bsl") == "static-check"
    assert classify_bash("git status") == "git"
    assert classify_bash("echo hi") == "other"


def test_summarize_events(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "python .claude/tools/run-tests.py a"}),
        tool_result("2026-01-01T00:01:00+00:00", "t1"),
        tool_use("2026-01-01T00:02:00+00:00", "t2", "Bash",
                 {"command": "python .claude/tools/run-tests.py b"}),
        tool_result("2026-01-01T00:02:30+00:00", "t2", "command not found", True),
        tool_use("2026-01-01T00:03:00+00:00", "t3", "Edit",
                 {"file_path": str(tmp_path / "src" / "cfe" / "ЮнитТесты" / "M.bsl")}),
        tool_result("2026-01-01T00:03:01+00:00", "t3"),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["test_runs"] == 2
    assert summary["tool_errors"] == 1
    assert summary["edits"]["src/cfe/ЮнитТесты/M.bsl"] == 1
    assert "command not found" in summary["error_signatures"][0]["signature"]
    assert summary["slow_ops"][0]["duration_sec"] == 60.0


def test_summarize_transcripts_and_subagent(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    main = write_jsonl(tmp_path / "main.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Agent",
                 {"description": "ревью", "prompt": "..."}),
        tool_result("2026-01-01T00:05:00+00:00", "t1"),
    ])
    subdir = tmp_path / "sid" / "subagents"
    subdir.mkdir(parents=True)
    sub = write_jsonl(subdir / "agent-a.jsonl", [
        tool_use("2026-01-01T00:00:10+00:00", "s1", "Read",
                 {"file_path": "/p/a.bsl"}),
        tool_result("2026-01-01T00:00:11+00:00", "s1"),
    ])
    (subdir / "agent-a.meta.json").write_text(json.dumps({
        "agentType": "reviewer", "description": "Ревью"}), encoding="utf-8")
    summary = summarize_transcripts(project, SessionFiles(main, (sub,)), None)
    assert summary["source"] == "session"
    assert summary["main"]["agent_calls"] == 1
    assert summary["subagents"][0]["agent"] == "reviewer"
    assert summary["subagents"][0]["tools"] == {"Read": 1}


def test_summarize_transcripts_falls_back_to_stream(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    fallback = write_jsonl(tmp_path / "stream.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "t1", "Bash",
                 {"command": "echo hi"}),
    ])
    summary = summarize_transcripts(project, SessionFiles(None, ()), fallback)
    assert summary["source"] == "stream"
    assert summary["main"]["tools"] == {"Bash": 1}


def test_mcp_tool_error_attributed(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "m1", "mcp__bsl_ls__check", {}),
        tool_result("2026-01-01T00:00:01+00:00", "m1", "server unavailable", True),
    ])
    summary = summarize_events(parse_tool_events(path), tmp_path)
    assert summary["error_signatures"][0]["signature"].startswith("mcp__bsl_ls__check:")
    env = aggregate_environment([{"transcript": {"main": summary}}])
    assert env["mcp_errors"] == 1


def test_aggregate_environment():
    tasks = [{"transcript": {"main": {"tool_errors": 2, "error_signatures": [
        {"signature": "command not found", "count": 1},
        {"signature": "timeout", "count": 1}]}}}]
    env = aggregate_environment(tasks)
    assert env["tool_errors"] == 2
    assert env["command_not_found"] == 1
    assert env["timeouts"] == 1


def test_aggregate_environment_timed_out_and_mcp():
    tasks = [{"transcript": {"main": {"tool_errors": 3, "error_signatures": [
        {"signature": "Bash: Command timed out after 2m", "count": 1},
        {"signature": "Bash: command not found", "count": 1},
        {"signature": "mcp__bsl_ls__check: server unavailable", "count": 1}]}}}]
    env = aggregate_environment(tasks)
    assert env["timeouts"] == 1
    assert env["command_not_found"] == 1
    assert env["mcp_errors"] == 1
    assert env["tool_errors"] == 3


def test_parse_tool_events_duplicate_id_keeps_first(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "dup", "Bash",
                 {"command": "echo hi"}),
        tool_use("2026-01-01T00:00:01+00:00", "dup", "Read",
                 {"file_path": "/p/a.bsl"}),
        tool_result("2026-01-01T00:00:30+00:00", "dup"),
    ])
    events = parse_tool_events(path)
    assert len(events) == 1
    assert events[0].name == "Bash"
    assert events[0].duration_sec is not None


def test_parse_tool_events_ignores_empty_result_id(tmp_path):
    path = write_jsonl(tmp_path / "t.jsonl", [
        tool_use("2026-01-01T00:00:00+00:00", "", "Bash",
                 {"command": "echo hi"}),
        tool_result("2026-01-01T00:00:30+00:00", ""),
    ])
    events = parse_tool_events(path)
    assert len(events) == 1
    assert events[0].name == "Bash"
    assert events[0].finished_at is None
    assert events[0].duration_sec is None


def test_aggregate_environment_tolerates_bad_transcript():
    env = aggregate_environment([{"transcript": "oops"},
                                 {"transcript": {"main": 42}}])
    assert env["tool_errors"] == 0
    assert env["timeouts"] == 0
    assert env["command_not_found"] == 0
    assert env["mcp_errors"] == 0
    assert env["error_signatures"] == []


def task_info(project: Path, folder: str) -> TaskInfo:
    path = project / "tasks" / folder
    data = json.loads((path / "task.json").read_text(encoding="utf-8"))
    return TaskInfo(folder, path, data["identifier"], data["max_minutes"],
                    data.get("status", ""), data)


def test_collect_task_state(tmp_path):
    project = tmp_path / "project"
    task_dir = project / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({
        "identifier": "001", "max_minutes": 30, "status": "planned"}),
        encoding="utf-8")
    (task_dir / "TASK.md").write_text("# TASK\n", encoding="utf-8")
    (task_dir / "DEVELOP.md").write_text("# dev\n", encoding="utf-8")
    (task_dir / "REVIEW.1.md").write_text("# old\n", encoding="utf-8")
    (task_dir / "REVIEW.md").write_text(
        "| Вердикт | ✓ ПРИНЯТО |\n", encoding="utf-8")
    logs = project / "logs" / "task#23"
    logs.mkdir(parents=True)
    (logs / "result.json").write_text(json.dumps({
        "Выполнено": True, "ОписаниеОшибки": None,
        "РезультатТестов": [{"Имя": "A", "Результат": True}]}),
        encoding="utf-8")
    task = task_info(project, "task##001")
    state = collect_task_state(project, task)
    assert "DEVELOP.md" in state["files"]
    assert state["verdicts"]["REVIEW.md"] == "✓ ПРИНЯТО"
    assert "REVIEW.1.md" in state["archives"]
    assert state["test_results"][0]["Выполнено"] is True


def test_stage_table_and_cycle_metrics():
    task_json = {"stages": [
        {"name": "tests", "enabled": True, "status": "done", "iteration": 3,
         "started_at": "2026-01-01T00:00:00+00:00",
         "finished_at": "2026-01-01T00:01:00+00:00", "changed_files": []},
        {"name": "review", "enabled": True, "status": "done", "iteration": 2,
         "started_at": "2026-01-01T00:01:00+00:00",
         "finished_at": None, "changed_files": []},
    ]}
    stages = stage_table(task_json)
    assert stages[0]["duration_sec"] == 60.0
    assert stages[1]["duration_sec"] is None
    cycles = cycle_metrics(
        task_json,
        {"archives": ["REVIEW.1.md"], "verdicts": {"REVIEW.md": "✓ ПРИНЯТО"}},
        {"main": {"test_runs": 4, "smoke_runs": 1,
                  "edits": {"src/cfe/ЮнитТесты/M.bsl": 5}}})
    assert cycles == {"tests_iteration": 3, "review_iteration": 2,
                      "review_archives": 1, "test_runs": 4,
                      "smoke_runs": 1, "test_module_edits": 5,
                      "review_verdict": "✓ ПРИНЯТО"}


def test_run_static_analyzers(tmp_path):
    project = tmp_path / "project"
    scripts = project / ".claude" / "skills"
    (scripts / "code-analyze" / "scripts").mkdir(parents=True)
    (scripts / "query-analyze" / "scripts").mkdir(parents=True)
    (scripts / "code-analyze" / "scripts" / "analyze_code.py").write_text(
        "print('warning | rule-1 | 1 | msg')\nprint('info | rule-2 | 2 | msg')\n",
        encoding="utf-8")
    (scripts / "query-analyze" / "scripts" / "extract_queries.py").write_text(
        "print('ВЫБРАТЬ 1')", encoding="utf-8")
    (scripts / "query-analyze" / "scripts" / "analyze_query.py").write_text(
        "import sys\nprint('error | q-1 | 1 | bad')\n", encoding="utf-8")
    target = project / "Module.bsl"
    target.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    reference = project / "example.bsl"
    reference.write_text("Процедура А()\nКонецПроцедуры\n", encoding="utf-8")
    result = run_static_analyzers(project, ["Module.bsl"], reference,
                                  tmp_path / "out")
    code = result["code_analyze"]["results"][str(target.resolve())]
    assert code["findings"] == {"warning": 1, "info": 1, "error": 0}
    assert str(reference.resolve()) in result["code_analyze"]["results"]
    query = result["query_analyze"]["results"][str(target.resolve())]
    assert query["findings"]["error"] == 1


def test_run_static_analyzers_missing_script(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    result = run_static_analyzers(project, [], None, tmp_path / "out")
    assert "не найден" in result["code_analyze"]["skipped"]


def test_write_json_atomic(tmp_path):
    path = tmp_path / "x.json"
    write_json_atomic(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}

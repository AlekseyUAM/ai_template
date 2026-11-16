import json
from pathlib import Path
from types import SimpleNamespace

import bench_metrics as mod
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


def test_aggregate_environment_includes_subagent_errors():
    tasks = [{"transcript": {
        "main": {"tool_errors": 1,
                 "error_signatures": [{"signature": "Bash: main", "count": 1}]},
        "subagents": [{"tool_errors": 2,
                       "error_signatures": [{"signature": "Edit: sub", "count": 2}]}],
    }}]
    env = aggregate_environment(tasks)
    assert env["tool_errors"] == 3
    assert any("Edit: sub" in item["signature"]
               for item in env["error_signatures"])


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
        "id": 23, "identifier": "001", "max_minutes": 30,
        "status": "planned"}), encoding="utf-8")
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
    other_logs = project / "logs" / "task#99"
    other_logs.mkdir(parents=True)
    (other_logs / "result.json").write_text(json.dumps({
        "Выполнено": True, "ОписаниеОшибки": None,
        "РезультатТестов": [{"Имя": "OTHER", "Результат": True}]}),
        encoding="utf-8")
    task = task_info(project, "task##001")
    state = collect_task_state(project, task)
    assert "DEVELOP.md" in state["files"]
    assert state["verdicts"]["REVIEW.md"] == "✓ ПРИНЯТО"
    assert "REVIEW.1.md" in state["archives"]
    assert state["archives_by_kind"]["review"] == ["REVIEW.1.md"]
    assert state["archives_by_kind"]["testing"] == []
    assert state["test_results"][0]["Выполнено"] is True
    assert len(state["test_results"]) == 1
    names = [item["Имя"] for result in state["test_results"]
             for item in result["РезультатТестов"]]
    assert "OTHER" not in names


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
        {"archives": ["REVIEW.1.md", "DEVELOP.1.md"],
         "archives_by_kind": {"review": ["REVIEW.1.md"],
                              "develop": ["DEVELOP.1.md"]},
         "verdicts": {"REVIEW.md": "✓ ПРИНЯТО"}},
        {"main": {"test_runs": 4, "smoke_runs": 1,
                  "edits": {"src/cfe/ЮнитТесты/M.bsl": 5}}})
    assert cycles == {"tests_iteration": 3, "review_iteration": 2,
                      "review_archives": 1, "develop_archives": 1,
                      "testing_archives": 0, "tests_archives": 0,
                      "test_runs": 4, "smoke_runs": 1,
                      "test_module_edits": 5, "review_verdict": "✓ ПРИНЯТО"}


def test_collect_task_state_archives_by_kind(tmp_path):
    project = tmp_path / "project"
    task_dir = project / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({
        "id": 1, "identifier": "001", "max_minutes": 30}), encoding="utf-8")
    for name in ("DEVELOP.1.md", "DEVELOP.2.md", "REVIEW.1.md",
                 "TESTING.1.md", "TESTS.1.md"):
        (task_dir / name).write_text("# архив\n", encoding="utf-8")
    state = collect_task_state(project, task_info(project, "task##001"))
    assert state["archives_by_kind"] == {
        "review": ["REVIEW.1.md"],
        "testing": ["TESTING.1.md"],
        "tests": ["TESTS.1.md"],
        "develop": ["DEVELOP.1.md", "DEVELOP.2.md"],
    }
    assert len(state["archives"]) == 5


def test_cycle_metrics_no_review_only_develop_archives(tmp_path):
    project = tmp_path / "project"
    task_dir = project / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({
        "id": 1, "identifier": "001", "max_minutes": 30}), encoding="utf-8")
    for name in ("DEVELOP.1.md", "DEVELOP.2.md"):
        (task_dir / name).write_text("# dev\n", encoding="utf-8")
    task_json = {"stages": [
        {"name": "develop", "enabled": True, "status": "failed",
         "iteration": 2},
        {"name": "review", "enabled": True, "status": "pending",
         "iteration": 1},
    ]}
    state = collect_task_state(project, task_info(project, "task##001"))
    cycles = cycle_metrics(task_json, state, {})
    assert cycles["review_archives"] == 0
    assert cycles["develop_archives"] == 2
    assert cycles["review_iteration"] == 0
    assert cycles["tests_iteration"] == 0


def test_cycle_metrics_iteration_only_for_active_stages():
    task_json = {"stages": [
        {"name": "tests", "enabled": False, "status": "done", "iteration": 4},
        {"name": "review", "enabled": True, "status": "skipped",
         "iteration": 3},
    ]}
    cycles = cycle_metrics(
        task_json, {"archives_by_kind": {"develop": ["DEVELOP.1.md"]}}, {})
    assert cycles["tests_iteration"] == 0
    assert cycles["review_iteration"] == 0
    assert cycles["review_archives"] == 0
    assert cycles["develop_archives"] == 1


def test_stage_table_runs_summed():
    task_json = {"stages": [{
        "name": "develop", "enabled": True, "status": "done", "iteration": 2,
        "started_at": "2026-01-01T00:10:00+00:00",
        "finished_at": "2026-01-01T00:11:00+00:00",
        "runs": [
            {"iteration": 1, "started_at": "2026-01-01T00:00:00+00:00",
             "finished_at": "2026-01-01T00:01:30+00:00"},
            {"iteration": 2, "started_at": "2026-01-01T00:10:00+00:00",
             "finished_at": "2026-01-01T00:11:00+00:00"},
            {"iteration": 2, "started_at": "2026-01-01T00:20:00+00:00",
             "finished_at": None},
        ],
    }]}
    stage = stage_table(task_json)[0]
    assert stage["duration_sec"] == 60.0
    assert stage["duration_sec_total"] == 150.0
    assert len(stage["runs"]) == 3


def test_stage_table_numeric_runs_stamps_summed():
    """Числовые epoch-отметки в runs[] — сумма длительностей, а не None."""
    task_json = {"stages": [{
        "name": "develop", "enabled": True, "status": "done", "iteration": 2,
        "started_at": 1767226200.0,
        "finished_at": 1767226260,
        "runs": [
            {"iteration": 1, "started_at": 1767225600.0,
             "finished_at": 1767225690.0},
            {"iteration": 2, "started_at": 1767226200,
             "finished_at": 1767226260},
            # числовые отметки этапа тоже; последний прогон открыт — в сумму не идёт
            {"iteration": 2, "started_at": 1767226500, "finished_at": None},
        ],
    }]}
    stage = stage_table(task_json)[0]
    assert stage["duration_sec_total"] == 150.0
    assert stage["duration_sec_total"] is not None


def test_stage_table_numeric_runs_with_string_iteration_not_skipped():
    """Числовые отметки runs[] при строковом iteration этапа: сумма, не None.

    `int(stage["iteration"])` падает на "2.0" — без толерантного разбора
    длительность по runs[] потерялась бы целиком."""
    task_json = {"stages": [{
        "name": "develop", "enabled": True, "status": "done", "iteration": "2.0",
        "runs": [
            {"iteration": "1", "started_at": 1767225600.0,
             "finished_at": 1767225660.0},
            {"iteration": 2, "started_at": 1767226200.0,
             "finished_at": 1767226260.0},
        ],
    }]}
    stage = stage_table(task_json)[0]
    assert stage["iteration"] == 2
    assert stage["duration_sec_total"] == 120.0


def test_stage_table_and_runs_tolerant_iteration():
    """Строки/дробные iteration не роняют метрики: int-значение или 1."""
    task_json = {"stages": [{
        "name": "develop", "enabled": True, "status": "done", "iteration": "2.0",
        "runs": [{"iteration": 2.5, "started_at": "2026-01-01T00:00:00+00:00",
                  "finished_at": "2026-01-01T00:01:00+00:00"},
                 {"iteration": "abc", "started_at": None, "finished_at": None}],
    }]}
    stage = stage_table(task_json)[0]
    assert stage["iteration"] == 2
    assert [run["iteration"] for run in stage["runs"]] == [2, 1]
    cycles = cycle_metrics(task_json, {}, {})
    assert cycles["tests_iteration"] == 0


def test_cycle_metrics_tests_stage_and_archives(tmp_path):
    """Активный tests (итерация 3) + TESTS.1.md + TESTING.1.md."""
    project = tmp_path / "project"
    task_dir = project / "tasks" / "task##001"
    task_dir.mkdir(parents=True)
    (task_dir / "task.json").write_text(json.dumps({
        "id": 1, "identifier": "001", "max_minutes": 30}), encoding="utf-8")
    for name in ("TESTS.1.md", "TESTING.1.md"):
        (task_dir / name).write_text("# архив\n", encoding="utf-8")
    task_json = {"stages": [
        {"name": "tests", "enabled": True, "status": "done", "iteration": 3},
        {"name": "testing", "enabled": True, "status": "done", "iteration": 2},
    ]}
    state = collect_task_state(project, task_info(project, "task##001"))
    cycles = cycle_metrics(task_json, state, {})
    assert cycles["tests_iteration"] == 3
    assert cycles["tests_archives"] == 1
    assert cycles["testing_archives"] == 1


def test_stage_table_without_runs_falls_back():
    task_json = {"stages": [
        {"name": "tests", "enabled": True, "status": "done", "iteration": 1,
         "started_at": "2026-01-01T00:00:00+00:00",
         "finished_at": "2026-01-01T00:02:00+00:00"},
        {"name": "review", "enabled": False, "status": "pending",
         "iteration": 1, "runs": []},
    ]}
    stages = stage_table(task_json)
    assert stages[0]["runs"] == []
    assert stages[0]["duration_sec_total"] == 120.0
    assert stages[1]["duration_sec_total"] is None


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


from bench_metrics import render_digest


def test_render_digest_contains_key_sections():
    metrics = {
        "run": {"run_id": "20260101-000000", "project_dir": "/p",
                "claude_cmd": "claude-ds", "force": False},
        "tasks": [{
            "folder": "task##001", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 120.0, "exit_code": 0,
            "stream": {"num_turns": 12, "session_id": "s"},
            "stages": [{"name": "develop", "enabled": True, "status": "done",
                        "iteration": 2, "duration_sec": 60.0}],
            "cycles": {"tests_iteration": 2, "review_iteration": 1,
                       "test_runs": 3, "smoke_runs": 1,
                       "test_module_edits": 4, "review_archives": 0},
            "transcript": {"source": "session", "main": {
                "tool_errors": 1,
                "error_signatures": [{"signature": "Bash: command not found",
                                      "count": 1}],
                "slow_ops": [{"tool": "Bash", "input": "run-tests.py",
                              "duration_sec": 90.0}],
                "gaps": [{"after": "Bash", "before": "Read", "gap_sec": 400,
                          "at": "2026-01-01T00:00:00+00:00"}],
                "tools": {"Bash": 5}}},
        }],
        "environment": {"tool_errors": 1,
                        "error_signatures": [{"signature": "Bash: command not found",
                                              "count": 1}],
                        "command_not_found": 1, "timeouts": 0,
                        "mcp_errors": 0},
    }
    text = render_digest(metrics)
    assert "# Дайджест benchmark-прогона" in text
    assert "task##001" in text
    assert "command not found" in text
    assert "run-tests.py" in text
    assert "400" in text


def _digest_metrics(task: dict) -> dict:
    return {"run": {"run_id": "r", "project_dir": "/p", "claude_cmd": "c"},
            "tasks": [task], "environment": {}}


def _digest_review_cell(task: dict) -> str:
    text = render_digest(_digest_metrics(task))
    row = next(line for line in text.splitlines()
               if line.startswith(f"| {task['folder']} "))
    cells = [cell.strip() for cell in row.strip("|").split(" | ")]
    return cells[-1]


def test_render_digest_review_not_done_when_pending():
    task = {"folder": "task##008", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0,
            "stages": [{"name": "review", "enabled": True, "status": "pending",
                        "iteration": 1, "duration_sec": None}],
            "cycles": {"tests_iteration": 1, "review_iteration": 0,
                       "review_archives": 0, "develop_archives": 2},
            "transcript": {}}
    cell = _digest_review_cell(task)
    assert cell == "ревью не проводилось"
    assert "итераций" not in cell


def test_render_digest_review_not_done_when_disabled_or_absent():
    for stages in ([{"name": "review", "enabled": False,
                     "status": "pending", "iteration": 1}],
                   [{"name": "develop", "enabled": True, "status": "done",
                     "iteration": 1}]):
        task = {"folder": "task##009", "limit_minutes": 30,
                "outcome": "success", "duration_sec": 5.0, "exit_code": 0,
                "stages": stages, "cycles": {}, "transcript": {}}
        assert _digest_review_cell(task) == "ревью не проводилось"


def test_render_digest_review_iterations_shown():
    task = {"folder": "task##010", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0,
            "stages": [{"name": "review", "enabled": True, "status": "done",
                        "iteration": 2, "duration_sec": 30.0}],
            "cycles": {"review_iteration": 2, "review_archives": 1,
                       "develop_archives": 1, "testing_archives": 0,
                       "tests_archives": 0},
            "transcript": {}}
    assert _digest_review_cell(task) == "итераций 2, архивов 1"


def test_render_digest_none_values_rendered_as_dash():
    task = {"folder": "task##002", "limit_minutes": 30, "outcome": "error",
            "duration_sec": 10.0, "exit_code": None,
            "stream": {"num_turns": 1, "session_id": None},
            "stages": [], "cycles": {}, "transcript": {}}
    text = render_digest(_digest_metrics(task))
    assert "код выхода: `—`" in text
    assert "session=—" in text
    assert "session=None" not in text
    assert "`None`" not in text


def test_render_digest_warns_on_unsuccessful_outcome():
    task = {"folder": "task##005", "limit_minutes": 30, "outcome": "timeout",
            "duration_sec": 1800.0, "exit_code": None, "stages": [], "cycles": {},
            "transcript": {}}
    text = render_digest(_digest_metrics(task))
    heading = text.index("## task##005")
    warning = text.index(
        "- ⚠ результаты задачи недостоверны: исход timeout — артефакты и "
        "анализаторы могут быть неполными")
    assert warning > heading


def test_render_digest_bad_duration_does_not_raise():
    task = {"folder": "task##003", "limit_minutes": 30, "outcome": "error",
            "duration_sec": "oops", "exit_code": 1, "transcript": {}}
    text = render_digest(_digest_metrics(task))
    assert "код выхода: `1`" in text
    assert "время: —" in text


def test_render_digest_escapes_pipe_in_tables():
    task = {"folder": "task##004", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0, "stages": [], "cycles": {},
            "transcript": {"main": {"slow_ops": [
                {"tool": "Bash", "input": "a | b", "duration_sec": 3.5}]}}}
    text = render_digest(_digest_metrics(task))
    assert "`a \\| b`" in text
    slow_row = next(line for line in text.splitlines() if "a \\| b" in line)
    assert slow_row.count("|") - slow_row.count("\\|") == 4
    task_row = next(line for line in text.splitlines()
                    if line.startswith("| task##004 "))
    assert task_row.count("|") == 8  # 7 столбцов


def test_render_digest_newline_in_cell_replaced():
    task = {"folder": "task##005", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0, "stages": [], "cycles": {},
            "transcript": {"main": {"slow_ops": [
                {"tool": "Bash", "input": "a\nb", "duration_sec": 1.0}]}}}
    text = render_digest(_digest_metrics(task))
    assert "`a b`" in text


def test_render_digest_analyzers_absent():
    task = {"folder": "task##006", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0, "transcript": {}}
    text = render_digest(_digest_metrics(task))
    assert "### Анализаторы" in text
    assert "анализаторы не запускались" in text
    assert "файлов 0" not in text


def test_render_digest_query_findings():
    task = {"folder": "task##007", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0, "transcript": {},
            "analyzers": {"query_analyze": {
                "skipped": None,
                "results": {"/p/Module.bsl": {
                    "findings": {"error": 1, "warning": 0, "info": 2}}}}}}
    text = render_digest(_digest_metrics(task))
    assert "query-analyze: файлов 1" in text
    assert "  - `Module.bsl`: error=1, warning=0, info=2" in text
    assert "анализаторы не запускались" not in text


def test_task_log_dirs_uses_identifier_and_folder(tmp_path):
    logs = tmp_path / "logs"
    (logs / "task##002").mkdir(parents=True)
    task = SimpleNamespace(folder="task##002", identifier="#002",
                           raw={"id": 24})
    dirs = mod._task_log_dirs(tmp_path, task)
    assert logs / "task##002" in dirs
    assert logs / "task#002" in dirs
    assert logs / "task#24" in dirs
    assert logs / "task##24" in dirs


def test_cycle_metrics_includes_subagents(tmp_path):
    main = {"test_runs": 1, "smoke_runs": 1,
            "edits": {"src/cfe/ЮнитТесты/Module.bsl": 1}}
    sub = {"test_runs": 3, "smoke_runs": 0,
           "edits": {"src/cfe/ЮнитТесты/Module.bsl": 2}}
    metrics = mod.cycle_metrics(
        {"stages": []}, {}, {"main": main, "subagents": [sub]})
    assert metrics["test_runs"] == 4
    assert metrics["smoke_runs"] == 1
    assert metrics["test_module_edits"] == 3


def test_render_digest_warns_on_extract_returncode():
    task = {"folder": "task##011", "limit_minutes": 30, "outcome": "success",
            "duration_sec": 5.0, "exit_code": 0, "transcript": {},
            "analyzers": {"query_analyze": {
                "skipped": None,
                "results": {"/p/Module.bsl": {
                    "findings": {"error": 0, "warning": 0, "info": 0},
                    "extract_returncode": 1}}}}}
    text = render_digest(_digest_metrics(task))
    assert ("  - ⚠ extract_queries вернул код 1 — запрос мог не проверяться "
            "(см. warnings)") in text


def test_render_digest_no_extract_warning_on_success():
    for code in (0, None):
        task = {"folder": "task##012", "limit_minutes": 30,
                "outcome": "success", "duration_sec": 5.0, "exit_code": 0,
                "transcript": {},
                "analyzers": {"query_analyze": {
                    "skipped": None,
                    "results": {"/p/Module.bsl": {
                        "findings": {"error": 0, "warning": 0, "info": 0},
                        "extract_returncode": code}}}}}
        text = render_digest(_digest_metrics(task))
        assert "extract_queries вернул код" not in text

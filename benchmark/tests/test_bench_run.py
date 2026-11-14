import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from bench_metrics import find_session_files, parse_stream
from bench_run import (BenchError, TaskInfo, _task_aliases, apply_limits,
                       build_options, changed_files, check_freshness,
                       collect_diff,
                       discover_tasks, git_state, parse_args, parse_limit_arg,
                       parse_minutes, read_env_file, resolve_project_dir,
                       run_claude, select_tasks)


def write_fake_claude(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
    path.chmod(0o755)
    return path


def test_parse_stream(tmp_path):
    stream = tmp_path / "s.jsonl"
    stream.write_text("\n".join([
        json.dumps({"type": "system", "subtype": "init",
                    "session_id": "sid-1"}),
        "not json",
        json.dumps({"type": "result", "is_error": False, "result": "ok",
                    "session_id": "sid-1", "duration_ms": 5}),
    ]) + "\n", encoding="utf-8")
    summary = parse_stream(stream)
    assert summary.session_id == "sid-1"
    assert summary.result["result"] == "ok"
    assert summary.parse_errors == 1


def test_find_session_files(tmp_path):
    sid = "abc"
    project = tmp_path / "projects" / "-tmp-x"
    project.mkdir(parents=True)
    main = project / f"{sid}.jsonl"
    main.write_text("", encoding="utf-8")
    sub = project / sid / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a.jsonl").write_text("", encoding="utf-8")
    files = find_session_files(sid, projects_root=tmp_path / "projects")
    assert files.main == main
    assert files.subagents == (sub / "agent-a.jsonl",)
    assert find_session_files("missing", projects_root=tmp_path / "projects").main is None


def test_find_session_files_case_insensitive(tmp_path):
    project = tmp_path / "projects" / "-tmp-x"
    project.mkdir(parents=True)
    main = project / "fake-session.jsonl"
    main.write_text("", encoding="utf-8")
    sub = project / "fake-session" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-a.jsonl").write_text("", encoding="utf-8")
    files = find_session_files("FAKE-SESSION", projects_root=tmp_path / "projects")
    assert files.main == main
    assert files.subagents == (sub / "agent-a.jsonl",)


def test_run_claude_result(tmp_path):
    fake = write_fake_claude(tmp_path / "fake", "\n".join([
        "import json",
        f"print(json.dumps({{'type':'system','subtype':'init','session_id':'sid-2'}}))",
        f"print(json.dumps({{'type':'result','is_error':False,'result':'ok','session_id':'sid-2'}}))",
    ]) + "\n")
    run = run_claude(cmd=str(fake), prompt="hi", cwd=tmp_path, timeout_sec=10,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.exit_code == 0
    assert run.timed_out is False
    assert run.stream.result["result"] == "ok"
    assert run.stream.session_id == "sid-2"


def test_run_claude_timeout_kills_process(tmp_path):
    fake = write_fake_claude(tmp_path / "sleep", "import time\ntime.sleep(30)\n")
    run = run_claude(cmd=str(fake), prompt="hi", cwd=tmp_path, timeout_sec=0.5,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.timed_out is True
    assert run.duration_sec < 10
    assert run.exit_code is not None


def test_run_claude_timeout_kills_descendants(tmp_path):
    pid_file = tmp_path / "grandchild.pid"
    fake = write_fake_claude(tmp_path / "parent", "\n".join([
        "import subprocess, sys, time",
        f"child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; "
        "signal.signal(signal.SIGINT, signal.SIG_IGN); "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)'])",
        f"open({str(pid_file)!r}, 'w').write(str(child.pid))",
        "time.sleep(30)",
    ]) + "\n")
    run = run_claude(cmd=str(fake), prompt="hi", cwd=tmp_path, timeout_sec=0.5,
                     stream_path=tmp_path / "out.jsonl",
                     stderr_path=tmp_path / "err.log")
    assert run.timed_out is True
    pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail(f"потомок {pid} остался жив после таймаута")


def make_project(root: Path) -> Path:
    project = root / "project"
    tasks = project / "tasks"
    for folder, ident, minutes in (("task##001", "#001", 30),
                                   ("task##002", "#002", 60)):
        task_dir = tasks / folder
        task_dir.mkdir(parents=True)
        (task_dir / "task.json").write_text(json.dumps({
            "identifier": ident,
            "status": "planned",
            "max_minutes": minutes,
            "stages": [],
        }), encoding="utf-8")
        (task_dir / "TASK.md").write_text("# TASK\n", encoding="utf-8")
    return project


def test_parse_minutes_units():
    assert parse_minutes("30") == 30
    assert parse_minutes("30м") == 30
    assert parse_minutes("30М") == 30
    assert parse_minutes("2ч") == 120
    assert parse_minutes("2h") == 120
    for bad in ("0", "-1", "abc", "", "1.5ч"):
        with pytest.raises(BenchError):
            parse_minutes(bad)


def test_parse_limit_arg():
    assert parse_limit_arg("task##001=30м") == ("task##001", 30)
    with pytest.raises(BenchError):
        parse_limit_arg("task##001")
    with pytest.raises(BenchError):
        parse_limit_arg("=30")


def test_read_env_file(tmp_path):
    path = tmp_path / "test.env"
    path.write_text("# comment\nA=1\nB = x y\n\n", encoding="utf-8")
    assert read_env_file(path) == {"A": "1", "B": "x y"}


def test_resolve_project_dir_from_env(tmp_path):
    project = make_project(tmp_path)
    env = tmp_path / "test.env"
    env.write_text(f"BENCH_PROJECT_DIR={project}\n", encoding="utf-8")
    assert resolve_project_dir(None, env, tmp_path) == project.resolve()
    assert resolve_project_dir(str(project), tmp_path / "missing.env",
                               tmp_path) == project.resolve()


def test_resolve_project_dir_requires_value(tmp_path):
    with pytest.raises(BenchError):
        resolve_project_dir(None, tmp_path / "missing.env", tmp_path)


def test_discover_and_select(tmp_path):
    project = make_project(tmp_path)
    tasks = discover_tasks(project)
    assert [t.folder for t in tasks] == ["task##001", "task##002"]
    assert tasks[0].identifier == "#001"
    assert tasks[0].max_minutes == 30
    assert select_tasks(tasks, []) == tasks
    assert [t.folder for t in select_tasks(tasks, ["#002"])] == ["task##002"]
    assert [t.folder for t in select_tasks(tasks, ["001"])] == ["task##001"]
    with pytest.raises(BenchError):
        select_tasks(tasks, ["nope"])


def test_empty_selector_does_not_match_any_task(tmp_path):
    tasks = discover_tasks(make_project(tmp_path))
    with pytest.raises(BenchError):
        select_tasks(tasks, [""])


def test_degenerate_identifier_has_no_empty_alias(tmp_path):
    task = TaskInfo(folder="task##001", path=tmp_path, identifier="#",
                    max_minutes=30, status="", raw={})
    assert "" not in _task_aliases(task)


def test_apply_limits_and_duplicates(tmp_path):
    tasks = discover_tasks(make_project(tmp_path))
    assert apply_limits(tasks, []) == {"task##001": 30, "task##002": 60}
    assert apply_limits(tasks, ["#001=45"])["task##001"] == 45
    with pytest.raises(BenchError):
        apply_limits(tasks, ["#001=45", "task##001=50"])
    with pytest.raises(BenchError):
        apply_limits(tasks, ["#999=10"])


def test_build_options(tmp_path):
    project = make_project(tmp_path)
    env = tmp_path / "test.env"
    env.write_text(f"BENCH_PROJECT_DIR={project}\n", encoding="utf-8")
    ns = parse_args(["--env", str(env), "--task", "#001", "--limit", "#001=30м",
                     "--analysis-timeout", "15"])
    opts = build_options(ns, tmp_path)
    assert opts.project_dir == project.resolve()
    assert [t.folder for t in opts.tasks] == ["task##001"]
    assert opts.limits == {"task##001": 30}
    assert opts.analysis_timeout_min == 15
    assert opts.run_dir is None


def git(project: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=project, text=True,
                          capture_output=True, check=True)
    return proc.stdout


def make_git_project(root: Path) -> Path:
    project = make_project(root)
    git(project, "init", "-q")
    git(project, "config", "user.email", "bench@example.ru")
    git(project, "config", "user.name", "Bench")
    (project / ".gitignore").write_text("/tmp\n", encoding="utf-8")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    git(project, "commit", "-q", "--allow-empty", "-m", "baseline before task#001")
    return project


def test_check_freshness_clean_and_problems(tmp_path):
    project = make_git_project(tmp_path)
    tasks = discover_tasks(project)
    assert check_freshness(project, tasks) == []
    (tasks[0].path / "DEVELOP.md").write_text("# x\n", encoding="utf-8")
    assert any("DEVELOP" in problem for problem in check_freshness(project, tasks))
    (tasks[0].path / "DEVELOP.md").unlink()
    (project / "changed.txt").write_text("x", encoding="utf-8")
    assert any("незакоммиченные" in problem for problem in check_freshness(project, tasks))
    assert check_freshness(project, tasks, force=True) == []


def test_check_freshness_requires_planned_and_baseline(tmp_path):
    project = make_git_project(tmp_path)
    tasks = discover_tasks(project)
    data = json.loads((tasks[0].path / "task.json").read_text(encoding="utf-8"))
    data["status"] = "running"
    (tasks[0].path / "task.json").write_text(json.dumps(data), encoding="utf-8")
    tasks = discover_tasks(project)
    problems = check_freshness(project, tasks)
    assert any("planned" in problem for problem in problems)

    project2 = make_project(tmp_path / "second")
    git(project2, "init", "-q")
    git(project2, "config", "user.email", "bench@example.ru")
    git(project2, "config", "user.name", "Bench")
    git(project2, "add", "-A")
    git(project2, "commit", "-q", "-m", "init")
    assert any("baseline" in problem
               for problem in check_freshness(project2, discover_tasks(project2)))


def test_collect_diff_includes_tracked_and_untracked(tmp_path):
    project = make_git_project(tmp_path)
    before = git_state(project).head
    tracked = project / "tracked.txt"
    tracked.write_text("one\n", encoding="utf-8")
    git(project, "add", "tracked.txt")
    git(project, "commit", "-q", "-m", "add tracked")
    (project / "new.txt").write_text("new\n", encoding="utf-8")
    out = tmp_path / "diff.txt"
    stat = tmp_path / "stat.txt"
    changed = collect_diff(project, before, out, stat)
    text = out.read_text(encoding="utf-8")
    assert "tracked.txt" in text and "new.txt" in text
    assert "tracked.txt" in changed and "new.txt" in changed
    assert "tracked.txt" in stat.read_text(encoding="utf-8")


def test_changed_files_rejects_invalid_before_head(tmp_path):
    project = make_git_project(tmp_path)
    with pytest.raises(BenchError):
        changed_files(project, "0" * 40)

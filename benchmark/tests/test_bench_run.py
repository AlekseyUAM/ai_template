import json
from pathlib import Path

import pytest

from bench_run import (BenchError, apply_limits, build_options, discover_tasks,
                       parse_args, parse_limit_arg, parse_minutes,
                       read_env_file, resolve_project_dir, select_tasks)


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

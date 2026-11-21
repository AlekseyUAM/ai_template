import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bench_run import build_task_prompt


REPO = Path(__file__).resolve().parents[2]
CLI = REPO / "benchmark" / "run_benchmark.py"


def git(project: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=project, check=True,
                   capture_output=True, text=True)


def make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir()
    (project / ".gitignore").write_text("/tmp\n", encoding="utf-8")
    for folder, ident in (("task#001", "#001"), ("task#002", "#002")):
        task_dir = project / "tasks" / folder
        task_dir.mkdir(parents=True)
        (task_dir / "TASK.md").write_text(f"# Задача {ident}\n", encoding="utf-8")
        (task_dir / "task.json").write_text(json.dumps({
            "identifier": ident, "status": "planned", "max_minutes": 30,
            "stages": [{"name": "develop", "enabled": True, "status": "pending",
                        "iteration": 1}],
        }), encoding="utf-8")
    git(project, "init", "-q")
    git(project, "config", "user.email", "bench@example.ru")
    git(project, "config", "user.name", "Bench")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "init")
    git(project, "commit", "-q", "--allow-empty", "-m", "baseline before task#001")
    return project


FAKE = r'''#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path

prompt = sys.stdin.read()
sid = "fake-session"
out = []

if prompt.startswith("Выполни задачу tasks/"):
    folder = re.search(r"Выполни задачу tasks/(\S+)", prompt).group(1).split("/")[-1]
    marker = Path(os.environ["FAKE_MARKER"])
    marker.write_text(marker.read_text() + "x" if marker.exists() else "x")
    if os.environ.get("FAKE_FAIL") == folder:
        out.append({"type": "result", "subtype": "error", "session_id": sid,
                    "is_error": True, "result": "boom", "duration_ms": 1})
        print("\n".join(json.dumps(x, ensure_ascii=False) for x in out))
        sys.exit(1)
    task_dir = Path.cwd() / "tasks" / folder
    data = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
    for stage in data.get("stages", []):
        if stage.get("enabled"):
            stage["status"] = "done"
            stage["iteration"] = 2
            stage["started_at"] = "2026-01-01T00:00:00+00:00"
            stage["finished_at"] = "2026-01-01T00:01:00+00:00"
    data["status"] = "done"
    (task_dir / "task.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    (task_dir / "DEVELOP.md").write_text("# DEVELOP\n", encoding="utf-8")
    proj = Path.home() / ".claude" / "projects" / "fake"
    proj.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "assistant", "timestamp": "2026-01-01T00:00:00Z",
         "message": {"content": [{"type": "tool_use", "id": "t1",
                                  "name": "Bash",
                                  "input": {"command": "python .claude/tools/run-tests.py c"}}]}},
        {"type": "user", "timestamp": "2026-01-01T00:00:30Z",
         "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                                  "content": "ok"}]}},
    ]
    (proj / f"{sid}.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    out.append({"type": "result", "subtype": "success", "session_id": sid,
                "is_error": False, "result": "done", "duration_ms": 1,
                "num_turns": 3})
else:
    out.append({"type": "result", "subtype": "success", "session_id": sid + "-a",
                "is_error": False, "duration_ms": 1,
                "result": "# Результат benchmark-прогона\n\n## Сводка прогона\n\nok"})
print("\n".join(json.dumps(x, ensure_ascii=False) for x in out))
'''


@pytest.fixture
def env(tmp_path):
    project = make_project(tmp_path)
    script = tmp_path / "fake-claude.py"
    script.write_text(FAKE, encoding="utf-8")
    if os.name == "nt":
        # Windows не исполняет shebang-скрипты напрямую (WinError 193) —
        # оборачиваем в .bat, который запускает тот же интерпретатор.
        fake = tmp_path / "fake-claude.bat"
        fake.write_text(
            '@echo off\r\n' + f'"{sys.executable}" "{script}" %*\r\n',
            encoding="utf-8")
    else:
        script.chmod(0o755)
        fake = script
    home = tmp_path / "home"
    home.mkdir()
    marker = tmp_path / "marker"
    values = dict(os.environ)
    values.update({"HOME": str(home), "USERPROFILE": str(home),
                   "FAKE_MARKER": str(marker), "PYTHONIOENCODING": "utf-8"})
    return project, fake, marker, values


def run_cli(project, fake, values, *extra):
    return subprocess.run(
        [sys.executable, str(CLI), "--project", str(project),
         "--claude-cmd", str(fake), *extra],
        cwd=REPO, env=values, capture_output=True, text=True,
        encoding="utf-8", timeout=120)


def test_task_prompt_triggers_single_agent():
    prompt = build_task_prompt("task#001")
    assert "tasks/task#001" in prompt
    assert "tasks/task#" in prompt
    assert "single-agent-workflow" in prompt
    assert "чеклист" in prompt
    assert "30 мин" in build_task_prompt("task#001", 30)


def test_e2e_success_with_analysis(env):
    project, fake, marker, values = env
    proc = run_cli(project, fake, values)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = (project / "tmp" / "RESULT.md").read_text(encoding="utf-8")
    assert report.startswith("# Результат benchmark-прогона")
    assert "## Сводка прогона" in report
    assert marker.read_text() == "xx"
    runs = sorted((project / "tmp" / "benchmark").iterdir())
    metrics = json.loads((runs[-1] / "metrics.json").read_text(encoding="utf-8"))
    assert [task["outcome"] for task in metrics["tasks"]] == ["success", "success"]
    assert metrics["run"]["contaminated"] is False
    assert (runs[-1] / "digest.md").is_file()
    assert (runs[-1] / "diffs" / "task#001.diff").is_file()
    assert (runs[-1] / "analysis-inputs" / "metrics.json").is_file()
    assert (runs[-1] / "analysis-transcripts" / "analyst.stream.jsonl").is_file()
    assert not (runs[-1] / "transcripts" / "analyst.stream.jsonl").exists()
    snapshot = json.loads(
        (runs[-1] / "analysis-inputs" / "metrics.json").read_text(encoding="utf-8"))
    assert "analysis" not in snapshot


def test_e2e_stops_after_failure_but_analyzes(env):
    project, fake, marker, values = env
    values = dict(values)
    values["FAKE_FAIL"] = "task#001"
    proc = run_cli(project, fake, values)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert marker.read_text() == "x"
    data = json.loads((project / "tasks" / "task#002" / "task.json")
                      .read_text(encoding="utf-8"))
    assert data["status"] == "planned"
    assert (project / "tmp" / "RESULT.md").is_file()


def test_e2e_skip_analysis(env):
    project, fake, marker, values = env
    proc = run_cli(project, fake, values, "--skip-analysis")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = (project / "tmp" / "RESULT.md").read_text(encoding="utf-8")
    assert "Качественный анализ пропущен" in report


def test_e2e_refuses_dirty_project(env):
    project, fake, marker, values = env
    (project / "tasks" / "task#001" / "DEVELOP.md").write_text("x", encoding="utf-8")
    proc = run_cli(project, fake, values)
    assert proc.returncode == 1
    assert "не готов" in proc.stderr
    assert not marker.exists()


def test_e2e_rejects_missing_claude_cmd(env):
    project, fake, marker, values = env
    proc = run_cli(project, Path("/nonexistent/claude"), values)
    assert proc.returncode == 1
    assert "команда агента" in proc.stderr
    assert not marker.exists()

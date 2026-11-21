from pathlib import Path

from bench_analysis import (build_prompt, deterministic_report,
                            extract_analyst_text, write_report)
from bench_metrics import StreamSummary


def test_build_prompt_has_constraints_and_no_orchestration_trigger(tmp_path):
    prompt = build_prompt(
        run_id="20260101-000000",
        project_dir=tmp_path / "project",
        repo_root=tmp_path / "repo",
        run_dir=tmp_path / "run",
        metrics_path=tmp_path / "run" / "metrics.json",
        digest_path=tmp_path / "run" / "digest.md",
        manifest_path=tmp_path / "run" / "analysis-inputs.md",
        reference_path=tmp_path / "repo" / "benchmark" / "example.bsl",
        contaminated=False,
        task_folders=["task#001", "task#002"],
    )
    assert "не затачивай" in prompt.lower()
    assert "example.bsl" in prompt
    assert "RESULT.md" not in prompt  # отчёт пишет скрипт, не аналитик
    assert "tasks/task#" not in prompt  # не триггерит route_to_checklists
    assert "Запрещено: Edit/Write/MultiEdit/NotebookEdit" in prompt
    assert "metrics.json" in prompt
    assert "analysis-inputs.md" in prompt
    for header in ("Время выполнения", "Итерации написания", "Итерации код-ревью",
                   "Качество кода", "Окружение template", "Рекомендации",
                   "Что уже работает хорошо"):
        assert header in prompt


def test_extract_analyst_text():
    stream = StreamSummary(result={"is_error": False, "result": "# Отчёт\n"})
    assert extract_analyst_text(stream) == "# Отчёт\n"
    assert extract_analyst_text(StreamSummary(result=None)) is None
    assert extract_analyst_text(
        StreamSummary(result={"is_error": True, "result": "boom"})) is None


def test_deterministic_report(tmp_path):
    metrics = {"run": {"run_id": "r1", "project_dir": "/p"},
               "tasks": [{"folder": "task#001", "outcome": "timeout",
                          "duration_sec": 1800, "limit_minutes": 30}],
               "analysis": {}}
    text = deterministic_report(run_id="r1", project_dir=tmp_path,
                                run_dir=tmp_path / "run", metrics=metrics,
                                error="аналитик упал")
    assert "аналитик упал" in text
    assert "task#001" in text
    skipped = deterministic_report(run_id="r1", project_dir=tmp_path,
                                   run_dir=tmp_path / "run", metrics=metrics,
                                   skipped=True)
    assert "пропущен" in skipped.lower()


def test_write_report_atomic(tmp_path):
    project = tmp_path / "project"
    path = write_report(project, "# hi\n")
    assert path == project / "tmp" / "RESULT.md"
    assert path.read_text(encoding="utf-8") == "# hi\n"

from pathlib import Path
TPL = Path(__file__).resolve().parents[3] / "template" / ".claude"
SEVEN = ["ANALYZE.md","ARCHITECT.md","TESTS.md","DEVELOP.md","TESTING.md","REVIEW.md","DOCS.md"]

def test_task_artifacts_rule_lists_all_seven():
    text = (TPL / "rules" / "task-artifacts.md").read_text(encoding="utf-8")
    for a in SEVEN:
        assert a in text, a

def test_developer_tests_names_tests_artifact():
    text = (TPL / "agents" / "developer-tests.md").read_text(encoding="utf-8")
    assert "TESTS.md" in text


def test_orchestrator_names_testing_artifact():
    # Этап testing (и его артефакт TESTING.md) ведёт оркестратор — субагента нет.
    text = (TPL / "skills" / "task-orchestration" / "SKILL.md").read_text(encoding="utf-8")
    assert "TESTING.md" in text

def test_developer_names_develop():
    text = (TPL / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "DEVELOP.md" in text

def test_technical_writer_names_docs():
    text = (TPL / "agents" / "technical-writer.md").read_text(encoding="utf-8")
    assert "DOCS.md" in text

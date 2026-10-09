from pathlib import Path
TPL = Path(__file__).resolve().parents[3] / "template" / ".claude"
SEVEN = ["ANALYZE.md","ARCHITECT.md","TESTS.md","DEVELOP.md","TESTING.md","REVIEW.md","DOCS.md"]

def test_task_artifacts_rule_lists_all_seven():
    text = (TPL / "rules" / "task-artifacts.md").read_text(encoding="utf-8")
    for a in SEVEN:
        assert a in text, a

def test_tester_names_both_stages():
    text = (TPL / "agents" / "tester.md").read_text(encoding="utf-8")
    assert "TESTS.md" in text and "TESTING.md" in text and "TEST.md" not in text

def test_developer_names_docs():
    text = (TPL / "agents" / "developer.md").read_text(encoding="utf-8")
    assert "DEVELOP.md" in text and "DOCS.md" in text

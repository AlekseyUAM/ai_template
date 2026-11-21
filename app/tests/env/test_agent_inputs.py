from pathlib import Path

CHECKLISTS = Path(__file__).resolve().parents[3] / "template" / ".claude" / "checklists"


def test_each_checklist_input_is_degradable():
    # downstream-этапы должны допускать отсутствие предыдущих артефактов и падать на TASK.md
    for name in ("architect", "developer-tests", "developer", "reviewer",
                 "technical-writer"):
        text = (CHECKLISTS / f"{name}.md").read_text(encoding="utf-8")
        assert "TASK.md" in text, f"{name}: нет упоминания TASK.md как fallback"


def test_analyst_explicitly_mentions_task_md():
    # analyst должен явно упомянуть TASK.md
    text = (CHECKLISTS / "analyst.md").read_text(encoding="utf-8")
    assert "TASK.md" in text, "analyst: нет упоминания TASK.md"
